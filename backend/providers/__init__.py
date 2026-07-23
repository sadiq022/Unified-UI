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

# Approximate max context window (tokens) per model, used only to decide when to
# compact conversation history — doesn't need to be exact, just roughly right.
CONTEXT_LENGTHS: dict[str, int] = {
    # OpenAI
    "gpt-4o": 128_000,
    "gpt-4o-mini": 128_000,
    "gpt-4-turbo": 128_000,
    "gpt-4": 8_192,
    "gpt-3.5-turbo": 16_385,
    "o1-preview": 128_000,
    "o1-mini": 128_000,
    # Anthropic
    "claude-sonnet-4-20250514": 200_000,
    "claude-opus-4-20250514": 200_000,
    "claude-3-5-sonnet-20241022": 200_000,
    "claude-3-5-haiku-20241022": 200_000,
    "claude-3-opus-20240229": 200_000,
    # Gemini
    "gemini-3.1-flash-lite": 1_000_000,
    "gemini-3.5-flash": 1_000_000,
    # Groq
    "llama-3.3-70b-versatile": 128_000,
    "llama-3.1-8b-instant": 128_000,
    "gemma2-9b-it": 8_192,
    "qwen/qwen3-32b": 32_768,
    "qwen/qwen3.6-27b": 32_768,
    "openai/gpt-oss-20b": 128_000,
    "meta-llama/llama-4-scout-17b-16e-instruct": 128_000,
    # DeepSeek
    "deepseek-chat": 64_000,
    "deepseek-reasoner": 64_000,
    # OpenRouter (namespaced; varies by underlying model)
    "openai/gpt-4o": 128_000,
    "anthropic/claude-sonnet-4-20250514": 200_000,
    "google/gemini-2.5-pro-preview-05-06": 1_000_000,
    "meta-llama/llama-3.3-70b-instruct": 128_000,
    "mistralai/mistral-large-latest": 128_000,
    # NVIDIA NIM
    "deepseek-ai/deepseek-v4-pro": 128_000,
    "deepseek-ai/deepseek-v4-flash": 128_000,
    "mistralai/mistral-large-3-675b-instruct-2512": 128_000,
    "mistralai/mistral-small-4-119b-2603": 128_000,
    "z-ai/glm-5.2": 128_000,
    "qwen/qwen3.5-397b-a17b": 128_000,
    "nvidia/nemotron-3-super-120b-a12b": 128_000,
    # Cerebras
    "gemma-4-31b": 32_000,
    "zai-glm-4.7": 128_000,
    "gpt-oss-120b": 128_000,
}
DEFAULT_CONTEXT_LENGTH = 32_000  # fallback for unlisted/custom models


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


def get_context_length(model: str) -> int:
    """Approximate max context window (tokens) for a model, with a safe fallback."""
    return CONTEXT_LENGTHS.get(model, DEFAULT_CONTEXT_LENGTH)
