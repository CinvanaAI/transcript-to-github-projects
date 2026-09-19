"""Ollama Cloud provider adapter."""

from __future__ import annotations

from typing import Any, Sequence

import requests

from ..config import AppConfig
from .base import ModelCapability, ProviderAdapter, ProviderError, PROVIDER_OLLAMA_CLOUD
from ..translator import build_transcript_extraction_messages


FILTER_RECOMMENDED = "Recommended"
FILTER_ALL = "All"
FALLBACK_MODELS = ("llama3.2", "qwen3", "gemma3")
OLLAMA_CHAT_PATH = "/api/chat"


def _normalize_model_ids(model_ids: Sequence[str]) -> list[str]:
    return sorted({model_id.strip() for model_id in model_ids if model_id.strip()}, key=str.casefold)


def _normalize_base_url(base_url: str) -> str:
    return base_url.rstrip("/")


def _extract_response_content(response_data: dict[str, Any]) -> str:
    message = response_data.get("message")
    if isinstance(message, dict) and isinstance(message.get("content"), str):
        return message["content"]

    response_text = response_data.get("response")
    if isinstance(response_text, str):
        return response_text

    raise ProviderError("Ollama response was missing message content.")


class OllamaCloudProvider(ProviderAdapter):
    """Provider adapter for Ollama Cloud model discovery."""

    name = PROVIDER_OLLAMA_CLOUD
    fallback_model_ids = FALLBACK_MODELS

    def list_models(self, config: AppConfig) -> list[str]:
        cleaned_api_key = config.ollama_api_key.strip()
        if not cleaned_api_key:
            raise ProviderError("Missing required environment variable: OLLAMA_API_KEY.")

        endpoint = f"{_normalize_base_url(config.ollama_cloud_base_url)}/api/tags"
        headers = {
            "Authorization": f"Bearer {cleaned_api_key}",
            "Content-Type": "application/json",
        }

        try:
            response = requests.get(endpoint, headers=headers, timeout=30)
        except requests.RequestException as exc:
            raise ProviderError(f"Ollama model list request failed: {exc}") from exc

        if response.status_code >= 400:
            raise ProviderError(
                f"Ollama API error {response.status_code}: {response.text.strip() or 'no response body'}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderError("Ollama returned a non-JSON HTTP response for model listing.") from exc

        data = payload.get("models")
        if not isinstance(data, list):
            raise ProviderError("Ollama model list response was missing a top-level models array.")

        model_ids = _normalize_model_ids(
            (
                item.get("name")
                if isinstance(item, dict) and isinstance(item.get("name"), str)
                else item.get("model")
                if isinstance(item, dict) and isinstance(item.get("model"), str)
                else ""
            )
            for item in data
        )
        if not model_ids:
            raise ProviderError("Ollama returned no visible models.")

        return model_ids

    def analyze_transcript(
        self,
        conversation_text: str,
        model_id: str,
        config: AppConfig,
    ) -> str:
        cleaned_api_key = config.ollama_api_key.strip()
        if not cleaned_api_key:
            raise ProviderError("Missing required environment variable: OLLAMA_API_KEY.")

        endpoint = f"{_normalize_base_url(config.ollama_cloud_base_url)}{OLLAMA_CHAT_PATH}"
        payload = {
            "model": model_id.strip(),
            "messages": build_transcript_extraction_messages(conversation_text),
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {cleaned_api_key}",
            "Content-Type": "application/json",
        }

        try:
            response = requests.post(endpoint, headers=headers, json=payload, timeout=90)
        except requests.RequestException as exc:
            raise ProviderError(f"Ollama request failed: {exc}") from exc

        if response.status_code >= 400:
            raise ProviderError(
                f"Ollama API error {response.status_code}: {response.text.strip() or 'no response body'}"
            )

        try:
            response_data = response.json()
        except ValueError as exc:
            raise ProviderError("Ollama returned a non-JSON HTTP response.") from exc

        content = _extract_response_content(response_data)
        if not content.strip():
            raise ProviderError("Ollama response did not contain any text content.")

        return content

    def get_model_capability(self, model_id: str | None) -> ModelCapability:
        return ModelCapability(
            can_list_models=True,
            can_analyze_transcript=True,
            recommended_for_analysis=False,
            notes="Compatibility is determined by live analysis attempts.",
        )

    def build_model_buckets(self, model_ids: Sequence[str]) -> dict[str, list[str]]:
        cleaned_all_models = _normalize_model_ids(model_ids)
        return {
            FILTER_RECOMMENDED: cleaned_all_models.copy(),
            FILTER_ALL: cleaned_all_models,
        }
