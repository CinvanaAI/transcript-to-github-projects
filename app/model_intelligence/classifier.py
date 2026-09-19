"""Compatibility classification helpers."""

from __future__ import annotations

from dataclasses import dataclass

from .store import (
    COMPATIBILITY_STATUS_FIXABLE,
    COMPATIBILITY_STATUS_UNKNOWN,
    COMPATIBILITY_STATUS_UNSUPPORTED,
)


@dataclass(frozen=True)
class CompatibilityClassification:
    """Normalized compatibility classification result."""

    compatibility_status: str
    blocked_reason: str | None
    fix_hint: str | None
    last_error_type: str | None
    last_error_message: str | None


def _contains_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(pattern in text for pattern in patterns)


def _unsupported_hint(capability_notes: str | None) -> str | None:
    notes = (capability_notes or "").strip()
    lowered = notes.casefold()

    if not notes:
        return None
    if "not implemented" in lowered or "supports model discovery only" in lowered:
        return "This provider currently supports model discovery only, not transcript analysis."
    return notes


def classify_capability_result(
    *,
    provider: str,
    model_id: str,
    task_name: str,
    can_list_models: bool,
    can_analyze_transcript: bool,
    capability_notes: str | None = None,
) -> CompatibilityClassification:
    """Classify a capability result before any live request is made."""

    if can_analyze_transcript:
        return CompatibilityClassification(
            compatibility_status=COMPATIBILITY_STATUS_UNKNOWN,
            blocked_reason="Compatibility will be determined by a live analysis attempt.",
            fix_hint="Run analysis with the selected model to record the real outcome.",
            last_error_type=None,
            last_error_message=None,
        )

    return CompatibilityClassification(
        compatibility_status=COMPATIBILITY_STATUS_UNSUPPORTED,
        blocked_reason=capability_notes or f"{provider} cannot analyze transcripts with {model_id}.",
        fix_hint=_unsupported_hint(capability_notes),
        last_error_type=None,
        last_error_message=None,
    )


def classify_exception_result(
    *,
    provider: str,
    model_id: str,
    task_name: str,
    exception_type: str,
    exception_message: str,
    capability_notes: str | None = None,
) -> CompatibilityClassification:
    """Classify an analysis failure into supported/unsupported/fixable/unknown."""

    error_type = exception_type.strip() or "UnknownError"
    error_message = exception_message.strip() or "Unknown compatibility failure."
    lowered_message = error_message.casefold()
    lowered_notes = (capability_notes or "").casefold()

    if _contains_any(
        lowered_notes,
        (
            "not implemented",
            "supports model discovery only",
            "cannot analyze transcripts",
        ),
    ):
        return CompatibilityClassification(
            compatibility_status=COMPATIBILITY_STATUS_UNSUPPORTED,
            blocked_reason=capability_notes or error_message,
            fix_hint=_unsupported_hint(capability_notes),
            last_error_type=error_type,
            last_error_message=error_message,
        )

    if _contains_any(
        lowered_message,
        (
            "not implemented for ollama",
            "use openai for transcript analysis",
            "cannot analyze transcripts",
        ),
    ):
        return CompatibilityClassification(
            compatibility_status=COMPATIBILITY_STATUS_UNSUPPORTED,
            blocked_reason=error_message,
            fix_hint=_unsupported_hint(error_message),
            last_error_type=error_type,
            last_error_message=error_message,
        )

    if _contains_any(
        lowered_message,
        (
            "missing required environment variable",
            "api key",
            "unauthorized",
            "forbidden",
            "authentication",
            "401",
            "403",
            "permission",
            "connection refused",
            "failed to establish a new connection",
            "max retries exceeded",
            "name or service not known",
            "connection aborted",
        ),
    ):
        return CompatibilityClassification(
            compatibility_status=COMPATIBILITY_STATUS_FIXABLE,
            blocked_reason=error_message,
            fix_hint="Check API key, provider URL, and authentication settings.",
            last_error_type=error_type,
            last_error_message=error_message,
        )

    if _contains_any(
        lowered_message,
        (
            "unsupported temperature",
            "temperature is not supported",
            "response_format",
            "json_schema",
            "unsupported parameter",
            "unknown parameter",
            "unsupported value",
            "chat completions",
            "responses api",
            "choices[0].message",
            "schema",
            "endpoint",
            "did not contain json content",
            "invalid json",
            "missing message content",
            "unexpected response structure",
        ),
    ):
        return CompatibilityClassification(
            compatibility_status=COMPATIBILITY_STATUS_FIXABLE,
            blocked_reason=error_message,
            fix_hint="Check request format for this provider/model path.",
            last_error_type=error_type,
            last_error_message=error_message,
        )

    if _contains_any(
        lowered_message,
        (
            "embedding",
            "embeddings",
            "audio only",
            "image generation",
            "vision only",
            "modality",
            "not supported for this task",
        ),
    ):
        return CompatibilityClassification(
            compatibility_status=COMPATIBILITY_STATUS_UNSUPPORTED,
            blocked_reason=error_message,
            fix_hint="Choose a model that can handle text generation for transcript analysis.",
            last_error_type=error_type,
            last_error_message=error_message,
        )

    if _contains_any(
        lowered_message,
        (
            "model does not exist",
            "no visible models",
            "not available",
            "do not have access",
            "does not have access",
        ),
    ):
        return CompatibilityClassification(
            compatibility_status=COMPATIBILITY_STATUS_FIXABLE,
            blocked_reason=error_message,
            fix_hint="Choose a visible model or check model access.",
            last_error_type=error_type,
            last_error_message=error_message,
        )

    return CompatibilityClassification(
        compatibility_status=COMPATIBILITY_STATUS_UNKNOWN,
        blocked_reason=error_message,
        fix_hint="Check provider availability and request details for this model path.",
        last_error_type=error_type,
        last_error_message=error_message,
    )
