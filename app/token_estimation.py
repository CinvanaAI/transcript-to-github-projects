"""Local token estimation helpers for transcript analysis."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil

from .translator import build_transcript_extraction_messages


CHARS_PER_TOKEN_ESTIMATE = 4
MESSAGE_OVERHEAD_TOKENS = 8
JSON_SCHEMA_ALLOWANCE_TOKENS = 220
MIN_OUTPUT_ALLOWANCE_TOKENS = 300
MAX_OUTPUT_ALLOWANCE_TOKENS = 1600


@dataclass(frozen=True)
class TokenEstimate:
    """Estimated token counts for a transcript analysis run."""

    prompt_tokens: int
    output_tokens: int
    total_tokens: int


def _estimate_text_tokens(text: str) -> int:
    cleaned_text = text.strip()
    if not cleaned_text:
        return 0
    return max(1, ceil(len(cleaned_text) / CHARS_PER_TOKEN_ESTIMATE))


def _estimate_messages_tokens(messages: list[dict[str, str]]) -> int:
    total = 0

    for message in messages:
        role = message.get("role", "")
        content = message.get("content", "")
        total += MESSAGE_OVERHEAD_TOKENS
        total += _estimate_text_tokens(role)
        total += _estimate_text_tokens(content)

    return total


def _estimate_output_allowance(transcript_text: str) -> int:
    transcript_tokens = _estimate_text_tokens(transcript_text)
    proportional_allowance = int(transcript_tokens * 0.45)
    return max(
        MIN_OUTPUT_ALLOWANCE_TOKENS,
        min(MAX_OUTPUT_ALLOWANCE_TOKENS, proportional_allowance),
    )


def estimate_transcript_analysis_tokens(
    transcript_text: str,
    provider: str,
    model_id: str,
) -> TokenEstimate:
    """Estimate prompt/output/total tokens for transcript analysis.

    The provider and model are accepted so this interface can grow with future
    provider-specific estimation rules without changing the UI call site.
    """

    messages = build_transcript_extraction_messages(transcript_text)
    prompt_tokens = _estimate_messages_tokens(messages) + JSON_SCHEMA_ALLOWANCE_TOKENS
    output_tokens = _estimate_output_allowance(transcript_text)
    return TokenEstimate(
        prompt_tokens=prompt_tokens,
        output_tokens=output_tokens,
        total_tokens=prompt_tokens + output_tokens,
    )
