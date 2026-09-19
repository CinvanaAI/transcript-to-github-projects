"""Schema definitions and strict validation helpers."""

from __future__ import annotations

from typing import Any


ALLOWED_ITEM_TYPES = ("Epic", "Task", "Question", "Decision", "Constraint")
ALLOWED_PRIORITIES = ("High", "Medium", "Low")
ALLOWED_CONFIDENCE = ("High", "Medium", "Low")
ALLOWED_PHASES = ("V1", "V2", "Later")

TOP_LEVEL_FIELDS = (
    "project_title",
    "project_description",
    "source_summary",
    "items",
)

ITEM_FIELDS = (
    "type",
    "title",
    "body",
    "priority",
    "confidence",
    "phase",
    "needs_review",
)

OPENAI_EXTRACTION_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": list(TOP_LEVEL_FIELDS),
    "properties": {
        "project_title": {"type": "string", "minLength": 1},
        "project_description": {"type": "string", "minLength": 1},
        "source_summary": {"type": "string", "minLength": 1},
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": list(ITEM_FIELDS),
                "properties": {
                    "type": {"type": "string", "enum": list(ALLOWED_ITEM_TYPES)},
                    "title": {"type": "string", "minLength": 1},
                    "body": {"type": "string", "minLength": 1},
                    "priority": {"type": "string", "enum": list(ALLOWED_PRIORITIES)},
                    "confidence": {"type": "string", "enum": list(ALLOWED_CONFIDENCE)},
                    "phase": {"type": "string", "enum": list(ALLOWED_PHASES)},
                    "needs_review": {"type": "boolean"},
                },
            },
        },
    },
}


class SchemaValidationError(ValueError):
    """Raised when extracted project data does not match the required schema."""


def _format_path(path: str) -> str:
    return path or "root"


def _raise(path: str, message: str) -> None:
    raise SchemaValidationError(f"{_format_path(path)}: {message}")


def _validate_exact_keys(value: dict[str, Any], expected: tuple[str, ...], path: str) -> None:
    actual_keys = set(value.keys())
    expected_keys = set(expected)

    missing_keys = sorted(expected_keys - actual_keys)
    extra_keys = sorted(actual_keys - expected_keys)

    if missing_keys:
        _raise(path, f"missing required keys: {', '.join(missing_keys)}")
    if extra_keys:
        _raise(path, f"unexpected keys: {', '.join(extra_keys)}")


def _validate_non_empty_string(value: Any, path: str) -> str:
    if not isinstance(value, str):
        _raise(path, f"expected a string, got {type(value).__name__}")

    cleaned = value.strip()
    if not cleaned:
        _raise(path, "must not be empty")

    return cleaned


def _validate_enum(value: Any, allowed: tuple[str, ...], path: str) -> str:
    cleaned = _validate_non_empty_string(value, path)
    if cleaned not in allowed:
        _raise(path, f"must be one of: {', '.join(allowed)}")
    return cleaned


def _validate_item(item: Any, index: int) -> dict[str, Any]:
    path = f"items[{index}]"

    if not isinstance(item, dict):
        _raise(path, f"expected an object, got {type(item).__name__}")

    _validate_exact_keys(item, ITEM_FIELDS, path)

    needs_review = item["needs_review"]
    if not isinstance(needs_review, bool):
        _raise(f"{path}.needs_review", f"expected a boolean, got {type(needs_review).__name__}")

    return {
        "type": _validate_enum(item["type"], ALLOWED_ITEM_TYPES, f"{path}.type"),
        "title": _validate_non_empty_string(item["title"], f"{path}.title"),
        "body": _validate_non_empty_string(item["body"], f"{path}.body"),
        "priority": _validate_enum(item["priority"], ALLOWED_PRIORITIES, f"{path}.priority"),
        "confidence": _validate_enum(item["confidence"], ALLOWED_CONFIDENCE, f"{path}.confidence"),
        "phase": _validate_enum(item["phase"], ALLOWED_PHASES, f"{path}.phase"),
        "needs_review": needs_review,
    }


def validate_project_data(data: Any) -> dict[str, Any]:
    """Validate extracted project data and return a normalized copy."""

    if not isinstance(data, dict):
        _raise("", f"expected a top-level object, got {type(data).__name__}")

    _validate_exact_keys(data, TOP_LEVEL_FIELDS, "")

    items = data["items"]
    if not isinstance(items, list):
        _raise("items", f"expected an array, got {type(items).__name__}")

    validated_items = [_validate_item(item, index) for index, item in enumerate(items)]

    return {
        "project_title": _validate_non_empty_string(data["project_title"], "project_title"),
        "project_description": _validate_non_empty_string(
            data["project_description"], "project_description"
        ),
        "source_summary": _validate_non_empty_string(data["source_summary"], "source_summary"),
        "items": validated_items,
    }
