"""
Prompt injection side of the memory pipeline: turns stored Memory rows into
0-2 system messages prepended to a turn's context — pinned facts always,
plus the top few extended facts relevant to the current message (hybrid
BM25 keyword scoring; no vector index in this build, see memory_pipeline.py).
"""
import datetime
import math
import re
from sqlalchemy import select
from backend.models import Memory
from backend.memory_prompts import PINNED_PREFACE_HEADER, EXTENDED_PREFACE_HEADER

TOP_K_EXTENDED = 3
BM25_K1 = 1.5
BM25_B = 0.75

_TOKEN_RE = re.compile(r"[a-z0-9']+")
_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "but", "if", "then", "else", "for", "to", "of", "in", "on", "at", "by", "with",
    "is", "are", "was", "were", "be", "been", "being", "this", "that", "these", "those", "it", "its", "as", "from",
    "about", "into", "over", "after", "before", "between", "out", "up", "down", "not", "no", "so", "than", "too",
    "very", "can", "will", "just", "should", "would", "could", "do", "does", "did", "have", "has", "had",
    "i", "you", "he", "she", "they", "we", "my", "your", "his", "her", "their", "our", "me", "him", "them", "us",
})


def _tokenize(text: str) -> list[str]:
    tokens = _TOKEN_RE.findall((text or "").lower())
    return [t for t in tokens if len(t) >= 3 and t not in _STOPWORDS]


def _bm25_top_k(memories: list[Memory], query_text: str, k: int = TOP_K_EXTENDED) -> list[Memory]:
    """Rank memories against the query by BM25-style IDF-weighted term overlap,
    treating the memory set itself as the corpus. Recency only breaks ties."""
    if not memories:
        return []
    query_terms = _tokenize(query_text)
    if not query_terms:
        return []

    docs = [_tokenize(m.text) for m in memories]
    doc_lens = [len(d) or 1 for d in docs]
    avgdl = sum(doc_lens) / len(doc_lens)
    n_docs = len(memories)

    df: dict[str, int] = {}
    for term in set(query_terms):
        df[term] = sum(1 for d in docs if term in d)

    scored = []
    for mem, doc, dlen in zip(memories, docs, doc_lens):
        score = 0.0
        for term in query_terms:
            n_qi = df.get(term, 0)
            if n_qi == 0:
                continue
            idf = math.log((n_docs - n_qi + 0.5) / (n_qi + 0.5) + 1)
            f = doc.count(term)
            if f == 0:
                continue
            score += idf * (f * (BM25_K1 + 1)) / (f + BM25_K1 * (1 - BM25_B + BM25_B * dlen / avgdl))
        if score > 0:
            scored.append((score, mem))

    scored.sort(key=lambda pair: (pair[0], pair[1].created_at or datetime.datetime.min), reverse=True)
    return [mem for _, mem in scored[:k]]


async def build_memory_preface(db, user_id: int, query_text: str) -> tuple[list[dict], list[Memory]]:
    """
    Returns (preface_messages, injected_memories):
      - preface_messages: 0-2 system-role {"role","content"} dicts to prepend
        to a target's context — pinned facts, then the top relevant extended
        facts for this specific message.
      - injected_memories: the Memory rows actually used, so the caller can
        bump their `uses` counter and commit once per turn (this is identical
        for every panel/target in the same turn, so callers should compute it
        once, not per target).
    """
    result = await db.execute(select(Memory).where(Memory.user_id == user_id))
    memories = result.scalars().all()
    if not memories:
        return [], []

    pinned = [m for m in memories if m.pinned]
    extended = [m for m in memories if not m.pinned]

    preface = []
    injected = []

    if pinned:
        lines = "\n".join(f"- {m.text}" for m in pinned)
        preface.append({"role": "system", "content": f"{PINNED_PREFACE_HEADER}\n{lines}"})
        injected.extend(pinned)

    relevant = _bm25_top_k(extended, query_text)
    if relevant:
        lines = "\n".join(f"- {m.text}" for m in relevant)
        preface.append({"role": "system", "content": f"{EXTENDED_PREFACE_HEADER}\n{lines}"})
        injected.extend(relevant)

    return preface, injected
