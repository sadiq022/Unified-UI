import json
from abc import ABC, abstractmethod
from typing import AsyncGenerator
import httpx


class BaseProvider(ABC):
    """Abstract base class for all LLM provider adapters."""

    @abstractmethod
    async def chat(self, messages: list[dict], model: str, api_key: str, max_tokens: int | None = None) -> dict:
        """
        Send a chat request to the provider.

        Args:
            messages: List of {"role": str, "content": str} dicts with turn markers.
            model: Model identifier string.
            api_key: The API key for authentication.
            max_tokens: Override the provider's default response length cap
                (used e.g. by context compaction to keep summaries short).

        Returns:
            {
                "content": str,          # The assistant's response text
                "token_count": int|None, # Total tokens used (if available)
            }
        """
        pass

    async def chat_stream(self, messages: list[dict], model: str, api_key: str) -> AsyncGenerator[str, None]:
        """
        Stream a chat response as it's generated, yielding text deltas.
        Default implementation falls back to a single chunk from chat() for any
        provider that hasn't implemented real streaming.
        """
        result = await self.chat(messages, model, api_key)
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

    async def _stream_sse_openai_compatible(
        self, url: str, payload: dict, headers: dict, timeout: float = 120.0
    ) -> AsyncGenerator[str, None]:
        """Shared SSE consumption for OpenAI-compatible streaming chat completions."""
        stream_payload = {**payload, "stream": True}
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
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta", {}).get("content")
                    if delta:
                        yield delta
