import json
from abc import ABC, abstractmethod
from typing import AsyncGenerator
import httpx


class BaseProvider(ABC):
    """Abstract base class for all LLM provider adapters."""

    @abstractmethod
    async def chat(
        self, messages: list[dict], model: str, api_key: str,
        max_tokens: int | None = None, temperature: float | None = None,
    ) -> dict:
        """
        Send a chat request to the provider.

        Args:
            messages: List of {"role": str, "content": str} dicts with turn markers.
            model: Model identifier string.
            api_key: The API key for authentication.
            max_tokens: Override the provider's default response length cap
                (used e.g. by context compaction to keep summaries short).
            temperature: Override the provider's default sampling temperature
                (used e.g. by memory extraction/audit, which want deterministic,
                low-temperature output rather than the normal chat temperature).

        Returns:
            {
                "content": str,          # The assistant's response text
                "token_count": int|None, # Total tokens used (if available)
            }
        """
        pass

    async def chat_stream(
        self, messages: list[dict], model: str, api_key: str, usage_sink: dict | None = None
    ) -> AsyncGenerator[str, None]:
        """
        Stream a chat response as it's generated, yielding text deltas.
        Default implementation falls back to a single chunk from chat() for any
        provider that hasn't implemented real streaming.

        usage_sink: an optional dict the caller passes in and reads after the
        generator is exhausted — streaming has no return value, so this is the
        side channel for token usage (which normally only arrives in a final
        chunk, after all the yielded text deltas).
        """
        result = await self.chat(messages, model, api_key)
        if usage_sink is not None:
            usage_sink["total_tokens"] = result.get("token_count")
        yield result["content"]

    def format_messages_with_turns(self, messages: list[dict]) -> list[dict]:
        """
        Add turn markers to user messages for context clarity.
        Messages should already have 'turn_number' in their metadata.

        Only user messages are prefixed. Prefixing assistant messages too would show
        the model its own past replies labeled "[Turn N] ...", and models tend to
        imitate that pattern and prepend the marker to their new reply.
        """
        formatted = []
        for msg in messages:
            turn = msg.get("turn_number")
            content = msg["content"]
            if turn is not None and msg["role"] == "user":
                content = f"[Turn {turn}] {content}"
            formatted.append({
                "role": msg["role"],
                "content": content,
            })
        return formatted

    def format_messages_with_image(self, messages: list[dict]) -> list[dict]:
        """
        Same as format_messages_with_turns, but also converts the current
        turn's attached image (if any) into the standard OpenAI-compatible
        multimodal content shape on the last user message:
            [{"type": "text", "text": ...}, {"type": "image_url", "image_url": {"url": ...}}]
        Shared by every provider whose API speaks this convention (Groq,
        local OpenAI-compatible servers running a vision-capable model, etc.)
        so a provider only needs to opt in by calling this instead of the
        plain turn-marker formatter — no per-provider image logic to duplicate.
        """
        formatted = self.format_messages_with_turns(messages)
        image = next(
            (msg["image"] for msg in reversed(messages) if msg.get("role") == "user" and msg.get("image")),
            None,
        )
        if image:
            for i in range(len(formatted) - 1, -1, -1):
                if formatted[i]["role"] == "user":
                    formatted[i] = {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": formatted[i]["content"]},
                            {"type": "image_url", "image_url": {"url": image}},
                        ],
                    }
                    break
        return formatted

    def _extract_openai_compatible_content(self, choice: dict) -> str:
        """
        Shared non-streaming content extraction for every OpenAI-compatible
        provider. Deliberately only ever returns the real "content" field —
        never the model's "reasoning_content" (its internal thinking trace,
        which some reasoning models return separately). If content is empty
        (e.g. the model ran out of length while still thinking), this returns
        "" and the caller shows a short, clean "no answer" note instead —
        the raw reasoning text itself never belongs in the visible chat.
        """
        return (choice.get("content") or "").strip()

    async def _stream_sse_openai_compatible(
        self, url: str, payload: dict, headers: dict, timeout: float = 120.0, usage_sink: dict | None = None
    ) -> AsyncGenerator[str, None]:
        """Shared SSE consumption for OpenAI-compatible streaming chat completions."""
        stream_payload = {**payload, "stream": True}
        # Ask for a final usage chunk — most OpenAI-compatible servers support this
        # and ignore it harmlessly if they don't. Without it, streamed responses
        # never carry a token count at all (only the non-streaming endpoint does).
        stream_payload.setdefault("stream_options", {"include_usage": True})
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", url, json=stream_payload, headers=headers) as response:
                if response.status_code >= 400:
                    await response.aread()
                    response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[len("data:"):].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    usage = chunk.get("usage")
                    if usage and usage_sink is not None:
                        usage_sink["total_tokens"] = usage.get("total_tokens")
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    # Only ever stream the real "content" deltas — a reasoning
                    # model's separate "reasoning_content" deltas (its internal
                    # thinking trace) are intentionally never yielded to the
                    # chat. If nothing but reasoning ever arrives, the caller
                    # (_stream_target) sees an empty accumulated response and
                    # shows a short "no answer" note instead — never the raw
                    # reasoning text.
                    text = choices[0].get("delta", {}).get("content")
                    if text:
                        yield text
