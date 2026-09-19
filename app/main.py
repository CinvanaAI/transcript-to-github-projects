"""CLI entry point for the shared pipeline."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from .pipeline import DEFAULT_INPUT_PATH, PipelineResult, run_pipeline
from .providers import PROVIDER_OPENAI, PROVIDER_OPTIONS


def _print_success_summary(result: PipelineResult) -> None:
    print("Success")
    print(f"Provider: {result.provider_name}")
    print(f"Model: {result.model_id}")
    print(f"Saved raw response: {result.saved_response_path}")
    print(f"Response characters: {result.response_char_count}")


def _print_failure_summary(exc: Exception) -> None:
    print("Failure")
    print(f"Error: {type(exc).__name__}: {exc}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Analyze one local transcript and save the raw model response for review."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT_PATH,
        help=f"Transcript path (default: {DEFAULT_INPUT_PATH})",
    )
    parser.add_argument(
        "--provider",
        choices=PROVIDER_OPTIONS,
        default=PROVIDER_OPENAI,
        help="Model provider adapter",
    )
    parser.add_argument("--model", help="Optional provider model override")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = run_pipeline(
            args.input,
            provider_name=args.provider,
            model_override=args.model,
        )
    except Exception as exc:
        _print_failure_summary(exc)
        return 1

    _print_success_summary(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
