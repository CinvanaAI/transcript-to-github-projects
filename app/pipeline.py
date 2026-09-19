"""Shared pipeline for the CLI and desktop UI."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

from .config import AppConfig, load_config
from .github_projects import create_project_with_draft_items
from .model_intelligence import (
    TASK_TRANSCRIPT_ANALYSIS,
    classify_exception_result,
    load_model_intelligence_store,
    read_compatibility_record,
    save_model_intelligence_store,
    upsert_compatibility_record,
)
from .providers import PROVIDER_OPENAI, get_provider_adapter


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT_PATH = PROJECT_ROOT / "input" / "conversation.txt"
OUTPUT_PATH = PROJECT_ROOT / "output" / "raw_model_response.txt"
BATCH_RUNS_PATH = PROJECT_ROOT / "output" / "batch_runs"

StatusCallback = Callable[[str], None]


class PipelineExecutionError(RuntimeError):
    """Raised when the pipeline fails after writing an output file."""

    def __init__(self, message: str, *, output_saved: bool, output_path: Path | None) -> None:
        super().__init__(message)
        self.output_saved = output_saved
        self.output_path = output_path


@dataclass(frozen=True)
class PipelineResult:
    """Successful raw-response pipeline output metadata."""

    provider_name: str
    model_id: str
    raw_response_text: str
    saved_response_path: Path
    response_char_count: int


@dataclass(frozen=True)
class AnalysisResult:
    """Raw model output that is ready for human review."""

    provider_name: str
    model_id: str
    raw_response_text: str
    saved_response_path: Path
    response_char_count: int


@dataclass(frozen=True)
class PublishResult:
    """GitHub metadata returned after publishing draft items."""

    project_id: str
    project_url: str | None
    items_added: int
    project_title: str
    owner_login: str
    owner_type: str
    draft_item_ids: list[str]


@dataclass(frozen=True)
class BatchAnalysisModelResult:
    """Per-model batch analysis result metadata."""

    model_id: str
    success: bool
    saved_response_path: Path | None
    response_char_count: int
    compatibility_status: str
    blocked_reason: str | None
    fix_hint: str | None
    error_type: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class BatchAnalysisResult:
    """Batch analysis summary and output metadata."""

    provider_name: str
    model_filter_name: str
    transcript_path: Path
    report_path: Path
    batch_output_dir: Path
    models_attempted: int
    models_succeeded: int
    models_failed: int
    compatibility_counts: dict[str, int]
    model_results: list[BatchAnalysisModelResult]


def _emit_status(status_callback: StatusCallback | None, message: str) -> None:
    if status_callback is not None:
        status_callback(message)


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _slugify_filename(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return slug.strip("._") or "model"


def _read_conversation(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Conversation transcript not found: {path}")

    content = path.read_text(encoding="utf-8").strip()
    if not content:
        raise ValueError(f"Conversation transcript is empty: {path}")

    return content


def _save_raw_response(raw_response_text: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(raw_response_text, encoding="utf-8")


def _save_batch_report(data: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _apply_overrides(
    config: AppConfig,
    model_override: str | None,
    github_owner_override: str | None,
) -> AppConfig:
    updated_config = config

    cleaned_model = (model_override or "").strip()
    if cleaned_model:
        updated_config = replace(updated_config, openai_model=cleaned_model)

    cleaned_owner = (github_owner_override or "").strip()
    if cleaned_owner:
        updated_config = replace(updated_config, github_owner=cleaned_owner)

    return updated_config


def _record_analysis_compatibility(
    *,
    provider_name: str,
    model_id: str,
    can_list_models: bool,
    can_analyze_transcript: bool,
    classification_status: str,
    blocked_reason: str | None = None,
    fix_hint: str | None = None,
    last_error_type: str | None = None,
    last_error_message: str | None = None,
) -> None:
    store = load_model_intelligence_store()
    upsert_compatibility_record(
        store,
        provider=provider_name,
        model_id=model_id,
        task_name=TASK_TRANSCRIPT_ANALYSIS,
        can_list_models=can_list_models,
        can_analyze_transcript=can_analyze_transcript,
        compatibility_status=classification_status,
        blocked_reason=blocked_reason,
        fix_hint=fix_hint,
        last_error_type=last_error_type,
        last_error_message=last_error_message,
    )
    save_model_intelligence_store(store)


def analyze_transcript(
    transcript_path: str | Path,
    provider_name: str = PROVIDER_OPENAI,
    model_override: str | None = None,
    output_path: str | Path | None = None,
    status_callback: StatusCallback | None = None,
) -> AnalysisResult:
    """Analyze a transcript locally and save raw model output."""

    _emit_status(status_callback, "Loading config...")
    config = load_config(
        require_openai_api_key=False,
        require_github_token=False,
        require_github_owner=False,
    )
    config = _apply_overrides(config, model_override, None)
    provider = get_provider_adapter(provider_name)
    selected_model = (model_override or "").strip() or config.openai_model
    capability = provider.get_model_capability(selected_model)

    _emit_status(status_callback, "Reading transcript...")
    conversation_text = _read_conversation(Path(transcript_path))

    _emit_status(status_callback, "Sending transcript to model...")
    try:
        raw_response_text = provider.analyze_transcript(conversation_text, selected_model, config)
    except Exception as exc:
        classification = classify_exception_result(
            provider=provider_name,
            model_id=selected_model,
            task_name=TASK_TRANSCRIPT_ANALYSIS,
            exception_type=type(exc).__name__,
            exception_message=str(exc),
            capability_notes=capability.notes,
        )
        _record_analysis_compatibility(
            provider_name=provider_name,
            model_id=selected_model,
            can_list_models=capability.can_list_models,
            can_analyze_transcript=False,
            classification_status=classification.compatibility_status,
            blocked_reason=classification.blocked_reason,
            fix_hint=classification.fix_hint,
            last_error_type=classification.last_error_type,
            last_error_message=classification.last_error_message,
        )
        raise

    if not raw_response_text.strip():
        classification = classify_exception_result(
            provider=provider_name,
            model_id=selected_model,
            task_name=TASK_TRANSCRIPT_ANALYSIS,
            exception_type="EmptyResponseError",
            exception_message="The model returned an empty response.",
            capability_notes=capability.notes,
        )
        _record_analysis_compatibility(
            provider_name=provider_name,
            model_id=selected_model,
            can_list_models=capability.can_list_models,
            can_analyze_transcript=False,
            classification_status=classification.compatibility_status,
            blocked_reason=classification.blocked_reason,
            fix_hint=classification.fix_hint,
            last_error_type=classification.last_error_type,
            last_error_message=classification.last_error_message,
        )
        raise RuntimeError("The model returned an empty response.")

    _record_analysis_compatibility(
        provider_name=provider_name,
        model_id=selected_model,
        can_list_models=capability.can_list_models,
        can_analyze_transcript=True,
        classification_status="supported",
        blocked_reason=None,
        fix_hint=None,
        last_error_type=None,
        last_error_message=None,
    )

    _emit_status(status_callback, "Saving raw response...")
    saved_response_path = Path(output_path) if output_path is not None else OUTPUT_PATH
    _save_raw_response(raw_response_text, saved_response_path)

    _emit_status(status_callback, "Analysis complete.")

    return AnalysisResult(
        provider_name=provider_name,
        model_id=selected_model,
        raw_response_text=raw_response_text,
        saved_response_path=saved_response_path,
        response_char_count=len(raw_response_text),
    )


def _read_current_compatibility(provider_name: str, model_id: str) -> tuple[str, str | None, str | None]:
    store = load_model_intelligence_store()
    compatibility_record = read_compatibility_record(
        store,
        provider=provider_name,
        model_id=model_id,
        task_name=TASK_TRANSCRIPT_ANALYSIS,
    )
    if compatibility_record is None:
        return ("unknown", None, None)

    return (
        compatibility_record.compatibility_status,
        compatibility_record.blocked_reason,
        compatibility_record.fix_hint,
    )


def batch_analyze_transcript(
    transcript_path: str | Path,
    provider_name: str,
    model_filter_name: str,
    model_ids: Sequence[str],
    status_callback: StatusCallback | None = None,
) -> BatchAnalysisResult:
    """Run transcript analysis once for each provided model without publishing."""

    cleaned_model_ids = [model_id.strip() for model_id in model_ids if model_id.strip()]
    if not cleaned_model_ids:
        raise ValueError("No models are available in the selected filter bucket.")

    transcript_path_obj = Path(transcript_path)
    run_id = _utc_timestamp()
    batch_output_dir = BATCH_RUNS_PATH / run_id
    report_path = PROJECT_ROOT / "output" / f"batch_report_{run_id}.json"

    _emit_status(
        status_callback,
        (
            f"Starting batch analysis for {len(cleaned_model_ids)} model(s) "
            f"in {model_filter_name}."
        ),
    )

    model_results: list[BatchAnalysisModelResult] = []
    compatibility_counts = {
        "supported": 0,
        "unsupported": 0,
        "fixable": 0,
        "unknown": 0,
    }

    for index, model_id in enumerate(cleaned_model_ids, start=1):
        _emit_status(
            status_callback,
            f"[{index}/{len(cleaned_model_ids)}] Batch analyzing {model_id}...",
        )
        model_output_path = batch_output_dir / f"{index:02d}_{_slugify_filename(model_id)}.txt"

        try:
            analysis_result = analyze_transcript(
                transcript_path=transcript_path_obj,
                provider_name=provider_name,
                model_override=model_id,
                output_path=model_output_path,
                status_callback=lambda message, current_model=model_id: _emit_status(
                    status_callback,
                    f"[{current_model}] {message}",
                ),
            )
        except Exception as exc:
            compatibility_status, blocked_reason, fix_hint = _read_current_compatibility(
                provider_name,
                model_id,
            )
            compatibility_counts[compatibility_status] = compatibility_counts.get(compatibility_status, 0) + 1
            model_results.append(
                BatchAnalysisModelResult(
                    model_id=model_id,
                    success=False,
                    saved_response_path=None,
                    response_char_count=0,
                    compatibility_status=compatibility_status,
                    blocked_reason=blocked_reason,
                    fix_hint=fix_hint,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                )
            )
            _emit_status(
                status_callback,
                f"[{model_id}] Failed: {type(exc).__name__}: {exc}",
            )
            continue

        compatibility_status, blocked_reason, fix_hint = _read_current_compatibility(
            provider_name,
            model_id,
        )
        compatibility_counts[compatibility_status] = compatibility_counts.get(compatibility_status, 0) + 1
        model_results.append(
            BatchAnalysisModelResult(
                model_id=model_id,
                success=True,
                saved_response_path=analysis_result.saved_response_path,
                response_char_count=analysis_result.response_char_count,
                compatibility_status=compatibility_status,
                blocked_reason=blocked_reason,
                fix_hint=fix_hint,
            )
        )
        _emit_status(
            status_callback,
            f"[{model_id}] Saved batch output: {analysis_result.saved_response_path}",
        )

    models_succeeded = sum(1 for result in model_results if result.success)
    models_failed = len(model_results) - models_succeeded

    report_payload = {
        "batch_run_id": run_id,
        "provider_name": provider_name,
        "model_filter_name": model_filter_name,
        "transcript_path": str(transcript_path_obj),
        "batch_output_dir": str(batch_output_dir),
        "models_attempted": len(cleaned_model_ids),
        "models_succeeded": models_succeeded,
        "models_failed": models_failed,
        "compatibility_counts": compatibility_counts,
        "results": [
            {
                **asdict(result),
                "saved_response_path": (
                    str(result.saved_response_path) if result.saved_response_path is not None else None
                ),
            }
            for result in model_results
        ],
    }
    _save_batch_report(report_payload, report_path)

    _emit_status(
        status_callback,
        (
            f"Batch complete. Succeeded: {models_succeeded}, failed: {models_failed}, "
            f"supported={compatibility_counts['supported']}, "
            f"unsupported={compatibility_counts['unsupported']}, "
            f"fixable={compatibility_counts['fixable']}, "
            f"unknown={compatibility_counts['unknown']}."
        ),
    )

    return BatchAnalysisResult(
        provider_name=provider_name,
        model_filter_name=model_filter_name,
        transcript_path=transcript_path_obj,
        report_path=report_path,
        batch_output_dir=batch_output_dir,
        models_attempted=len(cleaned_model_ids),
        models_succeeded=models_succeeded,
        models_failed=models_failed,
        compatibility_counts=compatibility_counts,
        model_results=model_results,
    )


def publish_project_to_github(
    project_data: dict[str, Any],
    github_owner_override: str | None = None,
    status_callback: StatusCallback | None = None,
) -> PublishResult:
    """Publish previously structured project data to GitHub Projects V2."""

    cleaned_owner_override = (github_owner_override or "").strip()

    config = load_config(
        require_openai_api_key=False,
        require_github_token=True,
        require_github_owner=not bool(cleaned_owner_override),
    )
    config = _apply_overrides(config, None, cleaned_owner_override)

    _emit_status(status_callback, "Creating GitHub Project...")
    github_result = create_project_with_draft_items(project_data, config)
    _emit_status(status_callback, "Done.")

    return PublishResult(
        project_id=github_result["project_id"],
        project_url=github_result.get("project_url"),
        items_added=github_result["items_added"],
        project_title=github_result["project_title"],
        owner_login=github_result["owner_login"],
        owner_type=github_result["owner_type"],
        draft_item_ids=list(github_result["draft_item_ids"]),
    )


def run_pipeline(
    transcript_path: str | Path,
    provider_name: str = PROVIDER_OPENAI,
    model_override: str | None = None,
    github_owner_override: str | None = None,
    status_callback: StatusCallback | None = None,
) -> PipelineResult:
    """Run the raw-response analysis pipeline up to the review boundary."""

    analysis_result = analyze_transcript(
        transcript_path=transcript_path,
        provider_name=provider_name,
        model_override=model_override,
        status_callback=status_callback,
    )

    return PipelineResult(
        provider_name=analysis_result.provider_name,
        model_id=analysis_result.model_id,
        raw_response_text=analysis_result.raw_response_text,
        saved_response_path=analysis_result.saved_response_path,
        response_char_count=analysis_result.response_char_count,
    )
