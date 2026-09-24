"""
Background memory-extraction pipeline: after a user sends a message, this
extracts durable personal facts (via regex + a low-temperature LLM call),
dedupes them against what's already known, stores new ones, and periodically
audits the whole set to merge/clean it up. Runs as a FastAPI BackgroundTask —
fired once per turn, never blocks or affects the actual chat response, and
must never raise (a failure here should be invisible to the user).

See memory_prompts.py for the exact wording sent to the LLM, and
memory_injection.py for how stored memories get fed back into future prompts.
"""
import datetime
import hashlib
import json
import re
import traceback
from sqlalchemy import select
from backend.database import async_session
from backend.models import Memory, MemoryAuditState, Message
from backend.providers import get_provider
from backend.memory_prompts import (
    EXTRACTION_SYSTEM_PROMPT, AUDIT_SYSTEM_PROMPT, VALID_CATEGORIES, AUTO_PIN_CATEGORIES,
)
from backend.text_cleanup import strip_think_blocks

JACCARD_THRESHOLD = 0.6
AUDIT_EVERY_N_MEMORIES = 5
AUDIT_REJECT_IF_REMOVES_OVER = 0.5  # reject the whole audit result if it deletes >50%

# The first active model does the extraction; the second (if there is one) is
# only a backup if the first errors. If both fail, nothing is written this turn.
MAX_EXTRACTION_MODELS = 2
# Headroom for models that emit a reasoning preamble before the JSON — 500 was
# enough for the JSON alone but not for a model that thinks first.
EXTRACTION_MAX_TOKENS = 1500
# Only the user's own short statements matter for extraction; a long assistant
# answer or an attached transcript just bloats the prompt (and can trip
# provider rate limits, which would force a needless fallback).
MAX_TRANSCRIPT_CHARS_PER_MESSAGE = 1500

_WORD_RE = re.compile(r"[a-z0-9']+")

# ── Regex fallback extractor (Stage 1B) — no LLM needed, runs on every turn ──
_REGEX_RULES = [
    (re.compile(r"\bmy name is ([A-Za-z][\w .'-]{0,40})", re.IGNORECASE), "identity", "User's name is {}."),
    (re.compile(r"\bcall me ([A-Za-z][\w .'-]{0,40})", re.IGNORECASE), "identity", "User wants to be called {}."),
    (re.compile(r"\bi live in ([A-Za-z][\w .'-]{0,40})", re.IGNORECASE), "identity", "User lives in {}."),
    (re.compile(r"\bi(?:'m| am) from ([A-Za-z][\w .'-]{0,40})", re.IGNORECASE), "identity", "User lives in {}."),
    (re.compile(r"\bi (?:prefer|like) ([A-Za-z][\w .'-]{0,40})", re.IGNORECASE), "preference", "User prefers {}."),
    (re.compile(r"\bi (?:love|hate) ([A-Za-z][\w .'-]{0,40})", re.IGNORECASE), "preference", "User prefers {}."),
    (re.compile(r"\bi want to visit ([A-Za-z][\w .'-]{0,40})", re.IGNORECASE), "goal", "User wants to visit {}."),
]


def _regex_extract(text: str) -> list[dict]:
    """Cheap, deterministic fact extraction — survives even if the LLM call fails."""
    if not text:
        return []
    results = []
    for pattern, category, template in _REGEX_RULES:
        match = pattern.search(text)
        if not match:
            continue
        # Cut the capture at the first clause boundary so a whole run-on
        # sentence doesn't get swept into the fact.
        captured = re.split(r"[.,!?;\n]", match.group(1))[0].strip()
        if not captured:
            continue
        value = captured.title() if category == "identity" else captured
        results.append({"text": template.format(value), "category": category})
        if len(results) >= 2:
            break
    return results


def _parse_json_array(raw: str) -> list | None:
    """
    Defensively parse an LLM's JSON array response. Returns the list (which may
    legitimately be empty — "nothing durable to extract"), or None if the
    response wasn't a usable JSON array at all — callers must treat those two
    differently. Reasoning traces (<think>...</think>, including the empty
    shell models emit even with thinking disabled) and markdown fences are
    stripped first — parsing the raw string used to fail on the very common
    "<think>\\n\\n</think>\\n\\n[...]" shape, silently discarding good output.
    """
    text = strip_think_blocks(raw or "")
    if text.startswith("```"):
        text = text.strip("`")
        if text[:4].lower() == "json":
            text = text[4:]
        text = text.strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, list) else None


async def _llm_extract(
    transcript: list[dict], provider_name: str, model: str, api_key: str
) -> list[dict] | None:
    """
    LLM extractor (Stage 1A). Returns the candidate facts (possibly an empty
    list — the model looked and found nothing durable, which is a success), or
    None if this model failed: the call errored, or what came back wasn't
    parseable. The caller falls back to the next model on None. Failures are
    logged — they used to be swallowed silently, which made "memory isn't
    working" impossible to diagnose.
    """
    label = f"{provider_name}/{model}"
    try:
        provider = get_provider(provider_name)
        # One user message holding the conversation as plain text. Passing the
        # turns as real chat messages made models answer the last one (e.g.
        # "Nice to meet you, Zorlak!") instead of returning the JSON array.
        conversation_text = "\n\n".join(
            f"{m['role'].upper()}: {m['content']}" for m in transcript
        )
        messages = [
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Extract durable facts about the USER from the conversation below. "
                    "Do not reply to it. Respond with ONLY the JSON array.\n\n"
                    f"<conversation>\n{conversation_text}\n</conversation>"
                ),
            },
        ]
        result = await provider.chat(
            messages, model, api_key, max_tokens=EXTRACTION_MAX_TOKENS, temperature=0.1
        )
    except Exception as e:
        print(f"[memory] extraction call failed on {label}: {type(e).__name__}: {e}")
        return None

    content = result.get("content", "")
    parsed = _parse_json_array(content)
    if parsed is None:
        print(f"[memory] extraction on {label} returned unparseable output: {content[:200]!r}")
        return None
    return [c for c in parsed if isinstance(c, dict) and c.get("text")]


def _tokenize(text: str) -> set[str]:
    return set(_WORD_RE.findall(text.lower()))


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _is_duplicate(candidate_text: str, existing: list[Memory]) -> bool:
    """Stage 2: exact match, then Jaccard fuzzy match — no vector store in this build."""
    candidate_lower = candidate_text.strip().lower()
    candidate_tokens = _tokenize(candidate_text)
    for m in existing:
        if m.text.strip().lower() == candidate_lower:
            return True
        if _jaccard(candidate_tokens, _tokenize(m.text)) >= JACCARD_THRESHOLD:
            return True
    return False


async def _store_candidate(db, user_id: int, candidate: dict, existing: list[Memory]) -> Memory | None:
    """Stage 3: dedup-check then store. Appends to `existing` so later candidates
    in the same batch also dedup against anything just added."""
    text = str(candidate.get("text") or "").strip()
    if not text or len(text) > 300:  # sanity cap — a "fact" that long isn't one
        return None
    if _is_duplicate(text, existing):
        return None

    category = candidate.get("category")
    if category not in VALID_CATEGORIES:
        category = "fact"

    mem = Memory(
        user_id=user_id,
        text=text,
        category=category,
        pinned=category in AUTO_PIN_CATEGORIES,
        source="auto",
    )
    db.add(mem)
    await db.flush()
    existing.append(mem)
    return mem


def _fingerprint(memories: list[Memory]) -> str:
    payload = sorted((m.id, m.text, m.category) for m in memories)
    return hashlib.sha256(json.dumps(payload).encode()).hexdigest()


async def _run_audit(db, user_id: int, provider_name: str, model: str, api_key: str) -> None:
    """Stage 4: periodic curation. Conservative — only merges true duplicates,
    guarded by a fingerprint skip and a 50%-deletion safety net."""
    result = await db.execute(select(Memory).where(Memory.user_id == user_id))
    memories = result.scalars().all()
    if not memories:
        return

    fingerprint = _fingerprint(memories)
    state = await db.get(MemoryAuditState, user_id)
    if state and state.fingerprint == fingerprint:
        return  # nothing's changed since the last audit — skip the LLM call entirely

    payload = [{"id": m.id, "text": m.text, "category": m.category} for m in memories]
    curated = None
    try:
        provider = get_provider(provider_name)
        result = await provider.chat(
            [
                {"role": "system", "content": AUDIT_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload)},
            ],
            model, api_key, max_tokens=16384, temperature=0.1,
        )
        curated = _parse_json_array(result.get("content", ""))
    except Exception:
        curated = None

    if curated and len(curated) < len(memories) * AUDIT_REJECT_IF_REMOVES_OVER:
        # Removed more than half the entries — almost certainly a hallucinated
        # or truncated response. Reject it entirely and keep the originals.
        curated = None

    if curated:
        by_id = {m.id: m for m in memories}
        keep_ids = set()
        for entry in curated:
            if not isinstance(entry, dict):
                continue
            try:
                mem_id = int(entry.get("id"))
            except (TypeError, ValueError):
                continue
            mem = by_id.get(mem_id)
            if not mem:
                continue
            keep_ids.add(mem_id)
            new_text = str(entry.get("text") or "").strip()
            if new_text:
                mem.text = new_text
            new_category = entry.get("category")
            if new_category in VALID_CATEGORIES:
                mem.category = new_category
        for mem in memories:
            if mem.id not in keep_ids:
                await db.delete(mem)
        await db.flush()

        surviving = await db.execute(select(Memory).where(Memory.user_id == user_id))
        fingerprint = _fingerprint(surviving.scalars().all())

    if state:
        state.fingerprint = fingerprint
        state.memories_since_audit = 0
        state.audited_at = datetime.datetime.utcnow()
    else:
        db.add(MemoryAuditState(
            user_id=user_id, fingerprint=fingerprint, memories_since_audit=0,
            audited_at=datetime.datetime.utcnow(),
        ))


async def extract_and_store(
    conversation_id: int, user_id: int, models: list[tuple[str, str, str]]
) -> None:
    """
    Entry point, fired once per turn right after the user's message is saved
    (not once per panel/model that answers it). Opens its own DB session since
    this runs as a background task after the request that triggered it has
    already returned.

    models: [(provider, model, api_key), ...] — every active model, in panel
    order. The first does the extraction; if it errors, the second is tried as
    a backup; if that fails too (or there was only one), nothing is written for
    this turn — no partial/regex-only results either.
    """
    try:
        # Same model picked in two panels would just repeat the same failure.
        unique_models = []
        seen = set()
        for provider, model, api_key in models:
            if (provider, model) not in seen:
                seen.add((provider, model))
                unique_models.append((provider, model, api_key))
        unique_models = unique_models[:MAX_EXTRACTION_MODELS]
        if not unique_models:
            return

        async with async_session() as db:
            history_result = await db.execute(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at.desc())
                .limit(6)
            )
            recent = list(reversed(history_result.scalars().all()))
            if not recent:
                return

            latest_user_msg = next((m for m in reversed(recent) if m.role == "user"), None)
            if not latest_user_msg or not latest_user_msg.content:
                return

            # Text only — images/attachments are stripped, just the conversational
            # turns, each capped so a long answer/transcript can't bloat the prompt.
            transcript = [
                {"role": m.role, "content": m.content[:MAX_TRANSCRIPT_CHARS_PER_MESSAGE]}
                for m in recent if m.content
            ]

            llm_candidates = None
            used_model = None
            for provider, model, api_key in unique_models:
                llm_candidates = await _llm_extract(transcript, provider, model, api_key)
                if llm_candidates is not None:
                    used_model = (provider, model, api_key)
                    break
                print(f"[memory] {provider}/{model} failed"
                      + (" — trying backup model" if (provider, model, api_key) != unique_models[-1] else ""))

            if used_model is None:
                print("[memory] every extraction model failed — nothing written this turn")
                return

            # The LLM prompt asks for max 2 facts but models don't always obey.
            candidates = _regex_extract(latest_user_msg.content) + llm_candidates[:2]
            if not candidates:
                return

            existing_result = await db.execute(select(Memory).where(Memory.user_id == user_id))
            existing = list(existing_result.scalars().all())

            stored_any = False
            for candidate in candidates:  # regex(2) + LLM(2) max per turn
                mem = await _store_candidate(db, user_id, candidate, existing)
                if mem:
                    stored_any = True

            if not stored_any:
                await db.commit()
                return

            state = await db.get(MemoryAuditState, user_id)
            if state:
                state.memories_since_audit += 1
            else:
                state = MemoryAuditState(user_id=user_id, memories_since_audit=1)
                db.add(state)
            await db.flush()

            if state.memories_since_audit >= AUDIT_EVERY_N_MEMORIES:
                # Reuse the model that just proved it works this turn.
                await _run_audit(db, user_id, *used_model)

            await db.commit()
    except Exception:
        # Background task — a memory-pipeline failure must never surface to the
        # user or affect the chat. Log server-side only.
        traceback.print_exc()
