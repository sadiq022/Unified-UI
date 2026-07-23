from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models import ContextCompaction
from backend.providers import get_context_length, get_provider

# Once a target's estimated context usage crosses this fraction of its window,
# older turns get summarized and dropped from the raw context sent to it.
COMPACT_THRESHOLD = 0.85

# Cap on the summary itself so compaction can't grow the context it's meant to shrink.
SUMMARY_MAX_TOKENS = 1000

SUMMARY_SYSTEM_PROMPT = """You are compacting an earlier portion of a conversation between a user and an AI assistant so it can be dropped from the active context while preserving what matters. Write a dense, factual summary covering:
- The user's overall goal or topic for this conversation
- Key questions asked and how they were answered
- Any decisions, conclusions, or facts established
- Any unresolved questions or pending next steps

Be concise and information-dense. Do not add commentary, headers, or restate this instruction. Write only the summary itself."""


def _estimate_tokens(text: str) -> int:
    """Rough chars/4 heuristic — no real tokenizer, just needs to be in the right ballpark."""
    return max(1, len(text) // 4) if text else 0


def _format_transcript(messages: list[dict]) -> str:
    lines = []
    for m in messages:
        speaker = "User" if m["role"] == "user" else "Assistant"
        lines.append(f"{speaker}: {m['content']}")
    return "\n\n".join(lines)


async def _get_compaction(
    db: AsyncSession, conversation_id: int, provider: str, model: str
) -> ContextCompaction | None:
    result = await db.execute(
        select(ContextCompaction).where(
            ContextCompaction.conversation_id == conversation_id,
            ContextCompaction.provider == provider,
            ContextCompaction.model == model,
        )
    )
    return result.scalar_one_or_none()


async def _upsert_compaction(
    db: AsyncSession, conversation_id: int, provider: str, model: str, summary: str, covers_through_turn: int
) -> None:
    existing = await _get_compaction(db, conversation_id, provider, model)
    if existing:
        existing.summary = summary
        existing.covers_through_turn = covers_through_turn
    else:
        db.add(ContextCompaction(
            conversation_id=conversation_id,
            provider=provider,
            model=model,
            summary=summary,
            covers_through_turn=covers_through_turn,
        ))
    await db.flush()


async def maybe_compact_context(
    db: AsyncSession,
    conversation_id: int,
    provider: str,
    model: str,
    api_key: str,
    context_messages: list[dict],
) -> tuple[str | None, list[dict]]:
    """
    Given the full attributed context built for one (provider, model) target,
    return (summary_or_None, messages_to_send): messages_to_send is the tail of
    context_messages not already covered by a cached summary. Summaries are
    cached per (conversation, provider, model) in ContextCompaction so turns
    under threshold are a cheap no-op — only crossing the threshold triggers a
    fresh (self-)summarization call against the same target model.
    """
    existing = await _get_compaction(db, conversation_id, provider, model)

    # A retry/edit can pass in a context truncated to some earlier turn. If the
    # cached summary already covers turns beyond what's present here, it was
    # built from a fuller/later view of the conversation and doesn't apply to
    # this truncated one — fall back to the raw (uncompacted) messages instead
    # of returning a summary with nothing left to go with it.
    max_turn_present = max((m["turn_number"] for m in context_messages), default=0)
    if existing and existing.covers_through_turn > max_turn_present:
        existing = None

    covers_through = existing.covers_through_turn if existing else 0
    recent = [m for m in context_messages if m["turn_number"] > covers_through]

    summary_tokens = _estimate_tokens(existing.summary) if existing else 0
    recent_tokens = sum(_estimate_tokens(m["content"]) for m in recent)
    total_tokens = summary_tokens + recent_tokens

    limit = get_context_length(model) * COMPACT_THRESHOLD
    distinct_turns = sorted(set(m["turn_number"] for m in recent))

    if total_tokens <= limit or len(distinct_turns) < 2:
        return (existing.summary if existing else None), recent

    # Split at the halfway point of the *recent* turns (never re-splitting
    # what's already summarized) — turn-number aligned so a user question and
    # its answers never end up split across the boundary.
    split_turn = distinct_turns[len(distinct_turns) // 2 - 1]
    older = [m for m in recent if m["turn_number"] <= split_turn]
    newer = [m for m in recent if m["turn_number"] > split_turn]
    if not older or not newer:
        return (existing.summary if existing else None), recent

    summary_input = []
    if existing and existing.summary:
        summary_input.append(f"Previous summary of even earlier turns:\n{existing.summary}")
    summary_input.append(f"Conversation to summarize:\n{_format_transcript(older)}")

    provider_obj = get_provider(provider)
    result = await provider_obj.chat(
        [
            {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
            {"role": "user", "content": "\n\n".join(summary_input)},
        ],
        model,
        api_key,
        max_tokens=SUMMARY_MAX_TOKENS,
    )
    new_summary = result["content"].strip()
    new_covers_through = older[-1]["turn_number"]

    await _upsert_compaction(db, conversation_id, provider, model, new_summary, new_covers_through)

    return new_summary, newer
