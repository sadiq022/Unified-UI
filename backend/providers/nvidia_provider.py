import httpx
from backend.providers.base import BaseProvider


class NvidiaProvider(BaseProvider):
    """Provider adapter for NVIDIA NIM's OpenAI-compatible API (integrate.api.nvidia.com)."""

    BASE_URL = "https://integrate.api.nvidia.com/v1/chat/completions"

    async def chat(
        self, messages: list[dict], model: str, api_key: str,
        max_tokens: int | None = None, temperature: float | None = None,
    ) -> dict:
        formatted = self.format_messages_with_image(messages)

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": model,
            "messages": formatted,
            "temperature": temperature if temperature is not None else 0.7,
            # NVIDIA-hosted reasoning models (nemotron, deepseek-v4, etc.) can
            # spend most of a small budget narrating their reasoning in plain
            # prose — not even wrapped in <think> tags, so there's nothing to
            # strip — before ever reaching the real answer.
            "max_tokens": max_tokens or 16384,
        }

        # NVIDIA-hosted reasoning models (e.g. deepseek-ai/deepseek-v4-pro) can take
        # several minutes, well beyond what other providers need.
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(self.BASE_URL, json=payload, headers=headers)
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
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": formatted,
            "temperature": 0.7,
            "max_tokens": 16384,
        }
        # NVIDIA-hosted reasoning models can take several minutes to complete.
        async for delta in self._stream_sse_openai_compatible(
            self.BASE_URL, payload, headers, timeout=300.0, usage_sink=usage_sink
        ):
            yield delta
