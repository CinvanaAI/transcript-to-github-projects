"""Shared model catalog helpers built on provider adapters."""

from __future__ import annotations

from .config import AppConfig
from .model_intelligence import (
    COMPATIBILITY_STATUS_FIXABLE,
    COMPATIBILITY_STATUS_SUPPORTED,
    TASK_TRANSCRIPT_ANALYSIS,
    classify_capability_result,
    load_model_intelligence_store,
    read_compatibility_record,
    save_model_intelligence_store,
    upsert_catalog_record,
    upsert_compatibility_record,
)
from .providers import (
    ModelCapability,
    ProviderError,
    get_provider_adapter,
)
FILTER_RECOMMENDED = "Recommended"
FILTER_FIXABLE = "Fixable"
FILTER_ALL = "All"
MODEL_FILTER_OPTIONS = (FILTER_RECOMMENDED, FILTER_FIXABLE, FILTER_ALL)


class ModelCatalogError(RuntimeError):
    """Raised when visible model discovery fails."""


def _merge_existing_classification(
    provider: str,
    model_id: str,
    capability: ModelCapability,
    classification: object,
) -> object:
    store = load_model_intelligence_store()
    existing_record = read_compatibility_record(
        store,
        provider=provider,
        model_id=model_id,
        task_name=TASK_TRANSCRIPT_ANALYSIS,
    )

    if existing_record is None:
        return classification

    return classification.__class__(
        compatibility_status=existing_record.compatibility_status,
        blocked_reason=existing_record.blocked_reason,
        fix_hint=existing_record.fix_hint,
        last_error_type=existing_record.last_error_type,
        last_error_message=existing_record.last_error_message,
    )


def _build_fixable_models(provider: str, model_ids: list[str]) -> list[str]:
    return _build_models_by_status(provider, model_ids, {COMPATIBILITY_STATUS_FIXABLE})


def _ensure_compatibility_records(provider: str, model_ids: list[str]) -> None:
    store = load_model_intelligence_store()
    adapter = get_provider_adapter(provider)

    for model_id in model_ids:
        capability = adapter.get_model_capability(model_id)
        classification = classify_capability_result(
            provider=provider,
            model_id=model_id,
            task_name=TASK_TRANSCRIPT_ANALYSIS,
            can_list_models=capability.can_list_models,
            can_analyze_transcript=capability.can_analyze_transcript,
            capability_notes=capability.notes,
        )
        classification = _merge_existing_classification(provider, model_id, capability, classification)
        upsert_compatibility_record(
            store,
            provider=provider,
            model_id=model_id,
            task_name=TASK_TRANSCRIPT_ANALYSIS,
            can_list_models=capability.can_list_models,
            can_analyze_transcript=capability.can_analyze_transcript,
            compatibility_status=classification.compatibility_status,
            blocked_reason=classification.blocked_reason,
            fix_hint=classification.fix_hint,
            last_error_type=classification.last_error_type,
            last_error_message=classification.last_error_message,
        )

    save_model_intelligence_store(store)


def _build_models_by_status(
    provider: str,
    model_ids: list[str],
    allowed_statuses: set[str],
) -> list[str]:
    _ensure_compatibility_records(provider, model_ids)
    store = load_model_intelligence_store()
    selected_models: list[str] = []

    for model_id in model_ids:
        compatibility_record = read_compatibility_record(
            store,
            provider=provider,
            model_id=model_id,
            task_name=TASK_TRANSCRIPT_ANALYSIS,
        )
        if (
            compatibility_record is not None
            and compatibility_record.compatibility_status in allowed_statuses
        ):
            selected_models.append(model_id)

    return selected_models


def _record_discovered_models(provider: str, model_ids: list[str]) -> None:
    store = load_model_intelligence_store()
    adapter = get_provider_adapter(provider)

    for model_id in model_ids:
        capability = adapter.get_model_capability(model_id)
        classification = classify_capability_result(
            provider=provider,
            model_id=model_id,
            task_name=TASK_TRANSCRIPT_ANALYSIS,
            can_list_models=capability.can_list_models,
            can_analyze_transcript=capability.can_analyze_transcript,
            capability_notes=capability.notes,
        )
        classification = _merge_existing_classification(provider, model_id, capability, classification)
        upsert_catalog_record(
            store,
            provider=provider,
            model_id=model_id,
            source="provider_api",
            notes=None,
            hidden_from_ui=False,
        )
        upsert_compatibility_record(
            store,
            provider=provider,
            model_id=model_id,
            task_name=TASK_TRANSCRIPT_ANALYSIS,
            can_list_models=capability.can_list_models,
            can_analyze_transcript=capability.can_analyze_transcript,
            compatibility_status=classification.compatibility_status,
            blocked_reason=classification.blocked_reason,
            fix_hint=classification.fix_hint,
            last_error_type=classification.last_error_type,
            last_error_message=classification.last_error_message,
        )

    save_model_intelligence_store(store)


def _record_compatibility_snapshot(provider: str, model_id: str | None, capability: ModelCapability) -> None:
    cleaned_model_id = (model_id or "").strip()
    if not cleaned_model_id:
        return

    store = load_model_intelligence_store()
    classification = classify_capability_result(
        provider=provider,
        model_id=cleaned_model_id,
        task_name=TASK_TRANSCRIPT_ANALYSIS,
        can_list_models=capability.can_list_models,
        can_analyze_transcript=capability.can_analyze_transcript,
        capability_notes=capability.notes,
    )
    classification = _merge_existing_classification(provider, cleaned_model_id, capability, classification)
    upsert_compatibility_record(
        store,
        provider=provider,
        model_id=cleaned_model_id,
        task_name=TASK_TRANSCRIPT_ANALYSIS,
        can_list_models=capability.can_list_models,
        can_analyze_transcript=capability.can_analyze_transcript,
        compatibility_status=classification.compatibility_status,
        blocked_reason=classification.blocked_reason,
        fix_hint=classification.fix_hint,
        last_error_type=classification.last_error_type,
        last_error_message=classification.last_error_message,
    )
    save_model_intelligence_store(store)


def load_visible_model_ids(provider: str, config: AppConfig) -> list[str]:
    """Fetch visible model IDs for the selected provider."""

    adapter = get_provider_adapter(provider)
    try:
        model_ids = adapter.list_models(config)
    except ProviderError as exc:
        raise ModelCatalogError(str(exc)) from exc

    _record_discovered_models(provider, model_ids)
    return model_ids


def build_model_buckets(provider: str, model_ids: list[str]) -> dict[str, list[str]]:
    """Build UI filter buckets for the selected provider."""

    adapter = get_provider_adapter(provider)
    buckets = adapter.build_model_buckets(model_ids)
    buckets[FILTER_RECOMMENDED] = _build_models_by_status(
        provider,
        model_ids,
        {COMPATIBILITY_STATUS_SUPPORTED},
    )
    buckets[FILTER_FIXABLE] = _build_fixable_models(provider, model_ids)
    return buckets


def build_fallback_model_buckets(provider: str) -> dict[str, list[str]]:
    """Build fallback UI filter buckets for the selected provider."""

    adapter = get_provider_adapter(provider)
    fallback_model_ids = list(adapter.fallback_model_ids)
    buckets = adapter.build_model_buckets(adapter.fallback_model_ids)
    buckets[FILTER_RECOMMENDED] = _build_models_by_status(
        provider,
        fallback_model_ids,
        {COMPATIBILITY_STATUS_SUPPORTED},
    )
    buckets[FILTER_FIXABLE] = _build_fixable_models(provider, fallback_model_ids)
    return buckets


def get_model_capability(provider: str, model_id: str | None) -> ModelCapability:
    """Return capabilities for the selected provider/model path."""

    adapter = get_provider_adapter(provider)
    capability = adapter.get_model_capability(model_id)
    _record_compatibility_snapshot(provider, model_id, capability)
    return capability
