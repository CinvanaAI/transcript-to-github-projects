"""Tkinter desktop UI for the shared conversation-to-project pipeline."""

from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

from dotenv import load_dotenv

from .config import DEFAULT_OPENAI_MODEL, ENV_FILE, load_config
from .model_intelligence import (
    PRICING_STALE_AFTER_DAYS,
    TASK_TRANSCRIPT_ANALYSIS,
    clear_task_compatibility_records,
    estimate_token_costs,
    is_pricing_record_stale,
    load_pricing_registry,
    read_pricing_record,
    refresh_pricing_registry,
)
from .model_catalog import (
    FILTER_RECOMMENDED,
    MODEL_FILTER_OPTIONS,
    build_fallback_model_buckets,
    build_model_buckets,
    load_visible_model_ids,
)
from .pipeline import (
    OUTPUT_PATH,
    AnalysisResult,
    BatchAnalysisResult,
    analyze_transcript,
    batch_analyze_transcript,
)
from .providers import PROVIDER_OPENAI, PROVIDER_OPTIONS
from .token_estimation import estimate_transcript_analysis_tokens


class TranslatorApp:
    """Small Windows-friendly desktop UI for running the pipeline."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Conversation to GitHub Projects Translator")
        self.root.minsize(760, 640)

        load_dotenv(dotenv_path=ENV_FILE)

        self._env_model_name = os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL).strip() or DEFAULT_OPENAI_MODEL
        self._model_buckets_by_provider = {
            provider_name: build_fallback_model_buckets(provider_name)
            for provider_name in PROVIDER_OPTIONS
        }
        self._model_buckets = self._model_buckets_by_provider[PROVIDER_OPENAI]
        self._user_changed_model_controls = False

        self.transcript_path_var = tk.StringVar()
        self.provider_var = tk.StringVar(value=PROVIDER_OPENAI)
        self.model_filter_var = tk.StringVar(value=FILTER_RECOMMENDED)
        self.model_var = tk.StringVar()
        self.github_owner_var = tk.StringVar(value=os.getenv("GITHUB_OWNER", "").strip())
        self.estimate_var = tk.StringVar(
            value=self._format_estimate_summary(note="Select a transcript file to view local estimates.")
        )

        self._event_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self._worker_thread: threading.Thread | None = None
        self._analyzed_result: AnalysisResult | None = None
        self._analyzed_signature: tuple[str, ...] | None = None

        self._build_layout()
        self._bind_input_watchers()
        self._apply_current_provider_model_buckets(
            preferred_model=self._preferred_model_for_provider(PROVIDER_OPENAI),
            preserve_current_model=False,
        )
        self._refresh_estimates()
        self._append_status("Choose a provider, choose a model, then click Analyze Transcript.")
        self._append_status("Loading visible OpenAI models...")
        self._start_model_catalog_load(PROVIDER_OPENAI)
        self.root.after(100, self._drain_event_queue)

    def _build_layout(self) -> None:
        container = ttk.Frame(self.root, padding=12)
        container.grid(sticky="nsew")

        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        container.columnconfigure(0, weight=1)
        container.rowconfigure(15, weight=3)
        container.rowconfigure(17, weight=1)

        ttk.Label(container, text="Provider").grid(row=0, column=0, sticky="w")

        self.provider_dropdown = ttk.Combobox(
            container,
            textvariable=self.provider_var,
            values=PROVIDER_OPTIONS,
            state="readonly",
        )
        self.provider_dropdown.grid(row=1, column=0, sticky="ew", pady=(4, 12))
        self.provider_dropdown.bind("<<ComboboxSelected>>", self._handle_model_control_selected)

        ttk.Label(container, text="Transcript File").grid(row=2, column=0, sticky="w")

        transcript_row = ttk.Frame(container)
        transcript_row.grid(row=3, column=0, sticky="ew", pady=(4, 12))
        transcript_row.columnconfigure(0, weight=1)

        self.transcript_entry = ttk.Entry(transcript_row, textvariable=self.transcript_path_var)
        self.transcript_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        self.browse_button = ttk.Button(transcript_row, text="Browse", command=self._browse_transcript)
        self.browse_button.grid(row=0, column=1, sticky="ew")

        ttk.Label(container, text="Model Filter").grid(row=4, column=0, sticky="w")

        self.model_filter_dropdown = ttk.Combobox(
            container,
            textvariable=self.model_filter_var,
            values=MODEL_FILTER_OPTIONS,
            state="readonly",
        )
        self.model_filter_dropdown.grid(row=5, column=0, sticky="ew", pady=(4, 12))
        self.model_filter_dropdown.bind("<<ComboboxSelected>>", self._handle_model_control_selected)

        ttk.Label(container, text="Model").grid(row=6, column=0, sticky="w")

        self.model_dropdown = ttk.Combobox(
            container,
            textvariable=self.model_var,
            state="readonly",
        )
        self.model_dropdown.grid(row=7, column=0, sticky="ew", pady=(4, 12))
        self.model_dropdown.bind("<<ComboboxSelected>>", self._handle_model_control_selected)

        ttk.Label(container, text="GitHub Owner").grid(row=8, column=0, sticky="w")

        self.github_owner_entry = ttk.Entry(container, textvariable=self.github_owner_var)
        self.github_owner_entry.grid(row=9, column=0, sticky="ew", pady=(4, 12))

        ttk.Label(container, text="Estimate").grid(row=10, column=0, sticky="w")

        self.estimate_label = ttk.Label(
            container,
            textvariable=self.estimate_var,
            justify="left",
            anchor="w",
            wraplength=720,
        )
        self.estimate_label.grid(row=11, column=0, sticky="ew", pady=(4, 12))

        ttk.Label(
            container,
            text="Review the raw model response below. Post-review structuring and publishing are deferred.",
        ).grid(row=12, column=0, sticky="w")

        button_row = ttk.Frame(container)
        button_row.grid(row=13, column=0, sticky="ew", pady=(8, 0))

        self.analyze_button = ttk.Button(
            button_row,
            text="Analyze Transcript",
            command=self._start_analysis,
        )
        self.analyze_button.grid(row=0, column=0, sticky="w", padx=(0, 8))

        self.batch_analyze_button = ttk.Button(
            button_row,
            text="Batch Analyze",
            command=self._start_batch_analysis,
        )
        self.batch_analyze_button.grid(row=0, column=1, sticky="w", padx=(0, 8))

        self.publish_button = ttk.Button(
            button_row,
            text="Create GitHub Project",
            command=self._start_publish,
            state="disabled",
        )
        self.publish_button.grid(row=0, column=2, sticky="w", padx=(0, 8))

        self.refresh_pricing_button = ttk.Button(
            button_row,
            text="Load Price Snapshot",
            command=self._refresh_pricing_registry,
        )
        self.refresh_pricing_button.grid(row=0, column=3, sticky="w", padx=(0, 8))

        self.clear_compatibility_button = ttk.Button(
            button_row,
            text="Clear Transcript Compatibility",
            command=self._clear_transcript_compatibility,
        )
        self.clear_compatibility_button.grid(row=0, column=4, sticky="w", padx=(0, 8))

        self.open_output_button = ttk.Button(
            button_row,
            text="Open Output Folder",
            command=self._open_output_folder,
        )
        self.open_output_button.grid(row=0, column=5, sticky="w")

        ttk.Label(container, text="Raw Model Response Review").grid(row=14, column=0, sticky="w", pady=(12, 0))

        self.preview_text = tk.Text(container, height=16, wrap="word", state="disabled")
        self.preview_text.grid(row=15, column=0, sticky="nsew", pady=(4, 0))

        ttk.Label(container, text="Status").grid(row=16, column=0, sticky="w", pady=(12, 0))

        self.status_text = tk.Text(container, height=9, wrap="word", state="disabled")
        self.status_text.grid(row=17, column=0, sticky="nsew", pady=(4, 0))

    def _bind_input_watchers(self) -> None:
        self.transcript_path_var.trace_add("write", self._handle_input_change)
        self.provider_var.trace_add("write", self._handle_input_change)
        self.provider_var.trace_add("write", self._handle_provider_change)
        self.model_filter_var.trace_add("write", self._handle_input_change)
        self.model_filter_var.trace_add("write", self._handle_model_filter_change)
        self.model_var.trace_add("write", self._handle_input_change)
        self.github_owner_var.trace_add("write", self._handle_input_change)

    def _start_model_catalog_load(self, provider: str) -> None:
        threading.Thread(target=self._load_model_catalog_worker, args=(provider,), daemon=True).start()

    def _load_model_catalog_worker(self, provider: str) -> None:
        try:
            config = load_config(
                require_openai_api_key=False,
                require_github_token=False,
                require_github_owner=False,
            )
            model_ids = load_visible_model_ids(provider, config)
            self._event_queue.put(
                ("model_catalog_success", (provider, build_model_buckets(provider, model_ids), len(model_ids)))
            )
        except Exception as exc:
            self._event_queue.put(("model_catalog_error", (provider, exc)))

    def _handle_model_control_selected(self, _event: object) -> None:
        self._user_changed_model_controls = True

    def _preferred_model_for_provider(self, provider: str) -> str | None:
        if provider == PROVIDER_OPENAI:
            return self._env_model_name
        return None

    def _handle_provider_change(self, *_args: object) -> None:
        active_provider = self.provider_var.get().strip() or PROVIDER_OPENAI
        self._model_buckets = self._model_buckets_by_provider.get(
            active_provider,
            build_fallback_model_buckets(active_provider),
        )
        self._apply_current_provider_model_buckets(
            preferred_model=self._preferred_model_for_provider(active_provider),
            preserve_current_model=True,
        )
        self._refresh_estimates()
        self._append_status(f"Loading visible {active_provider} models...")
        self._start_model_catalog_load(active_provider)

    def _handle_model_filter_change(self, *_args: object) -> None:
        self._refresh_model_dropdown(preserve_current_model=True)
        self._refresh_estimates()

    def _apply_current_provider_model_buckets(
        self,
        *,
        preferred_model: str | None,
        preserve_current_model: bool,
    ) -> None:
        self.provider_dropdown.config(values=PROVIDER_OPTIONS)
        self.model_filter_dropdown.config(values=MODEL_FILTER_OPTIONS)

        active_filter = self.model_filter_var.get().strip() or FILTER_RECOMMENDED
        if active_filter not in MODEL_FILTER_OPTIONS:
            self.model_filter_var.set(FILTER_RECOMMENDED)

        self._refresh_model_dropdown(
            preferred_model=preferred_model,
            preserve_current_model=preserve_current_model,
        )

    def _refresh_model_dropdown(
        self,
        *,
        preferred_model: str | None = None,
        preserve_current_model: bool = True,
    ) -> None:
        active_provider = self.provider_var.get().strip() or PROVIDER_OPENAI
        self._model_buckets = self._model_buckets_by_provider.get(
            active_provider,
            build_fallback_model_buckets(active_provider),
        )
        active_filter = self.model_filter_var.get().strip() or FILTER_RECOMMENDED
        available_models = list(self._model_buckets.get(active_filter, []))
        current_model = self.model_var.get().strip()

        selected_model = ""
        if preserve_current_model and current_model in available_models:
            selected_model = current_model
        elif preferred_model and preferred_model in available_models:
            selected_model = preferred_model
        elif available_models:
            selected_model = available_models[0]

        self.model_dropdown.config(values=available_models)

        if current_model != selected_model:
            self.model_var.set(selected_model)

    def _handle_input_change(self, *_args: object) -> None:
        self._refresh_estimates()
        current_signature = self._current_input_signature()
        if self._analyzed_result is None or self._analyzed_signature == current_signature:
            return

        self._analyzed_result = None
        self._analyzed_signature = None
        self._set_preview_text("")
        self._append_status("Inputs changed. Re-run analysis before making later review decisions.")
        self._update_button_states()

    def _current_input_signature(self) -> tuple[str, ...]:
        return (
            self.transcript_path_var.get().strip(),
            self.provider_var.get().strip(),
            self.model_filter_var.get().strip(),
            self.model_var.get().strip(),
            self.github_owner_var.get().strip(),
        )

    def _browse_transcript(self) -> None:
        selected_path = filedialog.askopenfilename(
            title="Select Transcript File",
            filetypes=[("Text Files", "*.txt")],
        )
        if selected_path:
            self.transcript_path_var.set(selected_path)

    def _start_analysis(self) -> None:
        transcript_text = self.transcript_path_var.get().strip()
        if not transcript_text:
            self._append_status("Error: Please select a transcript file.")
            return

        transcript_path = Path(transcript_text)
        if transcript_path.suffix.lower() != ".txt":
            self._append_status("Error: Please select a .txt transcript file.")
            return

        if not transcript_path.exists():
            self._append_status(f"Error: Transcript file not found: {transcript_path}")
            return

        selected_provider = self.provider_var.get().strip() or PROVIDER_OPENAI
        selected_model = self.model_var.get().strip()
        if not selected_model:
            self._append_status("Error: Please select a model.")
            return

        self._analyzed_result = None
        self._analyzed_signature = None
        self._set_preview_text("")
        self._set_busy(True)

        self._worker_thread = threading.Thread(
            target=self._run_analysis_worker,
            args=(transcript_path, selected_provider, selected_model),
            daemon=True,
        )
        self._worker_thread.start()

    def _start_publish(self) -> None:
        if self._analyzed_result is None:
            self._append_status("Error: Analyze the transcript and review the raw response first.")
            return

        self._append_status(
            "Post-review structuring, schema validation, and GitHub publishing are deferred beyond the current review boundary."
        )

    def _start_batch_analysis(self) -> None:
        transcript_text = self.transcript_path_var.get().strip()
        if not transcript_text:
            self._append_status("Error: Please select a transcript file.")
            return

        transcript_path = Path(transcript_text)
        if transcript_path.suffix.lower() != ".txt":
            self._append_status("Error: Please select a .txt transcript file.")
            return

        if not transcript_path.exists():
            self._append_status(f"Error: Transcript file not found: {transcript_path}")
            return

        selected_provider = self.provider_var.get().strip() or PROVIDER_OPENAI
        selected_filter = self.model_filter_var.get().strip() or FILTER_RECOMMENDED
        model_bucket = self._model_buckets_by_provider.get(
            selected_provider,
            build_fallback_model_buckets(selected_provider),
        )
        batch_models = list(model_bucket.get(selected_filter, []))
        if not batch_models:
            self._append_status(
                f"Error: No models are available in the {selected_filter} filter for {selected_provider}."
            )
            return

        self._set_busy(True)
        self._worker_thread = threading.Thread(
            target=self._run_batch_analysis_worker,
            args=(transcript_path, selected_provider, selected_filter, batch_models),
            daemon=True,
        )
        self._worker_thread.start()

    def _run_analysis_worker(
        self,
        transcript_path: Path,
        provider_name: str,
        model_override: str | None,
    ) -> None:
        try:
            result = analyze_transcript(
                transcript_path=transcript_path,
                provider_name=provider_name,
                model_override=model_override,
                status_callback=lambda message: self._event_queue.put(("status", message)),
            )
            self._event_queue.put(("analysis_success", result))
        except Exception as exc:
            self._event_queue.put(("analysis_error", exc))

    def _run_batch_analysis_worker(
        self,
        transcript_path: Path,
        provider_name: str,
        model_filter_name: str,
        model_ids: list[str],
    ) -> None:
        try:
            result = batch_analyze_transcript(
                transcript_path=transcript_path,
                provider_name=provider_name,
                model_filter_name=model_filter_name,
                model_ids=model_ids,
                status_callback=lambda message: self._event_queue.put(("status", message)),
            )
            self._event_queue.put(("batch_success", result))
        except Exception as exc:
            self._event_queue.put(("batch_error", exc))

    def _drain_event_queue(self) -> None:
        try:
            while True:
                event_type, payload = self._event_queue.get_nowait()

                if event_type == "status":
                    self._append_status(str(payload))
                    continue

                if event_type == "model_catalog_success":
                    self._handle_model_catalog_success(payload)
                    continue

                if event_type == "model_catalog_error":
                    self._handle_model_catalog_error(payload)
                    continue

                if event_type == "analysis_success":
                    self._handle_analysis_success(payload)
                    continue

                if event_type == "analysis_error":
                    self._handle_analysis_error(payload)
                    continue

                if event_type == "batch_success":
                    self._handle_batch_success(payload)
                    continue

                if event_type == "batch_error":
                    self._handle_batch_error(payload)
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self._drain_event_queue)

    def _handle_model_catalog_success(self, payload: object) -> None:
        if (
            not isinstance(payload, tuple)
            or len(payload) != 3
            or not isinstance(payload[0], str)
            or not isinstance(payload[1], dict)
            or not isinstance(payload[2], int)
        ):
            self._append_status("Could not apply the selected model catalog. Using the provider fallback list.")
            return

        provider, model_buckets, visible_model_count = payload
        normalized_buckets = {
            bucket_name: list(bucket_models)
            for bucket_name, bucket_models in model_buckets.items()
            if isinstance(bucket_name, str) and isinstance(bucket_models, list)
        }
        self._model_buckets_by_provider[provider] = normalized_buckets

        if provider == (self.provider_var.get().strip() or PROVIDER_OPENAI):
            self._model_buckets = normalized_buckets
            self._apply_current_provider_model_buckets(
                preferred_model=self._preferred_model_for_provider(provider),
                preserve_current_model=self._user_changed_model_controls,
            )
            self._refresh_estimates()

        self._append_status(f"Loaded {visible_model_count} visible {provider} models.")

    def _handle_model_catalog_error(self, payload: object) -> None:
        if (
            not isinstance(payload, tuple)
            or len(payload) != 2
            or not isinstance(payload[0], str)
        ):
            self._append_status("Could not load provider models. Using the provider fallback list.")
            return

        provider, error_payload = payload
        fallback_buckets = build_fallback_model_buckets(provider)
        self._model_buckets_by_provider[provider] = fallback_buckets

        if provider == (self.provider_var.get().strip() or PROVIDER_OPENAI):
            self._model_buckets = fallback_buckets
            self._apply_current_provider_model_buckets(
                preferred_model=self._preferred_model_for_provider(provider),
                preserve_current_model=True,
            )
            self._refresh_estimates()

        self._append_status(
            f"Could not load visible {provider} models. Using the provider fallback list."
        )
        self._append_status(f"Model loading error: {self._format_error_payload(error_payload)}")

    def _handle_analysis_success(self, payload: object) -> None:
        result = payload
        if not isinstance(result, AnalysisResult):
            self._append_status("Error: UI received an unexpected analysis payload.")
            self._set_busy(False)
            return

        self._analyzed_result = result
        self._analyzed_signature = self._current_input_signature()
        self._set_preview_text(result.raw_response_text)
        self._append_status(f"Saved raw response: {result.saved_response_path}")
        self._append_status(f"Response characters: {result.response_char_count}")
        self._append_status("Review the raw model response below.")
        self._set_busy(False)

    def _handle_analysis_error(self, payload: object) -> None:
        self._append_status(f"Error: {self._format_error_payload(payload)}")
        self._set_busy(False)

    def _handle_batch_success(self, payload: object) -> None:
        result = payload
        if not isinstance(result, BatchAnalysisResult):
            self._append_status("Error: UI received an unexpected batch analysis payload.")
            self._set_busy(False)
            return

        compatibility_counts = result.compatibility_counts
        self._append_status(f"Batch report: {result.report_path}")
        self._append_status(f"Batch output folder: {result.batch_output_dir}")
        self._append_status(f"Models attempted: {result.models_attempted}")
        self._append_status(f"Models succeeded: {result.models_succeeded}")
        self._append_status(f"Models failed: {result.models_failed}")
        self._append_status(
            (
                "Compatibility counts: "
                f"supported={compatibility_counts.get('supported', 0)}, "
                f"unsupported={compatibility_counts.get('unsupported', 0)}, "
                f"fixable={compatibility_counts.get('fixable', 0)}, "
                f"unknown={compatibility_counts.get('unknown', 0)}"
            )
        )
        self._set_busy(False)

    def _handle_batch_error(self, payload: object) -> None:
        self._append_status(f"Error: {self._format_error_payload(payload)}")
        self._set_busy(False)

    def _format_error_payload(self, payload: object) -> str:
        if isinstance(payload, Exception):
            return f"{type(payload).__name__}: {payload}"
        return str(payload)

    def _format_estimate_summary(
        self,
        *,
        prompt_tokens: int | None = None,
        output_tokens: int | None = None,
        total_tokens: int | None = None,
        input_cost: float | None = None,
        output_cost: float | None = None,
        total_cost: float | None = None,
        note: str | None = None,
    ) -> str:
        lines = [
            f"Estimated Prompt Tokens: {self._format_count(prompt_tokens)}",
            f"Estimated Output Tokens: {self._format_count(output_tokens)}",
            f"Estimated Total Tokens: {self._format_count(total_tokens)}",
            f"Estimated Input Cost: {self._format_cost(input_cost)}",
            f"Estimated Output Cost: {self._format_cost(output_cost)}",
            f"Estimated Total Cost: {self._format_cost(total_cost)}",
        ]
        if note:
            lines.extend(["", note])
        return "\n".join(lines)

    def _format_count(self, value: int | None) -> str:
        if value is None:
            return "Unavailable"
        return f"{value:,}"

    def _format_cost(self, value: float | None) -> str:
        if value is None:
            return "Unavailable"
        return f"${value:.6f}"

    def _refresh_pricing_registry(self) -> None:
        try:
            refreshed_path = refresh_pricing_registry()
        except Exception as exc:
            self._append_status(f"Price snapshot load failed: {type(exc).__name__}: {exc}")
            return

        self._append_status(f"Dated price snapshot loaded: {refreshed_path}")
        self._refresh_estimates()

    def _clear_transcript_compatibility(self) -> None:
        try:
            removed_count, store_path = clear_task_compatibility_records(TASK_TRANSCRIPT_ANALYSIS)
        except Exception as exc:
            self._append_status(
                f"Compatibility reset failed: {type(exc).__name__}: {exc}"
            )
            return

        self._append_status(
            (
                f"Cleared {removed_count} transcript_analysis compatibility record(s): "
                f"{store_path}"
            )
        )
        self._append_status(
            "Recommended and Fixable now need fresh live attempts. Re-run Batch Analyze on All to repopulate them."
        )
        self._rebuild_model_buckets_after_compatibility_reset()
        self._refresh_estimates()

    def _rebuild_model_buckets_after_compatibility_reset(self) -> None:
        for provider_name in PROVIDER_OPTIONS:
            existing_buckets = self._model_buckets_by_provider.get(provider_name, {})
            all_models = existing_buckets.get("All") if isinstance(existing_buckets, dict) else None
            if not isinstance(all_models, list) or not all_models:
                all_models = list(build_fallback_model_buckets(provider_name).get("All", []))

            self._model_buckets_by_provider[provider_name] = build_model_buckets(
                provider_name,
                list(all_models),
            )

        active_provider = self.provider_var.get().strip() or PROVIDER_OPENAI
        self._model_buckets = self._model_buckets_by_provider.get(
            active_provider,
            build_fallback_model_buckets(active_provider),
        )
        self._apply_current_provider_model_buckets(
            preferred_model=self._preferred_model_for_provider(active_provider),
            preserve_current_model=True,
        )

    def _refresh_estimates(self) -> None:
        selected_provider = self.provider_var.get().strip() or PROVIDER_OPENAI
        selected_model = self.model_var.get().strip()
        transcript_path_text = self.transcript_path_var.get().strip()

        if not selected_model:
            self.estimate_var.set(
                self._format_estimate_summary(note="Select a model to view local token and cost estimates.")
            )
            return

        if not transcript_path_text:
            self.estimate_var.set(
                self._format_estimate_summary(note="Select a transcript file to view local token and cost estimates.")
            )
            return

        transcript_path = Path(transcript_path_text)
        if not transcript_path.exists():
            self.estimate_var.set(
                self._format_estimate_summary(note="Transcript file not found. Select a valid .txt file.")
            )
            return

        try:
            transcript_text = transcript_path.read_text(encoding="utf-8").strip()
        except OSError:
            self.estimate_var.set(
                self._format_estimate_summary(note="Could not read the transcript file for local estimation.")
            )
            return

        if not transcript_text:
            self.estimate_var.set(
                self._format_estimate_summary(note="Transcript file is empty, so estimates are unavailable.")
            )
            return

        try:
            token_estimate = estimate_transcript_analysis_tokens(
                transcript_text,
                selected_provider,
                selected_model,
            )
        except ValueError as exc:
            self.estimate_var.set(self._format_estimate_summary(note=str(exc)))
            return

        pricing_registry = load_pricing_registry()
        pricing_record = read_pricing_record(
            pricing_registry,
            provider=selected_provider,
            model_id=selected_model,
        )

        if pricing_record is None:
            self.estimate_var.set(
                self._format_estimate_summary(
                    prompt_tokens=token_estimate.prompt_tokens,
                    output_tokens=token_estimate.output_tokens,
                    total_tokens=token_estimate.total_tokens,
                    note="Pricing unavailable for the selected provider/model in the local pricing registry.",
                )
            )
            return

        cost_estimate = estimate_token_costs(
            pricing_record,
            prompt_tokens=token_estimate.prompt_tokens,
            output_tokens=token_estimate.output_tokens,
        )
        stale_note = (
            f"Pricing data is older than {PRICING_STALE_AFTER_DAYS} days."
            if is_pricing_record_stale(pricing_record)
            else None
        )
        self.estimate_var.set(
            self._format_estimate_summary(
                prompt_tokens=token_estimate.prompt_tokens,
                output_tokens=token_estimate.output_tokens,
                total_tokens=token_estimate.total_tokens,
                input_cost=cost_estimate.input_cost,
                output_cost=cost_estimate.output_cost,
                total_cost=cost_estimate.total_cost,
                note=stale_note,
            )
        )

    def _update_button_states(self) -> None:
        self.analyze_button.config(state="normal")
        self.batch_analyze_button.config(state="normal")
        self.publish_button.config(state="normal" if self._analyzed_result is not None else "disabled")
        self.browse_button.config(state="normal")
        self.transcript_entry.config(state="normal")
        self.github_owner_entry.config(state="normal")
        self.provider_dropdown.config(state="readonly")
        self.model_filter_dropdown.config(state="readonly")
        self.model_dropdown.config(state="readonly")
        self.refresh_pricing_button.config(state="normal")
        self.clear_compatibility_button.config(state="normal")
        self.open_output_button.config(state="normal")

    def _set_busy(self, is_busy: bool) -> None:
        if is_busy:
            self.analyze_button.config(state="disabled")
            self.batch_analyze_button.config(state="disabled")
            self.publish_button.config(state="disabled")
            self.browse_button.config(state="disabled")
            self.transcript_entry.config(state="disabled")
            self.github_owner_entry.config(state="disabled")
            self.provider_dropdown.config(state="disabled")
            self.model_filter_dropdown.config(state="disabled")
            self.model_dropdown.config(state="disabled")
            self.refresh_pricing_button.config(state="disabled")
            self.clear_compatibility_button.config(state="disabled")
            self.open_output_button.config(state="disabled")
            return

        self._update_button_states()

    def _set_preview_text(self, content: str) -> None:
        self.preview_text.config(state="normal")
        self.preview_text.delete("1.0", "end")
        if content:
            self.preview_text.insert("1.0", content)
        self.preview_text.config(state="disabled")

    def _append_status(self, message: str) -> None:
        self.status_text.config(state="normal")
        self.status_text.insert("end", f"{message}\n")
        self.status_text.see("end")
        self.status_text.config(state="disabled")

    def _open_output_folder(self) -> None:
        output_dir = OUTPUT_PATH.parent
        output_dir.mkdir(parents=True, exist_ok=True)

        if not hasattr(os, "startfile"):
            self._append_status(f"Output folder: {output_dir}")
            return

        try:
            os.startfile(str(output_dir))  # type: ignore[attr-defined]
            self._append_status(f"Opened output folder: {output_dir}")
        except OSError as exc:
            self._append_status(f"Error opening output folder: {exc}")


def main() -> None:
    root = tk.Tk()
    TranslatorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
