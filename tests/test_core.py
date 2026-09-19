from __future__ import annotations

import json

import pytest

from app.config import AppConfig
from app.github_projects import _format_draft_item, create_project_with_draft_items
from app.main import main as cli_main
from app.model_intelligence.pricing import (
    SEEDED_OPENAI_PRICING_UPDATED_AT,
    load_pricing_registry,
    read_pricing_record,
    refresh_pricing_registry,
)
from app.providers.base import ProviderError
from app.providers.openai_provider import _extract_response_text
from app.schema import SchemaValidationError, validate_project_data
from app.token_estimation import estimate_transcript_analysis_tokens
from app.translator import build_transcript_extraction_messages


def _config() -> AppConfig:
    return AppConfig(
        openai_api_key="",
        openai_model="gpt-test",
        github_token="test-token",
        github_owner="example-lab",
        ollama_local_base_url="http://localhost:11434",
        ollama_cloud_base_url="https://ollama.com",
        ollama_api_key="",
    )


def _project_data() -> dict[str, object]:
    return {
        "project_title": "Offline Review Queue",
        "project_description": "Turn reviewed findings into draft work items.",
        "source_summary": "A synthetic planning transcript.",
        "items": [
            {
                "type": "Task",
                "title": "Add a review gate",
                "body": "Require a person to approve the draft.",
                "priority": "High",
                "confidence": "High",
                "phase": "V1",
                "needs_review": True,
            }
        ],
    }


def test_translator_rejects_blank_input_and_preserves_transcript() -> None:
    with pytest.raises(ValueError):
        build_transcript_extraction_messages("   ")

    messages = build_transcript_extraction_messages("User: keep the review boundary")
    assert messages[0]["role"] == "system"
    assert "keep the review boundary" in messages[1]["content"]


def test_schema_returns_normalized_copy() -> None:
    value = _project_data()
    value["project_title"] = "  Offline Review Queue  "
    result = validate_project_data(value)
    assert result["project_title"] == "Offline Review Queue"
    assert result["items"][0]["needs_review"] is True


def test_schema_rejects_unexpected_fields() -> None:
    value = _project_data()
    value["private_note"] = "should not silently pass"
    with pytest.raises(SchemaValidationError, match="unexpected keys"):
        validate_project_data(value)


def test_responses_api_text_extraction() -> None:
    payload = {
        "output": [
            {
                "type": "message",
                "content": [
                    {"type": "output_text", "text": "first "},
                    {"type": "output_text", "text": "second"},
                ],
            }
        ]
    }
    assert _extract_response_text(payload) == "first second"


def test_responses_api_refusal_is_explicit() -> None:
    payload = {
        "output": [
            {"type": "message", "content": [{"type": "refusal", "refusal": "No."}]}
        ]
    }
    with pytest.raises(ProviderError, match="refused"):
        _extract_response_text(payload)


def test_token_estimate_is_positive_and_additive() -> None:
    estimate = estimate_transcript_analysis_tokens("A short transcript", "OpenAI", "gpt-test")
    assert estimate.prompt_tokens > 0
    assert estimate.output_tokens >= 300
    assert estimate.total_tokens == estimate.prompt_tokens + estimate.output_tokens


def test_price_snapshot_keeps_its_historical_source_date(tmp_path) -> None:
    path = tmp_path / "pricing.json"
    refresh_pricing_registry(path)
    record = read_pricing_record(
        load_pricing_registry(path), provider="OpenAI", model_id="gpt-5-mini"
    )
    assert record is not None
    assert record.last_updated_at == SEEDED_OPENAI_PRICING_UPDATED_AT


def test_github_publisher_formats_and_sequences_requests(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_request(token: str, query: str, variables: dict[str, object]) -> dict[str, object]:
        calls.append({"token": token, "query": query, "variables": variables})
        if "ResolveOwner" in query:
            return {"user": {"id": "owner-1", "login": "example-lab"}, "organization": None}
        if "CreateProject" in query:
            return {
                "createProjectV2": {
                    "projectV2": {"id": "project-1", "title": "Offline Review Queue", "url": "https://example.invalid/project"}
                }
            }
        return {"addProjectV2DraftIssue": {"projectItem": {"id": "item-1"}}}

    monkeypatch.setattr("app.github_projects._graphql_request", fake_request)
    result = create_project_with_draft_items(_project_data(), _config())
    assert result["items_added"] == 1
    assert result["draft_item_ids"] == ["item-1"]
    assert len(calls) == 3

    title, body = _format_draft_item(
        "Description", _project_data()["items"][0]  # type: ignore[index]
    )
    assert title == "[Task] Add a review gate"
    assert "Needs Review: Yes" in body


def test_example_project_is_json_serializable() -> None:
    assert json.loads(json.dumps(_project_data()))["project_title"] == "Offline Review Queue"


def test_cli_has_standard_help(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli_main(["--help"])
    assert exc_info.value.code == 0
    output = capsys.readouterr().out
    assert "--input" in output
    assert "--provider" in output
