from backend.providers.base import BaseProvider
from backend.providers.openai_provider import OpenAIProvider
from backend.providers.anthropic_provider import AnthropicProvider
from backend.providers.gemini_provider import GeminiProvider
from backend.providers.groq_provider import GroqProvider
from backend.providers.deepseek_provider import DeepSeekProvider
from backend.providers.openrouter_provider import OpenRouterProvider

PROVIDERS: dict[str, BaseProvider] = {
    "openai": OpenAIProvider(),
    "anthropic": AnthropicProvider(),
    "gemini": GeminiProvider(),
    "groq": GroqProvider(),
    "deepseek": DeepSeekProvider(),
    "openrouter": OpenRouterProvider(),
}

# Hardcoded model lists per provider (used as defaults; OpenRouter fetches dynamically)
DEFAULT_MODELS: dict[str, list[str]] = {
    "openai": [
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4-turbo",
        "gpt-4",
        "gpt-3.5-turbo",
        "o1-preview",
        "o1-mini",
    ],
    "anthropic": [
        "claude-sonnet-4-20250514",
        "claude-opus-4-20250514",
        "claude-3-5-sonnet-20241022",
        "claude-3-5-haiku-20241022",
        "claude-3-opus-20240229",
    ],
    "gemini": [
        "gemini-1.5-flash",
        "gemini-1.5-flash-8b",
    ],
    "groq": [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "gemma2-9b-it",
    ],
    "deepseek": [
        "deepseek-chat",
        "deepseek-reasoner",
    ],
    "openrouter": [
        "openai/gpt-4o",
        "anthropic/claude-sonnet-4-20250514",
        "google/gemini-2.5-pro-preview-05-06",
        "meta-llama/llama-3.3-70b-instruct",
        "mistralai/mistral-large-latest",
    ],
}


def get_provider(name: str) -> BaseProvider:
    """Get a provider adapter by name."""
    provider = PROVIDERS.get(name.lower())
    if not provider:
        raise ValueError(f"Unknown provider: {name}. Available: {list(PROVIDERS.keys())}")
    return provider


def get_models(provider_name: str) -> list[str]:
    """Get default model list for a provider."""
    return DEFAULT_MODELS.get(provider_name.lower(), [])
