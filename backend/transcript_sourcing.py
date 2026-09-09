"""
"Generate with sources" pipeline: splits an attached document into IDed
sentences, builds the indexed transcript block sent to the model, and
defensively parses + validates the structured citation JSON it returns.

This is model-agnostic — it runs once per send (not once per panel), and the
same sentence table + validator is reused regardless of which provider/model
produced a given response. See mom_prompts.py for the exact wording sent to
the LLM.
"""
import json
import re
from backend.mom_prompts import TRANSCRIPT_BLOCK_HEADER

_WHITESPACE_RE = re.compile(r"\s+")
# Split after sentence-ending punctuation, only where followed by whitespace
# and something that looks like the start of a new sentence — good enough for
# transcript-style text (speaker labels, timestamps) without a full NLP
# tokenizer.
_SENTENCE_SPLIT_RE = re.compile(r'(?<=[.!?])\s+(?=[A-Z0-9"\'])')

MOM_SECTIONS = ("action_items", "decisions", "discussion_points")


def split_sentences(text: str) -> list[str]:
    """Best-effort sentence splitter — not perfect, good enough to check results."""
    if not text:
        return []
    normalized = _WHITESPACE_RE.sub(" ", text.strip())
    if not normalized:
        return []
    parts = _SENTENCE_SPLIT_RE.split(normalized)
    return [p.strip() for p in parts if p.strip()]


def build_indexed_transcript(text: str) -> tuple[str, list[dict]]:
    """
    Returns (indexed_block, sentence_table):
      - indexed_block: "[S1] ...\n[S2] ..." text to embed in the prompt.
      - sentence_table: [{"id": "S1", "text": "..."}, ...] — the lookup used
        both to validate returned citations and to render the source panel.
    """
    sentences = split_sentences(text)
    table = [{"id": f"S{i + 1}", "text": s} for i, s in enumerate(sentences)]
    block = "\n".join(f"[{row['id']}] {row['text']}" for row in table)
    return block, table


def build_mom_user_content(question: str, indexed_block: str) -> str:
    """The full user-turn content sent to the model in place of the plain
    question + raw attachment text: the question, then the indexed transcript."""
    return f"{question}\n\n{TRANSCRIPT_BLOCK_HEADER}\n{indexed_block}"


def _parse_json_object(raw: str):
    """Defensively parse an LLM's JSON object response, tolerating markdown fences."""
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text[:4].lower() == "json":
            text = text[4:]
        text = text.strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _clean_mom_dict(parsed: dict, valid_ids: set[str]) -> dict | None:
    """Shared cleanup for both a fully-parsed object and a salvaged one: keep
    only well-formed items, and drop any source_id not present in valid_ids —
    this is the one enforcement point that keeps a hallucinated ID from ever
    reaching the UI, regardless of which model produced it."""
    result = {}
    any_items = False
    for key in MOM_SECTIONS:
        items = parsed.get(key)
        if not isinstance(items, list):
            items = []
        cleaned = []
        for item in items:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            source_ids = item.get("source_ids")
            if not isinstance(source_ids, list):
                source_ids = []
            valid_cited = [sid for sid in source_ids if isinstance(sid, str) and sid in valid_ids]
            cleaned.append({"text": text, "source_ids": valid_cited})
            any_items = True
        result[key] = cleaned
    return result if any_items else None


# Matches one complete {"text": "...", "source_ids": [...]} object, even when
# it's embedded inside JSON that's incomplete/truncated overall.
_ITEM_RE = re.compile(
    r'\{\s*"text"\s*:\s*"((?:[^"\\]|\\.)*)"\s*,\s*"source_ids"\s*:\s*\[((?:[^\]]*))\]\s*\}'
)


def _salvage_truncated_mom(raw: str, valid_ids: set[str]) -> dict | None:
    """
    A model can run out of response length mid-generation, leaving the JSON
    truncated (unterminated string, missing closing brackets) — a hard parse
    failure that would otherwise throw away everything, even items the model
    did finish writing. Recover those instead: scan each section's own span of
    the raw text and pull out only complete {"text","source_ids"} objects.
    """
    result = {}
    any_items = False
    # Section spans in appearance order, so a section's content is bounded by
    # wherever the next section key (or end of string) starts — this keeps a
    # recovered item from bleeding into the wrong section.
    positions = [(key, raw.find(f'"{key}"')) for key in MOM_SECTIONS]
    positions = [(k, p) for k, p in positions if p != -1]
    positions.sort(key=lambda kp: kp[1])

    for idx, (key, start) in enumerate(positions):
        end = positions[idx + 1][1] if idx + 1 < len(positions) else len(raw)
        span = raw[start:end]
        cleaned = []
        for m in _ITEM_RE.finditer(span):
            try:
                text = json.loads(f'"{m.group(1)}"')
            except json.JSONDecodeError:
                continue
            text = text.strip()
            if not text:
                continue
            source_ids = [sid for sid in re.findall(r'"([^"]*)"', m.group(2)) if sid in valid_ids]
            cleaned.append({"text": text, "source_ids": source_ids})
            any_items = True
        result[key] = cleaned

    if not any_items:
        return None
    result["truncated"] = True
    return result


def parse_and_validate_mom(raw_content: str, valid_ids: set[str]) -> dict | None:
    """
    Parses a model's response as the {action_items, decisions, discussion_points}
    citation schema. Returns None only if nothing usable could be recovered at
    all (caller should fall back to showing the raw text).
    """
    parsed = _parse_json_object(raw_content)
    if parsed is not None:
        return _clean_mom_dict(parsed, valid_ids)
    # Not valid JSON at all — most likely cut off mid-generation. Salvage
    # whatever complete items did finish rather than discarding everything.
    return _salvage_truncated_mom(raw_content, valid_ids)
