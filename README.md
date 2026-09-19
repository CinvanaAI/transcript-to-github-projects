# Transcript to GitHub Projects

An early workbench for extracting proposed work from a transcript, preserving model responses and reviewing the plan before publication.

## Try the case

Python 3.11+. From this checkout:

```sh
python -m pip install -r requirements.txt
python -m examples.offline_case
```

**Input:** A synthetic conversation requesting a review queue and an explicitly authored provider response.

**Result:** The actual analysis coordinator reads the input, saves the raw response and validates its project schema. The example uses injected provider/configuration boundaries and makes no network calls.

See [the captured case](examples/RESULT.md) and [the source walkthrough](CASE_STUDY.md).

## What this project contributes

Raw model output remains available before it becomes structured planning data. Analysis success, plan correctness, human review and publication are distinct steps.

## Scope

The desktop publishing handoff is deferred. This package preserves the workbench as an inspectable case rather than claiming complete transcript-to-published-project automation. Historical model defaults and pricing snapshots need revalidation for a live account.

For an already reviewed JSON plan, [GitHub Project Draft Publisher](https://github.com/CinvanaAI/github-projects-v2-draft-publisher) provides the separate preview and explicit publication path.

Owned code is available under the [MIT license](LICENSE.md).
