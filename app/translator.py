"""Shared raw-response transcript prompts."""

from __future__ import annotations

SYSTEM_PROMPT = """You review software-planning conversations and produce a helpful raw analysis.

Do not assume a fixed schema.
You may answer in plain text, markdown, bullets, or JSON if you choose.
Preserve important goals, tasks, decisions, constraints, and open questions when relevant.
Do not invent unsupported facts."""


def build_transcript_extraction_messages(conversation_text: str) -> list[dict[str, str]]:
    """Build shared raw-review messages for provider adapters."""

    cleaned_conversation = conversation_text.strip()
    if not cleaned_conversation:
        raise ValueError("The conversation transcript is empty.")

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "Review the following conversation transcript.\n"
                "Return your best raw analysis for human review.\n"
                "Transcript:\n"
                f"{cleaned_conversation}"
            ),
        },
    ]
