"""Small text-cleanup helpers shared by the chat routes and background
pipelines (memory extraction, etc.) — kept in their own module so neither
has to import the other."""
import re

_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)
_UNCLOSED_THINK_RE = re.compile(r"<think>(.*)", re.IGNORECASE | re.DOTALL)


def strip_think_blocks(content: str) -> str:
    """
    Remove <think>...</think> reasoning traces some models (Qwen, DeepSeek-R1
    style, etc.) inline into their content. Reasoning is never shown or
    parsed, closed or not — a <think> tag left unclosed (the model ran out of
    response length mid-thought) just means everything from that point on is
    discarded, keeping only whatever real content came before it, if any.
    Models run with thinking disabled still emit an empty "<think></think>"
    shell before the answer, which this also removes.
    """
    stripped = _THINK_BLOCK_RE.sub("", content)
    match = _UNCLOSED_THINK_RE.search(stripped)
    if match:
        stripped = stripped[:match.start()]
    return stripped.strip()
