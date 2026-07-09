import httpx
from backend.providers.base import BaseProvider


class GroqProvider(BaseProvider):
    """Provider adapter for Groq's OpenAI-compatible API."""

    BASE_URL = "https://api.groq.com/openai/v1/chat/completions"

    async def chat(self, messages: list[dict], model: str, api_key: str) -> dict:
        formatted = self.format_messages_with_turns(messages)

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": model,
            "messages": formatted,
            "temperature": 0.7,
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(self.BASE_URL, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        choice = data["choices"][0]["message"]
        usage = data.get("usage", {})

        return {
            "content": choice["content"],
            "token_count": usage.get("total_tokens"),
        }
