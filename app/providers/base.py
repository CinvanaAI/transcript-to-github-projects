"""Base types for provider adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Sequence

from ..config import AppConfig


PROVIDER_OPENAI = "OpenAI"
PROVIDER_OLLAMA_LOCAL = "Ollama Local"
PROVIDER_OLLAMA_CLOUD = "Ollama Cloud"
PROVIDER_OPTIONS = (
    PROVIDER_OPENAI,
    PROVIDER_OLLAMA_LOCAL,
    PROVIDER_OLLAMA_CLOUD,
)


@dataclass(frozen=True)
class ModelCapability:
    """Minimal capability metadata for a provider/model path."""

    can_list_models: bool
    can_analyze_transcript: bool
    recommended_for_analysis: bool
    notes: str | None = None


class ProviderError(RuntimeError):
    """Raised when a provider adapter fails."""


class ProviderAdapter(ABC):
    """Minimal contract for provider-specific model and analysis logic."""

    name: str
    fallback_model_ids: tuple[str, ...]

    @abstractmethod
    def list_models(self, config: AppConfig) -> list[str]:
        """Return visible model IDs for the provider."""

    @abstractmethod
    def analyze_transcript(
        self,
        conversation_text: str,
        model_id: str,
        config: AppConfig,
    ) -> str:
        """Analyze a transcript and return raw response text."""

    @abstractmethod
    def get_model_capability(self, model_id: str | None) -> ModelCapability:
        """Return capabilities for the selected provider/model path."""

    @abstractmethod
    def build_model_buckets(self, model_ids: Sequence[str]) -> dict[str, list[str]]:
        """Build the UI's Recommended and All model buckets."""
