"""JSON-backed model pricing registry helpers."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_PRICING_PATH = PROJECT_ROOT / "output" / "model_pricing.json"
SEEDED_OPENAI_PRICING_SOURCE = "official_openai_pricing_page"
SEEDED_OPENAI_PRICING_UPDATED_AT = "2026-03-10T00:00:00+00:00"
PRICING_STALE_AFTER_DAYS = 7


@dataclass(frozen=True)
class PricingRecord:
    """Provider/model pricing metadata."""

    provider: str
    model_id: str
    input_cost_per_1m_tokens: float
    cached_input_cost_per_1m_tokens: float | None
    output_cost_per_1m_tokens: float
    source: str
    last_updated_at: str
    notes: str | None = None


@dataclass(frozen=True)
class CostEstimate:
    """Estimated costs for a token estimate."""

    input_cost: float
    output_cost: float
    total_cost: float


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


SEEDED_PRICING_RECORDS = (
    PricingRecord(
        provider="OpenAI",
        model_id="gpt-4o-mini",
        input_cost_per_1m_tokens=0.15,
        cached_input_cost_per_1m_tokens=0.075,
        output_cost_per_1m_tokens=0.60,
        source=SEEDED_OPENAI_PRICING_SOURCE,
        last_updated_at=SEEDED_OPENAI_PRICING_UPDATED_AT,
        notes="Seeded from the official OpenAI pricing page for local cost estimates.",
    ),
    PricingRecord(
        provider="OpenAI",
        model_id="gpt-5-mini",
        input_cost_per_1m_tokens=0.25,
        cached_input_cost_per_1m_tokens=0.025,
        output_cost_per_1m_tokens=2.00,
        source=SEEDED_OPENAI_PRICING_SOURCE,
        last_updated_at=SEEDED_OPENAI_PRICING_UPDATED_AT,
        notes="Seeded from the official OpenAI pricing page for local cost estimates.",
    ),
    PricingRecord(
        provider="OpenAI",
        model_id="gpt-5.4",
        input_cost_per_1m_tokens=2.50,
        cached_input_cost_per_1m_tokens=0.25,
        output_cost_per_1m_tokens=15.00,
        source=SEEDED_OPENAI_PRICING_SOURCE,
        last_updated_at=SEEDED_OPENAI_PRICING_UPDATED_AT,
        notes="Seeded from the official OpenAI pricing page for local cost estimates.",
    ),
)


def initialize_missing_pricing_sections(
    registry: dict[str, Any] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Initialize all expected pricing registry sections safely."""

    normalized: dict[str, list[dict[str, Any]]] = {}
    raw_registry = registry if isinstance(registry, dict) else {}

    records = raw_registry.get("records")
    normalized["records"] = records if isinstance(records, list) else []

    return normalized


def load_pricing_registry(path: Path = DEFAULT_PRICING_PATH) -> dict[str, list[dict[str, Any]]]:
    """Load the JSON-backed pricing registry."""

    if not path.exists():
        return initialize_missing_pricing_sections()

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return initialize_missing_pricing_sections()

    return initialize_missing_pricing_sections(payload)


def save_pricing_registry(
    registry: dict[str, list[dict[str, Any]]],
    path: Path = DEFAULT_PRICING_PATH,
) -> Path:
    """Save the JSON-backed pricing registry."""

    normalized_registry = initialize_missing_pricing_sections(registry)
    path.parent.mkdir(parents=True, exist_ok=True)
    previous_contents = path.read_text(encoding="utf-8") if path.exists() else None

    try:
        path.write_text(json.dumps(normalized_registry, indent=2) + "\n", encoding="utf-8")
    except Exception:
        if previous_contents is not None:
            path.write_text(previous_contents, encoding="utf-8")
        raise

    return path


def _find_record_index(records: list[dict[str, Any]], *, provider: str, model_id: str) -> int | None:
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            continue
        if record.get("provider") == provider and record.get("model_id") == model_id:
            return index
    return None


def upsert_pricing_record(
    registry: dict[str, list[dict[str, Any]]],
    *,
    provider: str,
    model_id: str,
    input_cost_per_1m_tokens: float,
    cached_input_cost_per_1m_tokens: float | None,
    output_cost_per_1m_tokens: float,
    source: str,
    last_updated_at: str,
    notes: str | None = None,
) -> None:
    """Insert or update a pricing record."""

    normalized_registry = initialize_missing_pricing_sections(registry)
    records = normalized_registry["records"]
    record_index = _find_record_index(records, provider=provider, model_id=model_id)

    record = PricingRecord(
        provider=provider,
        model_id=model_id,
        input_cost_per_1m_tokens=input_cost_per_1m_tokens,
        cached_input_cost_per_1m_tokens=cached_input_cost_per_1m_tokens,
        output_cost_per_1m_tokens=output_cost_per_1m_tokens,
        source=source,
        last_updated_at=last_updated_at,
        notes=notes,
    )

    if record_index is None:
        records.append(asdict(record))
    else:
        records[record_index] = asdict(record)

    registry.clear()
    registry.update(normalized_registry)


def read_pricing_record(
    registry: dict[str, list[dict[str, Any]]],
    *,
    provider: str,
    model_id: str,
) -> PricingRecord | None:
    """Read a pricing record for a provider/model path."""

    normalized_registry = initialize_missing_pricing_sections(registry)
    records = normalized_registry["records"]
    record_index = _find_record_index(records, provider=provider, model_id=model_id)
    if record_index is None:
        return None

    record = records[record_index]
    return PricingRecord(
        provider=str(record.get("provider", provider)),
        model_id=str(record.get("model_id", model_id)),
        input_cost_per_1m_tokens=float(record.get("input_cost_per_1m_tokens", 0.0)),
        cached_input_cost_per_1m_tokens=(
            float(record["cached_input_cost_per_1m_tokens"])
            if record.get("cached_input_cost_per_1m_tokens") is not None
            else None
        ),
        output_cost_per_1m_tokens=float(record.get("output_cost_per_1m_tokens", 0.0)),
        source=str(record.get("source", "")),
        last_updated_at=str(record.get("last_updated_at", "")),
        notes=record.get("notes"),
    )


def seed_default_pricing_records(
    registry: dict[str, list[dict[str, Any]]],
    *,
    refreshed_at: str | None = None,
) -> None:
    """Seed the local registry with the built-in pricing records used by this project."""

    timestamp = refreshed_at or SEEDED_OPENAI_PRICING_UPDATED_AT

    for seeded_record in SEEDED_PRICING_RECORDS:
        upsert_pricing_record(
            registry,
            provider=seeded_record.provider,
            model_id=seeded_record.model_id,
            input_cost_per_1m_tokens=seeded_record.input_cost_per_1m_tokens,
            cached_input_cost_per_1m_tokens=seeded_record.cached_input_cost_per_1m_tokens,
            output_cost_per_1m_tokens=seeded_record.output_cost_per_1m_tokens,
            source=seeded_record.source,
            last_updated_at=timestamp,
            notes=seeded_record.notes,
        )


def refresh_pricing_registry(path: Path = DEFAULT_PRICING_PATH) -> Path:
    """Load the dated built-in pricing snapshot into the local registry.

    This never presents the bundled historical rates as freshly fetched data.
    Direct source-backed refresh can be added later without changing callers.
    """

    registry = load_pricing_registry(path)
    seed_default_pricing_records(registry)
    return save_pricing_registry(registry, path)


def is_pricing_record_stale(
    pricing_record: PricingRecord,
    *,
    max_age_days: int = PRICING_STALE_AFTER_DAYS,
) -> bool:
    """Return True when pricing data is older than the allowed age."""

    try:
        updated_at = datetime.fromisoformat(pricing_record.last_updated_at)
    except ValueError:
        return True

    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)

    return datetime.now(timezone.utc) - updated_at > timedelta(days=max_age_days)


def estimate_token_costs(
    pricing_record: PricingRecord,
    *,
    prompt_tokens: int,
    output_tokens: int,
) -> CostEstimate:
    """Estimate input/output/total costs for a token estimate."""

    input_cost = (prompt_tokens / 1_000_000) * pricing_record.input_cost_per_1m_tokens
    output_cost = (output_tokens / 1_000_000) * pricing_record.output_cost_per_1m_tokens
    return CostEstimate(
        input_cost=input_cost,
        output_cost=output_cost,
        total_cost=input_cost + output_cost,
    )
