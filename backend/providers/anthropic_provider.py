import json
import httpx
from backend.providers.base import BaseProvider


class AnthropicProvider(BaseProvider):
    """Provider adapter for Anthropic's Messages API (different format from OpenAI)."""

    BASE_URL = "https://api.anthropic.com/v1/messages"

    async def chat(self, messages: list[dict], model: str, api_key: str, max_tokens: int | None = None) -> dict:
        formatted = self.format_messages_with_turns(messages)

        # Anthropic requires system message to be separate
        system_content = ""
        api_messages = []
        for msg in formatted:
            if msg["role"] == "system":
                system_content += msg["content"] + "\n"
            else:
                api_messages.append({
                    "role": msg["role"],
                    "content": msg["content"],
                })

        # Anthropic requires alternating user/assistant messages
        # Merge consecutive same-role messages
        merged = []
        for msg in api_messages:
            if merged and merged[-1]["role"] == msg["role"]:
                merged[-1]["content"] += "\n\n" + msg["content"]
            else:
                merged.append(msg)

        headers = {
            "x-api-key": api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }

        payload = {
            "model": model,
            "max_tokens": max_tokens or 4096,
            "messages": merged,
        }
        if system_content.strip():
            payload["system"] = system_content.strip()

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(self.BASE_URL, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        # Extract content from Anthropic's response format
        content_blocks = data.get("content", [])
        text = ""
        for block in content_blocks:
            if block.get("type") == "text":
                text += block.get("text", "")

        usage = data.get("usage", {})
        token_count = (usage.get("input_tokens", 0) or 0) + (usage.get("output_tokens", 0) or 0)

        return {
            "content": text,
            "token_count": token_count if token_count > 0 else None,
        }

    def _build_request(self, messages: list[dict]) -> tuple[list[dict], str]:
        formatted = self.format_messages_with_turns(messages)
        system_content = ""
        api_messages = []
        for msg in formatted:
            if msg["role"] == "system":
                system_content += msg["content"] + "\n"
            else:
                api_messages.append({"role": msg["role"], "content": msg["content"]})

        merged = []
        for msg in api_messages:
            if merged and merged[-1]["role"] == msg["role"]:
                merged[-1]["content"] += "\n\n" + msg["content"]
            else:
                merged.append(msg)
        return merged, system_content.strip()

    async def chat_stream(self, messages: list[dict], model: str, api_key: str):
        merged, system_content = self._build_request(messages)

        headers = {
            "x-api-key": api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }
        payload = {"model": model, "max_tokens": 4096, "messages": merged, "stream": True}
        if system_content:
            payload["system"] = system_content

        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", self.BASE_URL, json=payload, headers=headers) as response:
                if response.status_code >= 400:
                    await response.aread()
                    response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[len("data:"):].strip()
                    try:
                        event = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    if event.get("type") == "content_block_delta":
                        delta = event.get("delta", {})
                        if delta.get("type") == "text_delta":
                            text = delta.get("text")
                            if text:
                                yield text
