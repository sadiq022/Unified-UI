import asyncio
import re
import time
import traceback
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from backend.database import get_db
from backend.models import APIKey, Conversation, Message
from backend.schemas import ChatRequest, ChatResponse, ChatResponseItem, MessageResponse
from backend.providers import get_provider, is_vision_model

router = APIRouter(prefix="/api/chat", tags=["Chat"])

_TURN_PREFIX_RE = re.compile(r"^\s*\[Turn \d+\]\s*", re.IGNORECASE)
_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)
_UNCLOSED_THINK_RE = re.compile(r"<think>.*", re.IGNORECASE | re.DOTALL)


def _strip_turn_prefix(content: str) -> str:
    """Strip a leaked '[Turn N] ' marker some models echo back from the prompt."""
    return _TURN_PREFIX_RE.sub("", content, count=1)


def _strip_think_blocks(content: str) -> str:
    """Remove <think>...</think> reasoning traces some models inline into their content."""
    stripped = _THINK_BLOCK_RE.sub("", content)
    stripped = _UNCLOSED_THINK_RE.sub("", stripped)  # handle a truncated, never-closed tag
    return stripped.strip()


def _build_context_for_target(all_messages: list[Message], provider: str, model: str) -> list[dict]:
    """
    Build conversation context for one specific model: every user turn, plus only
    this model's own past assistant answers. Other panels' answers are never
    included — a model must never be shown a reply attributed to "assistant"
    that it didn't actually generate, since that fabricates a false memory and
    can bias its style/reasoning off another model's answer.
    """
    context_messages = []
    for msg in all_messages:
        if msg.role == "user":
            entry = {
                "role": "user",
                "content": msg.content,
                "turn_number": msg.turn_number,
            }
            if msg.image:
                entry["image"] = msg.image
            context_messages.append(entry)
        elif msg.role == "assistant" and msg.provider == provider and msg.model == model:
            context_messages.append({
                "role": "assistant",
                "content": msg.content,
                "turn_number": msg.turn_number,
            })
    return context_messages


async def _call_model(provider_name: str, model: str, api_key: str, messages: list[dict]) -> ChatResponseItem:
    """Call a single model and return the response with timing."""
    start = time.time()
    try:
        provider = get_provider(provider_name)
        result = await provider.chat(messages, model, api_key)
        elapsed_ms = (time.time() - start) * 1000

        return ChatResponseItem(
            provider=provider_name,
            model=model,
            content=_strip_think_blocks(_strip_turn_prefix(result["content"])),
            response_time_ms=round(elapsed_ms, 1),
            token_count=result.get("token_count"),
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
            content="",
            response_time_ms=round(elapsed_ms, 1),
            error=error_detail,
        )


async def _vision_unsupported_response(provider_name: str, model: str) -> ChatResponseItem:
    """Placeholder response for a target that can't handle the attached image."""
    return ChatResponseItem(
        provider=provider_name,
        model=model,
        content="",
        response_time_ms=0.0,
        error=(
            "This model doesn't support image input. Use a vision-capable model "
            "(e.g. Groq's qwen/qwen3.6-27b or meta-llama/llama-4-scout-17b-16e-instruct)."
        ),
    )


@router.post("/send", response_model=ChatResponse)
async def send_message(req: ChatRequest, db: AsyncSession = Depends(get_db)):
    """
    Send a user message to one or more models simultaneously.
    Returns all responses along with the turn number.
    """
    # Verify conversation exists
    conv_result = await db.execute(
        select(Conversation).where(Conversation.id == req.conversation_id)
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
    )
    db.add(user_msg)
    await db.flush()
    await db.refresh(user_msg)

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
                select(APIKey).where(APIKey.provider == target.provider)
            )
            key_obj = key_result.scalar_one_or_none()
            if not key_obj:
                raise HTTPException(
                    status_code=400,
                    detail=f"No API key configured for provider: {target.provider}"
                )
            api_keys[target.provider] = key_obj.api_key

    # Call all models concurrently, each with its own context (its own past answers only).
    # A target that can't handle the attached image gets a friendly error instead of a wasted API call.
    tasks = [
        _vision_unsupported_response(target.provider, target.model)
        if req.image and not is_vision_model(target.provider, target.model)
        else _call_model(
            target.provider,
            target.model,
            api_keys[target.provider],
            _build_context_for_target(all_messages, target.provider, target.model),
        )
        for target in req.targets
    ]
    responses = await asyncio.gather(*tasks)

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
                response_time_ms=resp.response_time_ms,
                token_count=resp.token_count,
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
        created_at=user_msg.created_at,
    )

    return ChatResponse(
        turn_number=turn_number,
        user_message=user_msg_response,
        responses=list(responses),
    )


@router.get("/history/{conversation_id}", response_model=list[MessageResponse])
async def get_history(conversation_id: int, db: AsyncSession = Depends(get_db)):
    """Get full message history for a conversation."""
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
    )
    messages = result.scalars().all()
    return messages
