# Memory Extraction Architecture — Implementation Blueprint

A 4-stage pipeline that runs silently after every chat turn, building a persistent,
deduplicated, auto-audited user fact store that selectively injects into every prompt.

---

## Stage 1 — Extract (after every LLM response)

**Trigger:** Background task fired immediately after the assistant reply completes.

**Input:** Last 6 messages from session history (text only — strip images/audio blocks).

### Two parallel extractors

#### A) LLM Extractor

Send to your model with `temperature=0.1`, `max_tokens=500`:

**System prompt:**
```
You are a memory extraction assistant. Extract ONLY durable personal
facts useful across many future conversations.

Good: name, job, city, family, long-term projects, strong preferences.
Bad: today's topic, temporary moods, what the assistant said, one-off tasks.

Rules:
- MAX 2 facts per conversation
- Only facts the USER stated or clearly implied
- Each fact: single sentence, under 15 words
- If similar to something already known, skip it
- If nothing durable, return []

Return JSON array: [{"text": "...", "category": "..."}]
Categories: identity | preference | fact | contact | project | goal
Return ONLY valid JSON, no markdown fences.
```

Then append the last 6 messages as user/assistant turns.

#### B) Regex Fallback (no LLM needed, runs always)

```
"my name is X"       →  { text: "User's name is X.",            category: "identity"   }
"call me X"          →  { text: "User wants to be called X.",    category: "identity"   }
"I live in X"        →  { text: "User lives in X.",              category: "identity"   }
"I am from X"        →  { text: "User lives in X.",              category: "identity"   }
"I prefer/like X"    →  { text: "User prefers X.",               category: "preference" }
"I love/hate X"      →  { text: "User prefers X.",               category: "preference" }
"I want to visit X"  →  { text: "User wants to visit X.",        category: "goal"       }
```

Cap fallback at 2 results. Merge with LLM results — both lists feed into Stage 2.

---

## Stage 2 — Deduplicate Before Saving

For each candidate fact, run these checks in order. Skip the fact if **any** check matches.

### Check 1 — Vector similarity
Embed the candidate text. Query your vector store filtered by owner. Threshold: **0.72**.
If a match is found and it belongs to the same owner → duplicate, skip.

### Check 2 — Exact text match
Case-insensitive string comparison against all existing memories for this owner.

### Check 3 — Jaccard fuzzy match
Tokenize both texts into word sets. Compute:

```
similarity = |intersection| / |union|
```

Threshold: **0.6**. Catches rephrased duplicates when vector index is unavailable.

---

## Stage 3 — Store

### Memory entry schema

```json
{
  "id": "uuid-v4",
  "text": "User prefers Python over JavaScript.",
  "category": "preference",
  "pinned": false,
  "source": "auto",
  "owner": "user@example.com",
  "uses": 0,
  "timestamp": 1234567890
}
```

### Auto-pin rule

```python
if category == "identity":
    entry["pinned"] = True
```

Identity facts (name, location, job) are pinned so they appear in every prompt turn,
not just when topically relevant.

### Persistence

- **Primary store:** `memory.json` — flat JSON array, source of truth.
- **Vector index:** sidecar (FAISS or ChromaDB) — used for dedup lookups and retrieval. Rebuilt after every audit.

---

## Stage 4 — Periodic Audit (every 5 new memories)

Send all memories for that owner to the LLM. `temperature=0.1`, `max_tokens=16384`.

**System prompt:**
```
You are a memory database curator. Be CONSERVATIVE: remove only TRUE
duplicates and clearly useless entries. Every distinct fact must survive.
When in doubt, KEEP.

Rules:
1. MERGE only entries stating the SAME fact in different words. Keep both if unsure.
   DO NOT merge related-but-distinct: "Likes Python" and "Uses Python at work"
   are DIFFERENT — keep both.
2. REMOVE only: entries about what the AI did (not the user), empty, meaningless.
3. Keep original wording. Only lightly trim obvious redundancy.
4. Preserve the 'id' of the kept entry when merging.
5. Never invent facts.

Return JSON array: [{"id": "...", "text": "...", "category": "..."}]
Return ONLY valid JSON, no markdown fences.
```

**User message:** JSON array of all current memories for this owner.

### Safety net

If the result removes **more than 50%** of entries → reject entirely, keep originals.
This protects against hallucinated or truncated audit output.

### Fingerprint cache

Before calling the LLM, hash `id + text + category` of all current entries.
If the hash matches the last audit's fingerprint → skip the LLM call entirely (nothing changed).
Saves 30–120 seconds per pass.

After a successful audit, rebuild the vector index from the full saved set (all owners).

---

## Prompt Injection (every chat turn)

### Split memories into two buckets

```python
pinned   = [m for m in memories if m["pinned"]]      # always injected
extended = [m for m in memories if not m["pinned"]]   # injected only if relevant
```

### Bucket 1 — Pinned (always in every prompt)

Inject as a system message:
```
Core facts about the user:
- User's name is Sal.
- User lives in Dubai.
```

### Bucket 2 — Extended (top 3 relevant to current message only)

Retrieve using **hybrid BM25 + vector search**:

1. Tokenize the current user message (remove stopwords, min 3 chars).
2. Score each extended memory using IDF-weighted keyword overlap (BM25-style).
3. Add vector similarity score if vector index is available.
4. Recency is a tiebreaker only — never the primary signal.
5. Take top `k=3` results above a minimum score.

Inject as a system message:
```
Memory context. Do not reference unless the user asks about these topics.
- User prefers Python over JavaScript.
- User is building a RAG-based assistant.
```

Increment the `uses` counter on every memory actually injected.

---

## Full Prompt Order (every turn)

```
[system]  Your base system prompt
[system]  Current date and time
[system]  Untrusted context policy warning
[system]  Pinned memories             ← always present
[system]  Top-3 retrieved memories    ← only if relevant to current message
[system]  RAG document chunks         ← only if documents are indexed
─────── conversation history (last N messages) ───────
[user]    Current message (+ inline attachment content if any)
```

---

## Key Design Decisions

| Decision | Reason |
|---|---|
| Max 2 facts extracted per turn | Prevents noise and hallucination accumulation |
| Audit every 5 new memories | Keeps store clean without constant LLM overhead |
| Fingerprint skips unchanged audits | Saves 30–120s per pass when nothing changed |
| 50% deletion guard on audit | Protects against hallucinated or truncated output |
| Identity always pinned | Name/location useful every turn, not just topically |
| Extended retrieved by hybrid BM25+vector | Pure recency buries relevant older facts |
| Regex fallback alongside LLM | Obvious facts survive even if LLM call fails |
| `temperature=0.1` for all memory LLM calls | Keeps extraction and audit deterministic |

---

## File Structure to Implement

```
services/
  memory/
    memory_extractor.py   # extract_and_store(), audit_memories()
src/
  memory.py               # MemoryManager (load, save, add_entry, find_duplicates)
  memory_vector.py        # Vector index (add, find_similar, rebuild)
  memory_provider.py      # Wires manager + vector together
  chat_processor.py       # build_context_preface() — reads + injects memories
data/
  memory.json             # Flat array of all memory entries (source of truth)
  memory_tidy_state.json  # Fingerprint cache for audit skip
```

---

## Trigger Wiring

```python
# After every assistant reply completes:
asyncio.create_task(
    extract_and_store(
        session=current_session,
        memory_manager=memory_manager,
        memory_vector=memory_vector,
        endpoint_url=llm_endpoint,
        model=model_name,
        headers=auth_headers,
    )
)
```

The task runs in the background — the user gets the assistant reply immediately
without waiting for extraction to finish.
