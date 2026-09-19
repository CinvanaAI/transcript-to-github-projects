"""Provider adapter registry and resolver."""

from __future__ import annotations

from .base import (
    ModelCapability,
    ProviderAdapter,
    ProviderError,
    PROVIDER_OLLAMA_CLOUD,
    PROVIDER_OLLAMA_LOCAL,
    PROVIDER_OPENAI,
    PROVIDER_OPTIONS,
)
from .ollama_cloud_provider import OllamaCloudProvider
from .ollama_local_provider import OllamaLocalProvider
from .openai_provider import OpenAIProvider


_PROVIDER_REGISTRY: dict[str, ProviderAdapter] = {
    PROVIDER_OPENAI: OpenAIProvider(),
    PROVIDER_OLLAMA_LOCAL: OllamaLocalProvider(),
    PROVIDER_OLLAMA_CLOUD: OllamaCloudProvider(),
}


def get_provider_adapter(provider_name: str) -> ProviderAdapter:
    """Resolve a provider adapter by display name."""

    try:
        return _PROVIDER_REGISTRY[provider_name]
    except KeyError as exc:
        raise ProviderError(f"Unsupported provider: {provider_name}") from exc


__all__ = [
    "ModelCapability",
    "ProviderAdapter",
    "ProviderError",
    "PROVIDER_OPENAI",
    "PROVIDER_OLLAMA_LOCAL",
    "PROVIDER_OLLAMA_CLOUD",
    "PROVIDER_OPTIONS",
    "get_provider_adapter",
]
