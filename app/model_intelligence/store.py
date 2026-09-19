"""JSON-backed model intelligence store."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_STORE_PATH = PROJECT_ROOT / "output" / "model_intelligence.json"
TASK_TRANSCRIPT_ANALYSIS = "transcript_analysis"

COMPATIBILITY_STATUS_SUPPORTED = "supported"
COMPATIBILITY_STATUS_UNSUPPORTED = "unsupported"
COMPATIBILITY_STATUS_FIXABLE = "fixable"
COMPATIBILITY_STATUS_UNKNOWN = "unknown"
COMPATIBILITY_STATUSES = (
    COMPATIBILITY_STATUS_SUPPORTED,
    COMPATIBILITY_STATUS_UNSUPPORTED,
    COMPATIBILITY_STATUS_FIXABLE,
    COMPATIBILITY_STATUS_UNKNOWN,
)


@dataclass(frozen=True)
class CatalogRecord:
    """Discovered model metadata."""

    provider: str
    model_id: str
    discovered_at: str
    last_seen_at: str
    source: str
    notes: str | None = None
    hidden_from_ui: bool = False


@dataclass(frozen=True)
class CompatibilityRecord:
    """Provider/model/task compatibility metadata."""

    provider: str
    model_id: str
    task_name: str
    can_list_models: bool
    can_analyze_transcript: bool
    compatibility_status: str
    blocked_reason: str | None = None
    fix_hint: str | None = None
    last_checked_at: str | None = None
    last_error_type: str | None = None
    last_error_message: str | None = None


@dataclass(frozen=True)
class BehaviorRecord:
    """Placeholder for future behavior review notes."""

    provider: str
    model_id: str
    task_name: str
    quality_notes: str | None = None
    last_behavior_reviewed_at: str | None = None


@dataclass(frozen=True)
class SuitabilityRecord:
    """Placeholder for future suitability preferences."""

    provider: str
    model_id: str
    task_name: str
    cost_tier: str | None = None
    speed_tier: str | None = None
    recommended_role: str | None = None
    manual_preference: str | None = None
    active_for_default_use: bool = False


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def initialize_missing_store_sections(store: dict[str, Any] | None = None) -> dict[str, list[dict[str, Any]]]:
    """Initialize all expected store sections safely."""

    normalized: dict[str, list[dict[str, Any]]] = {}
    raw_store = store if isinstance(store, dict) else {}

    for section_name in ("catalog", "compatibility", "behavior", "suitability"):
        section_value = raw_store.get(section_name)
        normalized[section_name] = section_value if isinstance(section_value, list) else []

    return normalized


def load_model_intelligence_store(path: Path = DEFAULT_STORE_PATH) -> dict[str, list[dict[str, Any]]]:
    """Load the JSON-backed model intelligence store."""

    if not path.exists():
        return initialize_missing_store_sections()

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return initialize_missing_store_sections()

    return initialize_missing_store_sections(payload)


def save_model_intelligence_store(
    store: dict[str, list[dict[str, Any]]],
    path: Path = DEFAULT_STORE_PATH,
) -> Path:
    """Save the JSON-backed model intelligence store."""

    normalized_store = initialize_missing_store_sections(store)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(normalized_store, indent=2) + "\n", encoding="utf-8")
    except OSError:
        return path
    return path


def _find_record_index(records: list[dict[str, Any]], **keys: str) -> int | None:
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            continue
        if all(record.get(key_name) == key_value for key_name, key_value in keys.items()):
            return index
    return None


def upsert_catalog_record(
    store: dict[str, list[dict[str, Any]]],
    *,
    provider: str,
    model_id: str,
    source: str,
    notes: str | None = None,
    hidden_from_ui: bool = False,
    seen_at: str | None = None,
) -> None:
    """Insert or update a catalog record."""

    normalized_store = initialize_missing_store_sections(store)
    timestamp = seen_at or _utc_now()
    records = normalized_store["catalog"]
    record_index = _find_record_index(records, provider=provider, model_id=model_id)

    discovered_at = timestamp
    if record_index is not None:
        existing_record = records[record_index]
        discovered_at = str(existing_record.get("discovered_at") or timestamp)

    record = CatalogRecord(
        provider=provider,
        model_id=model_id,
        discovered_at=discovered_at,
        last_seen_at=timestamp,
        source=source,
        notes=notes,
        hidden_from_ui=hidden_from_ui,
    )

    if record_index is None:
        records.append(asdict(record))
    else:
        records[record_index] = asdict(record)

    store.clear()
    store.update(normalized_store)


def upsert_compatibility_record(
    store: dict[str, list[dict[str, Any]]],
    *,
    provider: str,
    model_id: str,
    task_name: str,
    can_list_models: bool,
    can_analyze_transcript: bool,
    compatibility_status: str,
    blocked_reason: str | None = None,
    fix_hint: str | None = None,
    last_checked_at: str | None = None,
    last_error_type: str | None = None,
    last_error_message: str | None = None,
) -> None:
    """Insert or update a compatibility record."""

    normalized_store = initialize_missing_store_sections(store)
    records = normalized_store["compatibility"]
    record_index = _find_record_index(
        records,
        provider=provider,
        model_id=model_id,
        task_name=task_name,
    )

    status = (
        compatibility_status
        if compatibility_status in COMPATIBILITY_STATUSES
        else COMPATIBILITY_STATUS_UNKNOWN
    )
    record = CompatibilityRecord(
        provider=provider,
        model_id=model_id,
        task_name=task_name,
        can_list_models=can_list_models,
        can_analyze_transcript=can_analyze_transcript,
        compatibility_status=status,
        blocked_reason=blocked_reason,
        fix_hint=fix_hint,
        last_checked_at=last_checked_at or _utc_now(),
        last_error_type=last_error_type,
        last_error_message=last_error_message,
    )

    if record_index is None:
        records.append(asdict(record))
    else:
        records[record_index] = asdict(record)

    store.clear()
    store.update(normalized_store)


def clear_compatibility_records_for_task(
    store: dict[str, list[dict[str, Any]]],
    *,
    task_name: str,
) -> int:
    """Remove compatibility records for a specific task and return the count."""

    normalized_store = initialize_missing_store_sections(store)
    existing_records = normalized_store["compatibility"]
    kept_records: list[dict[str, Any]] = []
    removed_count = 0

    for record in existing_records:
        if isinstance(record, dict) and record.get("task_name") == task_name:
            removed_count += 1
            continue
        kept_records.append(record)

    normalized_store["compatibility"] = kept_records
    store.clear()
    store.update(normalized_store)
    return removed_count


def clear_task_compatibility_records(
    task_name: str,
    path: Path = DEFAULT_STORE_PATH,
) -> tuple[int, Path]:
    """Clear persisted compatibility records for a specific task."""

    store = load_model_intelligence_store(path)
    removed_count = clear_compatibility_records_for_task(store, task_name=task_name)

    normalized_store = initialize_missing_store_sections(store)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(normalized_store, indent=2) + "\n", encoding="utf-8")
    return removed_count, path


def read_compatibility_record(
    store: dict[str, list[dict[str, Any]]],
    *,
    provider: str,
    model_id: str,
    task_name: str,
) -> CompatibilityRecord | None:
    """Read a compatibility record for a provider/model/task."""

    normalized_store = initialize_missing_store_sections(store)
    records = normalized_store["compatibility"]
    record_index = _find_record_index(
        records,
        provider=provider,
        model_id=model_id,
        task_name=task_name,
    )
    if record_index is None:
        return None

    record = records[record_index]
    return CompatibilityRecord(
        provider=str(record.get("provider", provider)),
        model_id=str(record.get("model_id", model_id)),
        task_name=str(record.get("task_name", task_name)),
        can_list_models=bool(record.get("can_list_models", False)),
        can_analyze_transcript=bool(record.get("can_analyze_transcript", False)),
        compatibility_status=str(record.get("compatibility_status", COMPATIBILITY_STATUS_UNKNOWN)),
        blocked_reason=record.get("blocked_reason"),
        fix_hint=record.get("fix_hint"),
        last_checked_at=record.get("last_checked_at"),
        last_error_type=record.get("last_error_type"),
        last_error_message=record.get("last_error_message"),
    )
