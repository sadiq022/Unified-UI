import json
import httpx
from backend.providers.base import BaseProvider


class GeminiProvider(BaseProvider):
    """Provider adapter for Google Gemini's generateContent API."""

    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

    async def chat(
        self, messages: list[dict], model: str, api_key: str,
        max_tokens: int | None = None, temperature: float | None = None,
    ) -> dict:
        merged, system_instruction = self._build_contents(messages)

        url = f"{self.BASE_URL}/{model}:generateContent"

        headers = {
            "Content-Type": "application/json",
        }

        payload = {
            "contents": merged,
            "generationConfig": {
                "temperature": temperature if temperature is not None else 0.7,
                "maxOutputTokens": max_tokens or 4096,
            },
        }

        if system_instruction:
            payload["systemInstruction"] = {
                "parts": [{"text": system_instruction}]
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
        """Converts OpenAI-shaped {"role","content"} messages (plus an optional
        "image" data URL on the current turn) into Gemini's contents/parts
        shape. Gemini's image format (inline_data: {mime_type, data}) is
        unrelated to the OpenAI-style image_url convention the other
        providers share via BaseProvider.format_messages_with_image, so this
        is handled separately here rather than reusing that helper."""
        formatted = self.format_messages_with_turns(messages)
        image = next(
            (msg["image"] for msg in reversed(messages) if msg.get("role") == "user" and msg.get("image")),
            None,
        )
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

        if image and merged and merged[-1]["role"] == "user":
            header, _, b64_data = image.partition(",")
            mime_type = header.split(":")[1].split(";")[0] if header.startswith("data:") else "image/png"
            merged[-1]["parts"].append({"inline_data": {"mime_type": mime_type, "data": b64_data}})

        return merged, system_instruction.strip()

    async def chat_stream(self, messages: list[dict], model: str, api_key: str, usage_sink: dict | None = None):
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
                    usage = chunk.get("usageMetadata")
                    if usage and usage_sink is not None:
                        usage_sink["total_tokens"] = usage.get("totalTokenCount")
                    candidates = chunk.get("candidates", [])
                    if not candidates:
                        continue
                    parts = candidates[0].get("content", {}).get("parts", [])
                    for part in parts:
                        text = part.get("text")
                        if text:
                            yield text
