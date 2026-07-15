from backend.providers.base import BaseProvider
from backend.providers.openai_provider import OpenAIProvider
from backend.providers.anthropic_provider import AnthropicProvider
from backend.providers.gemini_provider import GeminiProvider
from backend.providers.groq_provider import GroqProvider
from backend.providers.deepseek_provider import DeepSeekProvider
from backend.providers.openrouter_provider import OpenRouterProvider
from backend.providers.nvidia_provider import NvidiaProvider
from backend.providers.cerebras_provider import CerebrasProvider

PROVIDERS: dict[str, BaseProvider] = {
    "openai": OpenAIProvider(),
    "anthropic": AnthropicProvider(),
    "gemini": GeminiProvider(),
    "groq": GroqProvider(),
    "deepseek": DeepSeekProvider(),
    "openrouter": OpenRouterProvider(),
    "nvidia": NvidiaProvider(),
    "cerebras": CerebrasProvider(),
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
        "gemini-3.1-flash-lite",
        "gemini-3.5-flash",
    ],
    "groq": [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "gemma2-9b-it",
        "qwen/qwen3-32b",
        "qwen/qwen3.6-27b",
        "openai/gpt-oss-20b",
        "meta-llama/llama-4-scout-17b-16e-instruct",
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
    "nvidia": [
        "deepseek-ai/deepseek-v4-pro",
        "deepseek-ai/deepseek-v4-flash",
        "mistralai/mistral-large-3-675b-instruct-2512",
        "mistralai/mistral-small-4-119b-2603",
        "z-ai/glm-5.2",
        "qwen/qwen3.5-397b-a17b",
        "nvidia/nemotron-3-super-120b-a12b",
    ],
    "cerebras": [
        "gemma-4-31b",
        "zai-glm-4.7",
        "gpt-oss-120b",
    ],
}

# Models that accept image input. None of the other listed models support vision.
VISION_MODELS: dict[str, list[str]] = {
    "groq": [
        "qwen/qwen3.6-27b",
        "meta-llama/llama-4-scout-17b-16e-instruct",
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


def is_vision_model(provider_name: str, model: str) -> bool:
    """Whether a given provider/model pair can accept image input."""
    return model in VISION_MODELS.get(provider_name.lower(), [])


def get_vision_models() -> dict[str, list[str]]:
    """Get the full map of provider -> vision-capable models."""
    return VISION_MODELS
