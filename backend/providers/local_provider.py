import json
import httpx
from backend.providers.base import BaseProvider


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
    # "thinking" before writing any visible answer, and exhaustive structured
    # output (e.g. "generate with sources" over a long transcript) can run to
    # thousands of tokens on its own — default well above the hosted providers
    # since local compute has no per-token cost to weigh, only the model's own
    # context window (commonly tens of thousands of tokens for local setups).
    DEFAULT_MAX_TOKENS = 32768

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

    async def chat(
        self, messages: list[dict], model: str, api_key: str,
        max_tokens: int | None = None, temperature: float | None = None,
    ) -> dict:
        formatted = self.format_messages_with_image(messages)

        payload = {
            "model": model,
            "messages": formatted,
            "temperature": temperature if temperature is not None else 0.7,
            "max_tokens": max_tokens or self.DEFAULT_MAX_TOKENS,
            # Qwen3-style hybrid thinking models can spend tens of thousands of
            # tokens reasoning before ever answering — often 10-100x slower
            # than just answering directly, and we don't want to show the
            # reasoning anyway. Tell the chat template to skip it entirely
            # instead of generating it and filtering it out afterward.
            # Harmless for templates that don't define this variable.
            "chat_template_kwargs": {"enable_thinking": False},
        }

        # Generous timeout — local inference (especially CPU-only) can be much
        # slower than a hosted API.
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(self._chat_url(api_key), json=payload)
            response.raise_for_status()
            data = response.json()

        choice = data["choices"][0]["message"]
        usage = data.get("usage", {})

        return {
            "content": self._extract_openai_compatible_content(choice),
            "token_count": usage.get("total_tokens"),
        }

    async def chat_stream(self, messages: list[dict], model: str, api_key: str, usage_sink: dict | None = None):
        formatted = self.format_messages_with_image(messages)
        payload = {
            "model": model,
            "messages": formatted,
            "temperature": 0.7,
            "max_tokens": self.DEFAULT_MAX_TOKENS,
            "stream": True,
            "stream_options": {"include_usage": True},
            "chat_template_kwargs": {"enable_thinking": False},
        }

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
                    usage = chunk.get("usage")
                    if usage and usage_sink is not None:
                        usage_sink["total_tokens"] = usage.get("total_tokens")
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    # Only ever stream real "content" deltas — reasoning models
                    # (llama.cpp, vLLM's --reasoning-parser, etc.) send their
                    # thinking trace separately in "reasoning_content", which
                    # never belongs in the visible chat. If nothing but
                    # reasoning ever arrives, _stream_target sees an empty
                    # accumulated response and shows a short "no answer" note.
                    text = choices[0].get("delta", {}).get("content")
                    if text:
                        yield text
