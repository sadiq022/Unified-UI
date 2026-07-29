import json
import httpx
from backend.providers.base import BaseProvider

_NO_ANSWER_NOTE = (
    "[No answer was produced before the token limit was reached — "
    "showing the model's reasoning instead:]\n"
)


class LocalProvider(BaseProvider):
    """
    Provider adapter for a locally-running OpenAI-compatible chat completions
    server (e.g. vLLM, llama.cpp server, LM Studio, Ollama's /v1 endpoint).

    Local servers usually need no credential, so the "API key" field for this
    provider is repurposed to hold the server's base URL instead (e.g.
    http://localhost:8000) — no schema change needed to support it.
    """

    DEFAULT_BASE_URL = "http://localhost:8000"

    # Reasoning models (e.g. gpt-oss) can spend most of a small budget just
    # "thinking" before writing any visible answer — default well above the
    # hosted providers since local compute has no per-token cost to weigh.
    DEFAULT_MAX_TOKENS = 8192

    def _chat_url(self, base_url: str) -> str:
        base = (base_url or self.DEFAULT_BASE_URL).strip().rstrip("/")
        return f"{base}/v1/chat/completions"

    async def list_models(self, base_url: str) -> list[str]:
        """Ask the local server what's actually loaded, via its own /v1/models."""
        base = (base_url or self.DEFAULT_BASE_URL).strip().rstrip("/")
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{base}/v1/models")
            response.raise_for_status()
            data = response.json()
        return [m["id"] for m in data.get("data", []) if m.get("id")]

    async def chat(self, messages: list[dict], model: str, api_key: str, max_tokens: int | None = None) -> dict:
        formatted = self.format_messages_with_turns(messages)

        payload = {
            "model": model,
            "messages": formatted,
            "temperature": 0.7,
            "max_tokens": max_tokens or self.DEFAULT_MAX_TOKENS,
        }

        # Generous timeout — local inference (especially CPU-only) can be much
        # slower than a hosted API.
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(self._chat_url(api_key), json=payload)
            response.raise_for_status()
            data = response.json()

        choice = data["choices"][0]["message"]
        usage = data.get("usage", {})

        # Reasoning models (llama.cpp, vLLM's --reasoning-parser, etc.) return the
        # thinking trace in its own "reasoning_content" field, separate from
        # "content". If the token budget runs out mid-thought, "content" comes
        # back empty even though the model did produce output — surface the
        # reasoning instead of leaving the chat bubble blank.
        content = (choice.get("content") or "").strip()
        if not content and choice.get("reasoning_content"):
            content = _NO_ANSWER_NOTE + choice["reasoning_content"]

        return {
            "content": content,
            "token_count": usage.get("total_tokens"),
        }

    async def chat_stream(self, messages: list[dict], model: str, api_key: str):
        formatted = self.format_messages_with_turns(messages)
        payload = {
            "model": model,
            "messages": formatted,
            "temperature": 0.7,
            "max_tokens": self.DEFAULT_MAX_TOKENS,
            "stream": True,
        }

        content_seen = False
        reasoning_buffer = ""

        async with httpx.AsyncClient(timeout=300.0) as client:
            async with client.stream("POST", self._chat_url(api_key), json=payload) as response:
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
                    delta = choices[0].get("delta", {})
                    text = delta.get("content")
                    if text:
                        content_seen = True
                        yield text
                    elif delta.get("reasoning_content"):
                        reasoning_buffer += delta["reasoning_content"]

        # Same fallback as chat(): nothing but reasoning ever arrived, so show
        # that instead of ending the stream with an empty bubble.
        if not content_seen and reasoning_buffer:
            yield _NO_ANSWER_NOTE + reasoning_buffer
