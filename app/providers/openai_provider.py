"""OpenAI provider adapter."""

from __future__ import annotations

from typing import Any, Sequence

import requests

from ..config import AppConfig
from .base import ModelCapability, ProviderAdapter, ProviderError, PROVIDER_OPENAI
from ..translator import build_transcript_extraction_messages


OPENAI_MODELS_URL = "https://api.openai.com/v1/models"
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
FILTER_RECOMMENDED = "Recommended"
FILTER_ALL = "All"
FALLBACK_MODELS = ("gpt-4o-mini", "gpt-5-mini", "gpt-5.4")


def _extract_response_text(response_data: dict[str, Any]) -> str:
    """Extract text from a raw Responses API payload without SDK helpers."""

    direct_text = response_data.get("output_text")
    if isinstance(direct_text, str) and direct_text.strip():
        return direct_text

    fragments: list[str] = []
    refusals: list[str] = []
    output = response_data.get("output")
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "output_text" and isinstance(part.get("text"), str):
                    fragments.append(part["text"])
                elif part.get("type") == "refusal" and isinstance(part.get("refusal"), str):
                    refusals.append(part["refusal"])

    combined = "".join(fragments).strip()
    if combined:
        return combined
    if refusals:
        raise ProviderError(f"OpenAI refused the request: {'; '.join(refusals)}")
    raise ProviderError("OpenAI response did not contain any output text.")


def _normalize_model_ids(model_ids: Sequence[str]) -> list[str]:
    return sorted({model_id.strip() for model_id in model_ids if model_id.strip()}, key=str.casefold)


class OpenAIProvider(ProviderAdapter):
    """Provider adapter for OpenAI APIs."""

    name = PROVIDER_OPENAI
    fallback_model_ids = FALLBACK_MODELS

    def list_models(self, config: AppConfig) -> list[str]:
        cleaned_api_key = config.openai_api_key.strip()
        if not cleaned_api_key:
            raise ProviderError("Missing required environment variable: OPENAI_API_KEY.")

        headers = {
            "Authorization": f"Bearer {cleaned_api_key}",
            "Content-Type": "application/json",
        }

        try:
            response = requests.get(OPENAI_MODELS_URL, headers=headers, timeout=30)
        except requests.RequestException as exc:
            raise ProviderError(f"OpenAI model list request failed: {exc}") from exc

        if response.status_code >= 400:
            raise ProviderError(
                f"OpenAI API error {response.status_code}: {response.text.strip() or 'no response body'}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderError("OpenAI returned a non-JSON HTTP response for model listing.") from exc

        data = payload.get("data")
        if not isinstance(data, list):
            raise ProviderError("OpenAI model list response was missing a top-level data array.")

        model_ids = _normalize_model_ids(
            item["id"]
            for item in data
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        )
        if not model_ids:
            raise ProviderError("OpenAI returned no visible models for this API key.")

        return model_ids

    def analyze_transcript(
        self,
        conversation_text: str,
        model_id: str,
        config: AppConfig,
    ) -> str:
        cleaned_model_id = model_id.strip() or config.openai_model
        cleaned_api_key = config.openai_api_key.strip()
        if not cleaned_api_key:
            raise ProviderError("Missing required environment variable: OPENAI_API_KEY.")

        try:
            messages = build_transcript_extraction_messages(conversation_text)
        except ValueError as exc:
            raise ProviderError(str(exc)) from exc

        payload = {"model": cleaned_model_id, "input": messages}

        headers = {
            "Authorization": f"Bearer {cleaned_api_key}",
            "Content-Type": "application/json",
        }

        try:
            response = requests.post(
                OPENAI_RESPONSES_URL,
                headers=headers,
                json=payload,
                timeout=90,
            )
        except requests.RequestException as exc:
            raise ProviderError(f"OpenAI request failed: {exc}") from exc

        if response.status_code >= 400:
            raise ProviderError(
                f"OpenAI API error {response.status_code}: {response.text.strip() or 'no response body'}"
            )

        try:
            response_data = response.json()
        except ValueError as exc:
            raise ProviderError("OpenAI returned a non-JSON HTTP response.") from exc

        return _extract_response_text(response_data)

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
