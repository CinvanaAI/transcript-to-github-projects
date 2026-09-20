"""Actual analysis coordinator with explicit synthetic provider/configuration."""
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
from app import pipeline
from app.config import AppConfig
from app.providers.base import ModelCapability
from app.schema import validate_project_data
from app.translator import build_transcript_extraction_messages

def demonstrate(root, raw_response=None):
    root.mkdir(parents=True, exist_ok=True)
    transcript = "User: Make a review queue. Require approval before publishing any item."
    source = root / "source.txt"
    source.write_text(transcript, encoding="utf-8")
    plan = {"project_title": "Workshop Review Queue", "project_description": "Review proposed work before publication.",
            "source_summary": "Synthetic planning request.",
            "items": [{"type": "Task", "title": "Add a review gate", "body": "Require a person to approve each draft.",
                       "priority": "High", "confidence": "High", "phase": "V1", "needs_review": True}]}
    authored_response = json.dumps(plan) if raw_response is None else raw_response
    class FixtureProvider:
        def get_model_capability(self, _):
            return ModelCapability(False, True, False, "Fixture only")
        def analyze_transcript(self, text, model, config):
            assert text == transcript
            return authored_response
    config = AppConfig("", "synthetic-model", "", "example-lab", "http://localhost:11434", "https://ollama.com", "")
    observed = []
    with patch.object(pipeline, "load_config", lambda **_: config), \
         patch.object(pipeline, "get_provider_adapter", lambda _: FixtureProvider()), \
         patch.object(pipeline, "_record_analysis_compatibility", lambda **row: observed.append(row)):
        result = pipeline.analyze_transcript(source, model_override="synthetic-model", output_path=root / "response.txt")
    saved = (root / "response.txt").read_text(encoding="utf-8")
    assert saved == authored_response == result.raw_response_text
    try:
        structured = validate_project_data(json.loads(saved))
        schema = {"passed": True, "project_title": structured["project_title"]}
    except (ValueError, TypeError) as error:
        schema = {"passed": False, "error_type": type(error).__name__}
    return {"mode": "Actual coordinator; explicitly authored fixture response",
            "source": transcript, "request_messages": build_transcript_extraction_messages(transcript),
            "captured_raw_response": saved, "raw_preserved_exactly": True,
            "schema_validation": schema, "compatibility_status": observed[0]["classification_status"],
            "human_approval_performed": False, "published": False, "network_calls": 0}

if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="transcript-case-") as scratch:
        root = Path(scratch)
        structured = demonstrate(root / "structured")
        prose = demonstrate(root / "prose", "The conversation asks for a review queue with explicit approval before publication.")
        assert structured["schema_validation"]["passed"]
        assert not prose["schema_validation"]["passed"] and prose["raw_preserved_exactly"]
        assert prose["compatibility_status"] == "supported"
        print(json.dumps({"structured_fixture": structured, "raw_prose_fixture": prose}, indent=2))
