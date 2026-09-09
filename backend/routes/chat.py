import asyncio
import json
import re
import time
import traceback
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from backend.database import get_db, async_session
from backend.models import APIKey, Conversation, ContextCompaction, Message, User
from backend.schemas import (
    ChatRequest, ChatResponse, ChatResponseItem, MessageResponse, RetryRequest, EditMessageRequest,
    CompactionResponse,
)
from backend.providers import get_provider, is_vision_model
from backend.auth import get_current_user
from backend.context_compaction import maybe_compact_context, estimate_usage_pct
from backend.memory_injection import build_memory_preface
from backend.memory_pipeline import extract_and_store
from backend.mom_prompts import MOM_SYSTEM_PROMPT
from backend.transcript_sourcing import build_indexed_transcript, build_mom_user_content, parse_and_validate_mom

router = APIRouter(prefix="/api/chat", tags=["Chat"])

_TURN_PREFIX_RE = re.compile(r"^\s*\[Turn \d+\]\s*", re.IGNORECASE)
_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)
_UNCLOSED_THINK_RE = re.compile(r"<think>(.*)", re.IGNORECASE | re.DOTALL)

# Final catch-all: whatever the exact reason (reasoning cut off with no real
# answer following it, a content filter, something we haven't seen yet), an
# assistant message must never silently render as a blank bubble — but it also
# must never dump the model's raw <think> reasoning into the chat as a
# substitute. This short note is the only thing shown in that case.
_EMPTY_RESPONSE_NOTE = (
    "This model returned an empty response — it may have run out of length "
    "while still \"thinking\" without producing a final answer. Try again, or "
    "ask for something more focused."
)

# "Generate with sources" note for the same situation, but where the model DID
# return text — just never the requested structured/cited format. Some models
# narrate their reasoning as plain prose with no <think> tag or other marker
# at all ("Here's my thinking process: 1. ..."), so there's nothing to detect
# and strip — but we already know, from the parse failing, that this isn't
# the real deliverable, so it shouldn't be shown as if it were.
_MOM_NO_STRUCTURED_OUTPUT_NOTE = (
    "This model didn't produce the requested structured, sourced summary — it "
    "may have run out of length while still reasoning through the task. Try "
    "again, or try a different model."
)


def _strip_turn_prefix(content: str) -> str:
    """Strip a leaked '[Turn N] ' marker some models echo back from the prompt."""
    return _TURN_PREFIX_RE.sub("", content, count=1)


def _strip_think_blocks(content: str) -> str:
    """
    Remove <think>...</think> reasoning traces some models (Qwen, DeepSeek-R1
    style, etc.) inline into their content. Reasoning is never shown in the
    chat, closed or not — a <think> tag left unclosed (the model ran out of
    response length mid-thought) just means everything from that point on is
    discarded, keeping only whatever real content came before it, if any. If
    that leaves nothing, the caller's empty-response check shows a short,
    clean note instead — never the raw reasoning text.
    """
    stripped = _THINK_BLOCK_RE.sub("", content)
    match = _UNCLOSED_THINK_RE.search(stripped)
    if match:
        stripped = stripped[:match.start()]
    return stripped.strip()


def _friendly_error(raw: str) -> str:
    """
    Turn a raw provider error — often a JSON blob straight from the API, or a
    low-level exception message — into a short, plain-language sentence a
    non-technical user can actually act on, instead of a wall of JSON/stack
    trace text showing up in the chat UI.
    """
    lowered = raw.lower()

    # Providers usually return {"error": {"message": ..., "code": ...}} — pull
    # those out if present so matching isn't limited to whatever happens to be
    # in the raw text (e.g. a "code" field the message text itself doesn't repeat).
    code = ""
    message = ""
    try:
        parsed = json.loads(raw)
        err = parsed.get("error", parsed) if isinstance(parsed, dict) else {}
        if isinstance(err, dict):
            code = str(err.get("code") or "").lower()
            message = str(err.get("message") or "")
    except (json.JSONDecodeError, AttributeError, TypeError):
        pass

    haystack = f"{lowered} {code} {message.lower()}"

    if "image input is not supported" in haystack or "mmproj" in haystack:
        return ("This local model wasn't loaded with vision support. Restart llama-server with a "
                "--mmproj file for this model (or switch to a model that has one), then try again.")
    if "rate_limit" in haystack or "tokens per minute" in haystack or " tpm" in haystack or "429" in haystack:
        return "This model is getting too many requests right now. Wait a moment and try again, or send a shorter message."
    if "context_length_exceeded" in haystack or "maximum context length" in haystack:
        return "This conversation is too long for this model to handle. Try starting a new conversation, or switch to a model with a larger context window."
    if "invalid_api_key" in haystack or "incorrect api key" in haystack or "unauthorized" in haystack or "401" in haystack:
        return "This provider rejected the API key. Double-check it in Settings → API Keys."
    if "insufficient_quota" in haystack or "billing" in haystack or "quota" in haystack:
        return "This provider account is out of credits or quota. Check your billing with the provider."
    if "model_not_found" in haystack or "does not exist" in haystack or "404" in haystack:
        return "This model isn't available right now. Try selecting a different model."
    if "timeout" in haystack or "timed out" in haystack:
        return "This model took too long to respond. Try again."
    if "overloaded" in haystack or "503" in haystack or "service unavailable" in haystack:
        return "This provider's servers are overloaded right now. Try again in a moment."
    if "content_policy" in haystack or "content management policy" in haystack or "safety" in haystack:
        return "This message was blocked by the provider's content filters."

    # Nothing recognized — still never dump raw JSON/exception text into the UI.
    return "This model couldn't generate a response right now. Try again, or try a different model."


def _build_raw_context(
    all_messages: list[Message], provider: str, model: str, content_override: dict[int, str] | None = None,
) -> list[dict]:
    """
    Build conversation context for one specific model: every user turn, this model's
    own past answers presented as genuine assistant turns, and every OTHER model's
    past answers also included so a newly added panel isn't starting blind — but
    clearly attributed as generated by a different model, so the target model never
    mistakes another model's reply for something it said itself.

    content_override: {message_id: replacement_text} — used by "generate with
    sources" to swap the current turn's plain attachment text for the
    sentence-indexed transcript, without touching what's actually persisted.
    """
    content_override = content_override or {}
    context_messages = []
    for msg in all_messages:
        if msg.role == "user":
            if msg.id in content_override:
                content = content_override[msg.id]
            else:
                content = msg.content
                if msg.attached_file_name:
                    content = f"{content}\n\n[Attached file: {msg.attached_file_name}]\n{msg.attached_file_content}"
            entry = {
                "role": "user",
                "content": content,
                "turn_number": msg.turn_number,
            }
            if msg.image:
                entry["image"] = msg.image
            context_messages.append(entry)
        elif msg.role == "assistant":
            is_own_answer = msg.provider == provider and msg.model == model
            content = msg.content if is_own_answer else (
                f"[The following was generated by a different AI model ({msg.provider}/{msg.model}), "
                f"not by you. Shown for context only:]\n{msg.content}"
            )
            context_messages.append({
                "role": "assistant",
                "content": content,
                "turn_number": msg.turn_number,
            })
    return context_messages


async def _build_context_for_target(
    db: AsyncSession,
    conversation_id: int,
    all_messages: list[Message],
    provider: str,
    model: str,
    api_key: str,
    system_preface: list[dict] | None = None,
    content_override: dict[int, str] | None = None,
) -> tuple[list[dict], float]:
    """
    Same as _build_raw_context, but compacts older turns into a cached summary
    once this target's estimated usage crosses its context-window threshold,
    and prepends any preface system messages (memory facts, "generate with
    sources" instructions — identical for every target in a turn, built once
    by the caller). Returns (context_to_send, usage_pct) — usage_pct is the %
    of the model's context window that context_to_send itself is using.
    """
    context_messages = _build_raw_context(all_messages, provider, model, content_override)
    summary, kept = await maybe_compact_context(db, conversation_id, provider, model, api_key, context_messages)
    if summary:
        kept = [{
            "role": "system",
            "content": f"[Conversation summary — earlier turns compacted]\n{summary}",
        }] + kept
    if system_preface:
        kept = system_preface + kept
    return kept, estimate_usage_pct(kept, model)


async def _call_model(
    provider_name: str, model: str, api_key: str, messages: list[dict], panel_id: str | None = None,
    context_usage_pct: float | None = None,
) -> ChatResponseItem:
    """Call a single model and return the response with timing."""
    start = time.time()
    try:
        provider = get_provider(provider_name)
        result = await provider.chat(messages, model, api_key)
        elapsed_ms = (time.time() - start) * 1000
        content = _strip_think_blocks(_strip_turn_prefix(result["content"]))
        if not content.strip():
            content = _EMPTY_RESPONSE_NOTE

        return ChatResponseItem(
            provider=provider_name,
            model=model,
            panel_id=panel_id,
            content=content,
            response_time_ms=round(elapsed_ms, 1),
            token_count=result.get("token_count"),
            context_usage_pct=context_usage_pct,
        )
    except Exception as e:
        elapsed_ms = (time.time() - start) * 1000
        error_detail = str(e)
        # Try to extract more useful error info
        if hasattr(e, 'response'):
            try:
                error_detail = e.response.text
            except Exception:
                pass
        # Some exceptions (e.g. httpx.ReadTimeout) stringify to "" — never let an
        # empty error message get treated as falsy/no-error downstream.
        if not error_detail:
            error_detail = f"{type(e).__name__} after {elapsed_ms / 1000:.1f}s"
        return ChatResponseItem(
            provider=provider_name,
            model=model,
            panel_id=panel_id,
            content="",
            response_time_ms=round(elapsed_ms, 1),
            error=_friendly_error(error_detail),
            error_detail=error_detail,
        )


async def _vision_unsupported_response(provider_name: str, model: str, panel_id: str | None = None) -> ChatResponseItem:
    """Placeholder response for a target that can't handle the attached image."""
    return ChatResponseItem(
        provider=provider_name,
        model=model,
        panel_id=panel_id,
        content="",
        response_time_ms=0.0,
        error=(
            "This model doesn't support image input. Use a vision-capable model "
            "(e.g. Groq's qwen/qwen3.6-27b or meta-llama/llama-4-scout-17b-16e-instruct)."
        ),
    )


@router.post("/send", response_model=ChatResponse)
async def send_message(
    req: ChatRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Send a user message to one or more models simultaneously.
    Returns all responses along with the turn number.
    """
    # Verify conversation exists and belongs to the current user
    conv_result = await db.execute(
        select(Conversation).where(
            Conversation.id == req.conversation_id, Conversation.user_id == current_user.id
        )
    )
    conv = conv_result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Determine the next turn number
    max_turn = await db.execute(
        select(func.max(Message.turn_number)).where(
            Message.conversation_id == req.conversation_id
        )
    )
    current_max = max_turn.scalar() or 0
    turn_number = current_max + 1

    # Save the user message
    user_msg = Message(
        conversation_id=req.conversation_id,
        turn_number=turn_number,
        role="user",
        content=req.message,
        image=req.image,
        attached_file_name=req.attached_file_name,
        attached_file_content=req.attached_file_content,
    )
    db.add(user_msg)
    await db.flush()
    await db.refresh(user_msg)

    # "Generate with sources": index the attachment into IDed sentences once,
    # replacing the plain attachment text with that indexed block for every
    # target — same sentence table and citation instruction for every panel,
    # regardless of which provider/model answers.
    content_override = {}
    mom_preface = []
    valid_source_ids: set[str] = set()
    if req.with_sources and req.attached_file_content:
        indexed_block, sentence_table = build_indexed_transcript(req.attached_file_content)
        user_msg.source_sentences = json.dumps(sentence_table)
        content_override[user_msg.id] = build_mom_user_content(req.message, indexed_block)
        mom_preface = [{"role": "system", "content": MOM_SYSTEM_PROMPT}]
        valid_source_ids = {row["id"] for row in sentence_table}

    # Build conversation history for context
    history_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == req.conversation_id)
        .order_by(Message.created_at)
    )
    all_messages = history_result.scalars().all()

    # Look up API keys for each target
    api_keys = {}
    for target in req.targets:
        if target.provider not in api_keys:
            key_result = await db.execute(
                select(APIKey).where(
                    APIKey.user_id == current_user.id, APIKey.provider == target.provider
                )
            )
            key_obj = key_result.scalar_one_or_none()
            if not key_obj:
                raise HTTPException(
                    status_code=400,
                    detail=f"No API key configured for provider: {target.provider}"
                )
            api_keys[target.provider] = key_obj.api_key

    # Extraction runs once per turn (not once per panel/model) using whichever
    # model answers first — a background task, so it never adds latency to the
    # actual chat response and a failure there can never affect it.
    first_target = req.targets[0]
    background_tasks.add_task(
        extract_and_store, req.conversation_id, current_user.id,
        first_target.provider, first_target.model, api_keys[first_target.provider],
    )

    # Same facts (pinned + relevant-to-this-message) get injected into every
    # target's context this turn — computed once, not per target.
    memory_preface, injected_memories = await build_memory_preface(db, current_user.id, req.message)
    for mem in injected_memories:
        mem.uses += 1
    system_preface = memory_preface + mom_preface

    # Call all models concurrently, each with its own (possibly compacted) context.
    # A target that can't handle the attached image gets a friendly error instead of a wasted API call.
    contexts = {
        target.provider + "|" + target.model: await _build_context_for_target(
            db, req.conversation_id, all_messages, target.provider, target.model, api_keys[target.provider],
            system_preface, content_override,
        )
        for target in req.targets
    }
    tasks = [
        _vision_unsupported_response(target.provider, target.model, target.panel_id)
        if req.image and not is_vision_model(target.provider, target.model)
        else _call_model(
            target.provider,
            target.model,
            api_keys[target.provider],
            contexts[target.provider + "|" + target.model][0],
            target.panel_id,
            contexts[target.provider + "|" + target.model][1],
        )
        for target in req.targets
    ]
    responses = await asyncio.gather(*tasks)

    # Each panel's raw text gets checked against the shared sentence table —
    # same validator regardless of which model produced it. A model that
    # didn't produce the requested format at all (e.g. it got stuck narrating
    # its reasoning in plain prose and never reached real output) shows a
    # clean note instead of that raw, unfinished text.
    if req.with_sources and valid_source_ids:
        for resp in responses:
            if resp.error:
                continue
            parsed = parse_and_validate_mom(resp.content, valid_source_ids)
            if parsed is not None:
                resp.content = json.dumps(parsed)
                resp.content_format = "mom_json"
            else:
                resp.content = _MOM_NO_STRUCTURED_OUTPUT_NOTE

    # Save assistant responses to database
    for resp in responses:
        if not resp.error:
            assistant_msg = Message(
                conversation_id=req.conversation_id,
                turn_number=turn_number,
                role="assistant",
                content=resp.content,
                provider=resp.provider,
                model=resp.model,
                panel_id=resp.panel_id,
                response_time_ms=resp.response_time_ms,
                token_count=resp.token_count,
                context_usage_pct=resp.context_usage_pct,
                content_format=resp.content_format,
            )
            db.add(assistant_msg)

    # Update conversation title from first user message if still "New Chat"
    if conv.title == "New Chat" and turn_number == 1:
        # Use first 60 chars of the message as the title
        conv.title = req.message[:60] + ("..." if len(req.message) > 60 else "")

    await db.flush()

    user_msg_response = MessageResponse(
        id=user_msg.id,
        conversation_id=user_msg.conversation_id,
        turn_number=user_msg.turn_number,
        role=user_msg.role,
        content=user_msg.content,
        image=user_msg.image,
        source_sentences=user_msg.source_sentences,
        attached_file_name=user_msg.attached_file_name,
        attached_file_content=user_msg.attached_file_content,
        created_at=user_msg.created_at,
    )

    return ChatResponse(
        turn_number=turn_number,
        user_message=user_msg_response,
        responses=list(responses),
    )


class _ThinkTagFilter:
    """
    Strips <think>...</think> reasoning out of a live stream of text deltas,
    as they arrive — not just from the final accumulated text. Without this,
    a model's raw reasoning streams straight to the client in real time (often
    the bulk of a slow response), and only gets cleaned up once the whole
    response finishes; for a model that thinks for a long time, that means
    watching nothing but raw reasoning for most of the wait.

    Handles <think>/</think> landing split across separate chunks by holding
    back a small tail of the buffer whenever it might be an in-progress tag.
    """
    OPEN_TAG = "<think>"
    CLOSE_TAG = "</think>"

    def __init__(self):
        self._buffer = ""
        self._in_think = False

    def feed(self, chunk: str) -> str:
        """Feed a raw chunk, return whatever visible (non-reasoning) text is
        now safe to emit — may be "" if nothing new is visible yet."""
        self._buffer += chunk
        visible = ""
        while True:
            tag = self.CLOSE_TAG if self._in_think else self.OPEN_TAG
            idx = self._buffer.find(tag)
            if idx == -1:
                # Tag not found yet — it might be starting at the very end of
                # the buffer, split across a chunk boundary. Hold back just
                # enough characters to safely catch that next time, and only
                # emit/discard the rest.
                safe_len = max(0, len(self._buffer) - (len(tag) - 1))
                if not self._in_think:
                    visible += self._buffer[:safe_len]
                self._buffer = self._buffer[safe_len:]
                break
            if not self._in_think:
                visible += self._buffer[:idx]
            self._buffer = self._buffer[idx + len(tag):]
            self._in_think = not self._in_think
        return visible

    def flush(self) -> str:
        """Call once the stream ends: an unclosed <think> at end-of-stream
        means whatever's left was never-finished reasoning — discard it.
        Otherwise it's genuine trailing content that was just being held back
        as a possible partial tag — emit it."""
        remaining = "" if self._in_think else self._buffer
        self._buffer = ""
        return remaining


async def _stream_target(
    queue: asyncio.Queue, idx: int, provider_name: str, model: str, api_key: str, messages: list[dict],
    panel_id: str | None = None, context_usage_pct: float | None = None,
):
    """Stream one model's response, pushing delta/done/error events onto the shared queue."""
    start = time.time()
    accumulated = ""
    usage_sink: dict = {}
    think_filter = _ThinkTagFilter()
    try:
        provider = get_provider(provider_name)
        async for raw_delta in provider.chat_stream(messages, model, api_key, usage_sink=usage_sink):
            visible = think_filter.feed(raw_delta)
            if not visible:
                continue
            accumulated += visible
            await queue.put({
                "idx": idx, "provider": provider_name, "model": model, "panel_id": panel_id,
                "type": "delta", "content": visible,
            })
        trailing = think_filter.flush()
        if trailing:
            accumulated += trailing
            await queue.put({
                "idx": idx, "provider": provider_name, "model": model, "panel_id": panel_id,
                "type": "delta", "content": trailing,
            })
        elapsed_ms = round((time.time() - start) * 1000, 1)
        cleaned = _strip_think_blocks(_strip_turn_prefix(accumulated))
        if not cleaned.strip():
            cleaned = _EMPTY_RESPONSE_NOTE
        await queue.put({
            "idx": idx, "provider": provider_name, "model": model, "panel_id": panel_id, "type": "done",
            "content": cleaned, "response_time_ms": elapsed_ms, "token_count": usage_sink.get("total_tokens"),
            "context_usage_pct": context_usage_pct,
        })
    except Exception as e:
        elapsed_ms = round((time.time() - start) * 1000, 1)
        error_detail = str(e)
        if hasattr(e, "response"):
            try:
                error_detail = e.response.text
            except Exception:
                pass
        if not error_detail:
            error_detail = f"{type(e).__name__} after {elapsed_ms / 1000:.1f}s"
        await queue.put({
            "idx": idx, "provider": provider_name, "model": model, "panel_id": panel_id, "type": "error",
            "error": _friendly_error(error_detail), "error_detail": error_detail, "response_time_ms": elapsed_ms,
        })


@router.post("/send-stream")
async def send_message_stream(
    req: ChatRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Same as /send, but streams each model's response as it's generated over
    Server-Sent Events instead of waiting for every model to fully finish.
    """
    conv_result = await db.execute(
        select(Conversation).where(
            Conversation.id == req.conversation_id, Conversation.user_id == current_user.id
        )
    )
    conv = conv_result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    max_turn = await db.execute(
        select(func.max(Message.turn_number)).where(Message.conversation_id == req.conversation_id)
    )
    current_max = max_turn.scalar() or 0
    turn_number = current_max + 1

    user_msg = Message(
        conversation_id=req.conversation_id,
        turn_number=turn_number,
        role="user",
        content=req.message,
        image=req.image,
        attached_file_name=req.attached_file_name,
        attached_file_content=req.attached_file_content,
    )
    db.add(user_msg)
    await db.flush()
    await db.refresh(user_msg)

    # "Generate with sources": index the attachment into IDed sentences once,
    # replacing the plain attachment text with that indexed block for every
    # target — same sentence table and citation instruction for every panel,
    # regardless of which provider/model answers.
    content_override = {}
    mom_preface = []
    valid_source_ids: set[str] = set()
    if req.with_sources and req.attached_file_content:
        indexed_block, sentence_table = build_indexed_transcript(req.attached_file_content)
        user_msg.source_sentences = json.dumps(sentence_table)
        content_override[user_msg.id] = build_mom_user_content(req.message, indexed_block)
        mom_preface = [{"role": "system", "content": MOM_SYSTEM_PROMPT}]
        valid_source_ids = {row["id"] for row in sentence_table}

    history_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == req.conversation_id)
        .order_by(Message.created_at)
    )
    all_messages = history_result.scalars().all()

    api_keys = {}
    for target in req.targets:
        if target.provider not in api_keys:
            key_result = await db.execute(
                select(APIKey).where(
                    APIKey.user_id == current_user.id, APIKey.provider == target.provider
                )
            )
            key_obj = key_result.scalar_one_or_none()
            if not key_obj:
                raise HTTPException(
                    status_code=400,
                    detail=f"No API key configured for provider: {target.provider}"
                )
            api_keys[target.provider] = key_obj.api_key

    # Extraction runs once per turn (not once per panel/model) using whichever
    # model answers first — a background task, so it never adds latency to the
    # actual chat response and a failure there can never affect it.
    first_target = req.targets[0]
    background_tasks.add_task(
        extract_and_store, req.conversation_id, current_user.id,
        first_target.provider, first_target.model, api_keys[first_target.provider],
    )

    # Same facts (pinned + relevant-to-this-message) get injected into every
    # target's context this turn — computed once, not per target. Must happen
    # here (needs the DB) before the request-scoped session below is torn down.
    memory_preface, injected_memories = await build_memory_preface(db, current_user.id, req.message)
    for mem in injected_memories:
        mem.uses += 1
    system_preface = memory_preface + mom_preface

    # Everything the generator needs, captured as plain data — the `db` session
    # injected above is torn down once this function returns, before the
    # streamed body actually runs, so it can't be used inside the generator.
    # Compaction (which needs the DB) must happen here, before that teardown.
    context_by_target = [
        await _build_context_for_target(
            db, req.conversation_id, all_messages, t.provider, t.model, api_keys[t.provider],
            system_preface, content_override,
        )
        for t in req.targets
    ]
    targets = list(req.targets)
    conversation_id = req.conversation_id
    image = req.image
    with_sources = req.with_sources
    user_message_payload = {
        "id": user_msg.id,
        "conversation_id": user_msg.conversation_id,
        "turn_number": user_msg.turn_number,
        "role": user_msg.role,
        "content": user_msg.content,
        "image": user_msg.image,
        "attached_file_name": user_msg.attached_file_name,
        "attached_file_content": user_msg.attached_file_content,
        "source_sentences": user_msg.source_sentences,
        "created_at": user_msg.created_at.isoformat(),
    }
    should_set_title = conv.title == "New Chat" and turn_number == 1
    title_text = req.message[:60] + ("..." if len(req.message) > 60 else "")

    async def event_generator():
        yield f"data: {json.dumps({'type': 'start', 'turn_number': turn_number, 'user_message': user_message_payload})}\n\n"

        queue: asyncio.Queue = asyncio.Queue()
        tasks = []
        for idx, target in enumerate(targets):
            if image and not is_vision_model(target.provider, target.model):
                await queue.put({
                    "idx": idx, "provider": target.provider, "model": target.model, "panel_id": target.panel_id,
                    "type": "error",
                    "error": (
                        "This model doesn't support image input. Use a vision-capable model "
                        "(e.g. Groq's qwen/qwen3.6-27b or meta-llama/llama-4-scout-17b-16e-instruct)."
                    ),
                    "response_time_ms": 0.0,
                })
                continue
            tasks.append(asyncio.create_task(
                _stream_target(
                    queue, idx, target.provider, target.model, api_keys[target.provider], context_by_target[idx][0],
                    target.panel_id, context_by_target[idx][1],
                )
            ))

        remaining = len(targets)
        to_save = []
        while remaining > 0:
            item = await queue.get()
            if item["type"] == "done" and with_sources and valid_source_ids:
                # Same shared validator regardless of which model produced this
                # panel's response — dropped in before the client ever sees it,
                # so streamed and non-streamed panels behave identically.
                parsed = parse_and_validate_mom(item["content"], valid_source_ids)
                if parsed is not None:
                    item["content"] = json.dumps(parsed)
                    item["content_format"] = "mom_json"
                else:
                    item["content"] = _MOM_NO_STRUCTURED_OUTPUT_NOTE
            yield f"data: {json.dumps(item)}\n\n"
            if item["type"] in ("done", "error"):
                remaining -= 1
                if item["type"] == "done":
                    to_save.append(item)

        if tasks:
            await asyncio.gather(*tasks)

        # Persist with a fresh session — the request-scoped one is already closed.
        # A slow response (some models take minutes) can outlive the conversation
        # it belongs to, e.g. the user deletes it mid-generation — the client
        # already received the content live over SSE either way, so a failure
        # here just means it doesn't get saved, not an unhandled crash.
        try:
            async with async_session() as session:
                for item in to_save:
                    session.add(Message(
                        conversation_id=conversation_id,
                        turn_number=turn_number,
                        role="assistant",
                        content=item["content"],
                        provider=item["provider"],
                        model=item["model"],
                        panel_id=item.get("panel_id"),
                        response_time_ms=item["response_time_ms"],
                        token_count=item.get("token_count"),
                        context_usage_pct=item.get("context_usage_pct"),
                        content_format=item.get("content_format"),
                    ))
                if should_set_title:
                    title_result = await session.execute(select(Conversation).where(Conversation.id == conversation_id))
                    title_conv = title_result.scalar_one_or_none()
                    if title_conv:
                        title_conv.title = title_text
                await session.commit()
        except Exception:
            print(f"[send-stream] Failed to persist turn {turn_number} for conversation {conversation_id} "
                  f"(it may have been deleted while this response was still generating):")
            traceback.print_exc()

        yield f"data: {json.dumps({'type': 'end'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        background=background_tasks,
    )


@router.post("/retry", response_model=ChatResponseItem)
async def retry_message(
    req: RetryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Regenerate a single model's response for a past turn, without touching
    any other panel's answer for that turn.
    """
    conv_result = await db.execute(
        select(Conversation).where(
            Conversation.id == req.conversation_id, Conversation.user_id == current_user.id
        )
    )
    if not conv_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Conversation not found")

    key_result = await db.execute(
        select(APIKey).where(APIKey.user_id == current_user.id, APIKey.provider == req.provider)
    )
    key_obj = key_result.scalar_one_or_none()
    if not key_obj:
        raise HTTPException(status_code=400, detail=f"No API key configured for provider: {req.provider}")

    history_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == req.conversation_id)
        .order_by(Message.created_at)
    )
    all_messages = history_result.scalars().all()

    user_msg_for_turn = next(
        (m for m in all_messages if m.role == "user" and m.turn_number == req.turn_number), None
    )
    if not user_msg_for_turn:
        raise HTTPException(status_code=404, detail="That turn no longer exists")

    # Prefer matching by panel identity — provider+model alone is ambiguous once
    # two panels have used the same model. Falls back to provider+model for
    # messages saved before panel_id existed, or if the caller doesn't send one.
    candidates = [
        m for m in all_messages
        if m.role == "assistant" and m.turn_number == req.turn_number
        and m.provider == req.provider and m.model == req.model
    ]
    if req.panel_id:
        existing_assistant = next((m for m in candidates if m.panel_id == req.panel_id), None) \
            or next((m for m in candidates if not m.panel_id), None)
    else:
        existing_assistant = candidates[0] if candidates else None

    # Context as of this turn only — excluding the stale answer we're about to replace.
    context_source = [
        m for m in all_messages
        if m.turn_number <= req.turn_number and m is not existing_assistant
    ]
    # No new extraction trigger here (retry doesn't add a new user turn), but the
    # regenerated answer should still see the same memory context that turn's
    # original question would have.
    memory_preface, injected_memories = await build_memory_preface(
        db, current_user.id, user_msg_for_turn.content
    )
    for mem in injected_memories:
        mem.uses += 1
    context_messages, usage_pct = await _build_context_for_target(
        db, req.conversation_id, context_source, req.provider, req.model, key_obj.api_key, memory_preface,
    )

    if user_msg_for_turn.image and not is_vision_model(req.provider, req.model):
        return await _vision_unsupported_response(req.provider, req.model, req.panel_id)

    resp = await _call_model(req.provider, req.model, key_obj.api_key, context_messages, req.panel_id, usage_pct)

    if not resp.error:
        if existing_assistant:
            existing_assistant.content = resp.content
            existing_assistant.panel_id = req.panel_id or existing_assistant.panel_id
            existing_assistant.response_time_ms = resp.response_time_ms
            existing_assistant.token_count = resp.token_count
            existing_assistant.context_usage_pct = resp.context_usage_pct
        else:
            db.add(Message(
                conversation_id=req.conversation_id,
                turn_number=req.turn_number,
                role="assistant",
                provider=req.provider,
                model=req.model,
                panel_id=req.panel_id,
                content=resp.content,
                response_time_ms=resp.response_time_ms,
                token_count=resp.token_count,
                context_usage_pct=resp.context_usage_pct,
            ))
        await db.flush()

    return resp


@router.post("/edit", response_model=ChatResponse)
async def edit_message(
    req: EditMessageRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Edit a past user message and regenerate responses for that turn. Everything
    after that turn (including the stale answers to the pre-edit question) is
    discarded, since it was all built on a question that no longer exists.
    """
    conv_result = await db.execute(
        select(Conversation).where(
            Conversation.id == req.conversation_id, Conversation.user_id == current_user.id
        )
    )
    conv = conv_result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    msg_result = await db.execute(
        select(Message).where(Message.id == req.message_id, Message.conversation_id == req.conversation_id)
    )
    user_msg = msg_result.scalar_one_or_none()
    if not user_msg or user_msg.role != "user":
        raise HTTPException(status_code=404, detail="Message not found")

    turn_number = user_msg.turn_number
    user_msg.content = req.content
    user_msg.image = req.image
    user_msg.attached_file_name = req.attached_file_name
    user_msg.attached_file_content = req.attached_file_content
    await db.flush()

    # Discard everything built on the pre-edit question: this turn's old
    # answers, plus every later turn (their context is now stale).
    await db.execute(
        delete(Message).where(
            Message.conversation_id == req.conversation_id,
            Message.turn_number >= turn_number,
            Message.id != user_msg.id,
        )
    )
    await db.flush()

    history_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == req.conversation_id)
        .order_by(Message.created_at)
    )
    all_messages = history_result.scalars().all()

    api_keys = {}
    for target in req.targets:
        if target.provider not in api_keys:
            key_result = await db.execute(
                select(APIKey).where(
                    APIKey.user_id == current_user.id, APIKey.provider == target.provider
                )
            )
            key_obj = key_result.scalar_one_or_none()
            if not key_obj:
                raise HTTPException(
                    status_code=400,
                    detail=f"No API key configured for provider: {target.provider}"
                )
            api_keys[target.provider] = key_obj.api_key

    # An edit is a new statement from the user, same as a fresh /send — extract
    # from it too.
    first_target = req.targets[0]
    background_tasks.add_task(
        extract_and_store, req.conversation_id, current_user.id,
        first_target.provider, first_target.model, api_keys[first_target.provider],
    )

    memory_preface, injected_memories = await build_memory_preface(db, current_user.id, req.content)
    for mem in injected_memories:
        mem.uses += 1

    contexts = {
        target.provider + "|" + target.model: await _build_context_for_target(
            db, req.conversation_id, all_messages, target.provider, target.model, api_keys[target.provider],
            memory_preface,
        )
        for target in req.targets
    }
    tasks = [
        _vision_unsupported_response(target.provider, target.model, target.panel_id)
        if req.image and not is_vision_model(target.provider, target.model)
        else _call_model(
            target.provider,
            target.model,
            api_keys[target.provider],
            contexts[target.provider + "|" + target.model][0],
            target.panel_id,
            contexts[target.provider + "|" + target.model][1],
        )
        for target in req.targets
    ]
    responses = await asyncio.gather(*tasks)

    for resp in responses:
        if not resp.error:
            db.add(Message(
                conversation_id=req.conversation_id,
                turn_number=turn_number,
                role="assistant",
                content=resp.content,
                provider=resp.provider,
                model=resp.model,
                panel_id=resp.panel_id,
                response_time_ms=resp.response_time_ms,
                token_count=resp.token_count,
                context_usage_pct=resp.context_usage_pct,
            ))

    await db.flush()
    await db.refresh(user_msg)

    user_msg_response = MessageResponse(
        id=user_msg.id,
        conversation_id=user_msg.conversation_id,
        turn_number=user_msg.turn_number,
        role=user_msg.role,
        content=user_msg.content,
        image=user_msg.image,
        attached_file_name=user_msg.attached_file_name,
        attached_file_content=user_msg.attached_file_content,
        created_at=user_msg.created_at,
    )

    return ChatResponse(
        turn_number=turn_number,
        user_message=user_msg_response,
        responses=list(responses),
    )


@router.get("/history/{conversation_id}", response_model=list[MessageResponse])
async def get_history(
    conversation_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get full message history for a conversation the current user owns."""
    conv_result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id, Conversation.user_id == current_user.id
        )
    )
    if not conv_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Conversation not found")

    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
    )
    messages = result.scalars().all()
    return messages


@router.get("/compactions/{conversation_id}", response_model=list[CompactionResponse])
async def get_compactions(
    conversation_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Which (provider, model) targets in this conversation have had their history
    compacted, and up through which turn — used by the frontend to place a
    "context compacted" divider in each affected panel.
    """
    conv_result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id, Conversation.user_id == current_user.id
        )
    )
    if not conv_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Conversation not found")

    result = await db.execute(
        select(ContextCompaction).where(ContextCompaction.conversation_id == conversation_id)
    )
    return result.scalars().all()
