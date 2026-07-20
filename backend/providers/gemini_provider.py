import json
import httpx
from backend.providers.base import BaseProvider


class GeminiProvider(BaseProvider):
    """Provider adapter for Google Gemini's generateContent API."""

    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

    async def chat(self, messages: list[dict], model: str, api_key: str) -> dict:
        formatted = self.format_messages_with_turns(messages)

        # Convert OpenAI-style messages to Gemini format
        # Gemini uses "user" and "model" roles, and "parts" array
        system_instruction = ""
        contents = []

        for msg in formatted:
            role = msg["role"]
            if role == "system":
                system_instruction += msg["content"] + "\n"
                continue

            # Map roles: "assistant" -> "model"
            gemini_role = "model" if role == "assistant" else "user"
            contents.append({
                "role": gemini_role,
                "parts": [{"text": msg["content"]}],
            })

        # Ensure conversation starts with a user message
        if contents and contents[0]["role"] != "user":
            contents.insert(0, {"role": "user", "parts": [{"text": "Hello"}]})

        # Merge consecutive same-role messages (Gemini requires alternating)
        merged = []
        for item in contents:
            if merged and merged[-1]["role"] == item["role"]:
                merged[-1]["parts"].extend(item["parts"])
            else:
                merged.append(item)

        url = f"{self.BASE_URL}/{model}:generateContent"

        headers = {
            "Content-Type": "application/json",
        }

        payload = {
            "contents": merged,
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 4096,
            },
        }

        if system_instruction.strip():
            payload["systemInstruction"] = {
                "parts": [{"text": system_instruction.strip()}]
            }

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                url,
                json=payload,
                headers=headers,
                params={"key": api_key},
            )
            response.raise_for_status()
            data = response.json()

        # Extract text from Gemini response
        candidates = data.get("candidates", [])
        text = ""
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            for part in parts:
                text += part.get("text", "")

        usage = data.get("usageMetadata", {})
        token_count = usage.get("totalTokenCount")

        return {
            "content": text,
            "token_count": token_count,
        }

    def _build_contents(self, messages: list[dict]) -> tuple[list[dict], str]:
        formatted = self.format_messages_with_turns(messages)
        system_instruction = ""
        contents = []
        for msg in formatted:
            role = msg["role"]
            if role == "system":
                system_instruction += msg["content"] + "\n"
                continue
            gemini_role = "model" if role == "assistant" else "user"
            contents.append({"role": gemini_role, "parts": [{"text": msg["content"]}]})

        if contents and contents[0]["role"] != "user":
            contents.insert(0, {"role": "user", "parts": [{"text": "Hello"}]})

        merged = []
        for item in contents:
            if merged and merged[-1]["role"] == item["role"]:
                merged[-1]["parts"].extend(item["parts"])
            else:
                merged.append(item)
        return merged, system_instruction.strip()

    async def chat_stream(self, messages: list[dict], model: str, api_key: str):
        merged, system_instruction = self._build_contents(messages)

        url = f"{self.BASE_URL}/{model}:streamGenerateContent"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": merged,
            "generationConfig": {"temperature": 0.7, "maxOutputTokens": 4096},
        }
        if system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST", url, json=payload, headers=headers, params={"key": api_key, "alt": "sse"}
            ) as response:
                if response.status_code >= 400:
                    await response.aread()
                    response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[len("data:"):].strip()
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    candidates = chunk.get("candidates", [])
                    if not candidates:
                        continue
                    parts = candidates[0].get("content", {}).get("parts", [])
                    for part in parts:
                        text = part.get("text")
                        if text:
                            yield text
