"""Turns a web search into a system message for the current turn, when the user
switches the Web search toggle on. The results are added to this request's
context only — never stored in the conversation — so they can't go stale or
bloat later turns. Searching is done once per message, not once per panel."""
import asyncio
import datetime
import os
import re

from backend.services.search.core import comprehensive_web_search

# Every search this app runs gets appended here — the original message, the
# query actually searched, and the exact text handed to the model — so you can
# see what's happening in the backend without digging through server logs.
# Not per-user (this is a single-user diagnostic log, not app data): if you
# share this machine, don't share this file, since it holds your chat content.
LOG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "web_search_log.txt")


def _log(message: str, query: str, prompt_text: str) -> None:
    entry = (
        f"{'=' * 100}\n"
        f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"YOUR MESSAGE:  {message}\n"
        f"SEARCH QUERY:  {query}\n"
        f"{'-' * 100}\n"
        f"SENT TO MODEL (exact system message it received):\n\n{prompt_text}\n\n"
    )
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(entry)
    except OSError as e:
        print(f"[web search] couldn't write log file: {e}")

SEARCH_TIMEOUT_SECONDS = 30
MAX_PAGES = 4
# Search results + fetched page text. Kept modest so small-context local
# models still have room for the conversation itself.
MAX_CONTEXT_CHARS = 9000
# The result block starts with a fenced ```sources list we don't need (the
# instructions below already tell the model to cite the URLs).
_SOURCES_FENCE_RE = re.compile(r"```sources.*?```\s*", re.DOTALL)

_INSTRUCTIONS = (
    "The user turned on web search. Below are live results from the web for their latest "
    "message. Use them to answer, prefer them over your own memory for anything current, and "
    "cite the pages you used as markdown links like [title](url). If the results don't answer "
    "the question, say so plainly instead of guessing."
)
_FAILED = (
    "The user turned on web search, but it returned no usable results (search failed or found "
    "nothing). Tell the user the web search didn't work and answer from your own knowledge only "
    "if you clearly say that it may be out of date."
)


_LEADING_NOISE_RE = re.compile(
    r"^\s*(please\s+)?(search|google|look\s*up|find)(\s+(the\s+)?(web|internet|online))?(\s+for)?\s*[:,-]?\s*",
    re.IGNORECASE,
)
_TRAILING_INSTRUCTION_RE = re.compile(
    r"\b(answer|reply|respond|explain|summari[sz]e|give me|include|in \d+ (sentences|words|bullets))\b.*$",
    re.IGNORECASE | re.DOTALL,
)
MAX_QUERY_CHARS = 200


def clean_query(message: str) -> str:
    """The whole chat message makes a poor search query — drop 'search the web:'
    prefixes and trailing formatting instructions, and cap the length."""
    q = _LEADING_NOISE_RE.sub("", message.strip())
    trimmed = _TRAILING_INSTRUCTION_RE.sub("", q).strip(" .,:;-\n")
    q = trimmed if len(trimmed) >= 8 else q
    return q[:MAX_QUERY_CHARS].strip()


async def build_web_search_preface(message: str) -> list[dict]:
    """Returns one system message (results, or a note that the search failed)."""
    query = clean_query(message)
    try:
        context, sources = await asyncio.wait_for(
            asyncio.to_thread(comprehensive_web_search, query, max_pages=MAX_PAGES, return_sources=True),
            timeout=SEARCH_TIMEOUT_SECONDS,
        )
    except Exception as e:  # timeout, network, provider errors — never fail the chat over search
        print(f"[web search] failed: {type(e).__name__}: {e}")
        _log(message, query, f"(search failed: {type(e).__name__}: {e})\n\n{_FAILED}")
        return [{"role": "system", "content": _FAILED}]

    if not sources:
        print(f"[web search] no results for {query!r}")
        _log(message, query, f"(no results)\n\n{_FAILED}")
        return [{"role": "system", "content": _FAILED}]

    context = _SOURCES_FENCE_RE.sub("", context).strip()
    # The log gets the full, untruncated fetch — the truncation below is only
    # to keep small-context models fed; you should still be able to see everything.
    full_context = context
    if len(context) > MAX_CONTEXT_CHARS:
        context = context[:MAX_CONTEXT_CHARS] + "\n[...results truncated before being sent to the model]"
    prompt_text = f"{_INSTRUCTIONS}\n\n{context}"
    log_text = prompt_text if context == full_context else f"{_INSTRUCTIONS}\n\n{full_context}\n\n[NOTE: the model only received the first {MAX_CONTEXT_CHARS} characters of the block above]"
    _log(message, query, log_text)
    return [{"role": "system", "content": prompt_text}]
