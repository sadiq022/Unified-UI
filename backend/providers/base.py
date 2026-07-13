from abc import ABC, abstractmethod


class BaseProvider(ABC):
    """Abstract base class for all LLM provider adapters."""

    @abstractmethod
    async def chat(self, messages: list[dict], model: str, api_key: str) -> dict:
        """
        Send a chat request to the provider.

        Args:
            messages: List of {"role": str, "content": str} dicts with turn markers.
            model: Model identifier string.
            api_key: The API key for authentication.

        Returns:
            {
                "content": str,          # The assistant's response text
                "token_count": int|None, # Total tokens used (if available)
            }
        """
        pass

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
