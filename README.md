# Transcript to GitHub Projects

An early workbench for reading a planning conversation, keeping the model's raw response, and reviewing proposed work before publication. The useful idea is the review boundary: **a returned analysis, a structurally valid plan, and a plan someone approves are different things**.

This is an inspectable source snapshot, including the desktop and provider code. Its current completed visitor path is the offline case below; the desktop publishing handoff remains deferred. [Origin](ORIGIN.md)

## Follow both outcomes

Python 3.11+, from this checkout:

```sh
python -m pip install -e .
python -m examples.offline_case
python -m pip install pytest
python -m pytest -q
```

[The source walkthrough](examples/offline_case.py) runs the real coordinator with a synthetic provider and temporary output files. [The captured cases](examples/result.json) show the full request messages, exact saved responses and schema results:

| Authored fixture response | Raw analysis | Project schema |
| --- | --- | --- |
| JSON describing a review gate | Saved exactly | Passes |
| Ordinary prose about the same request | Saved exactly | Does not parse as a project |

Both return nonempty text, so the coordinator records compatibility as “supported.” That label means this request returned usable text; it does not establish plan validity, model quality or general capabilities. Neither case performs human approval or publishes anything.

## Why the second case matters

[translator.py](app/translator.py) asks for raw analysis and explicitly allows prose, Markdown or JSON. It does not request a fixed project schema. [pipeline.py](app/pipeline.py) captures the response; [schema.py](app/schema.py) is a later structural check that callers can use for a proposed plan.

The valid JSON in the first example was deliberately authored as a fixture. It is not evidence that a model reliably converts conversations into that schema. A structurally valid plan can still omit a constraint or promote a rejected suggestion into work.

## Inspect or extend the snapshot

Follow [CASE_STUDY.md](CASE_STUDY.md) for the call path. Change the fixture response in the example to test another review/schema outcome without credentials or external requests. Preserve the raw response even when the later schema step rejects it.

The historical CLI and desktop adapters remain in source. Live analysis sends your transcript to the selected provider and requires configuration; historical model defaults/pricing need revalidation. The default private input file is deliberately absent. The included [synthetic conversation](input/conversation.example.txt) is an example, not recovered personal data. No live provider/account behavior is newly certified by the offline case.

For an already reviewed JSON plan, the separate [GitHub Projects V2 Draft Publisher](https://github.com/CinvanaAI/github-projects-v2-draft-publisher) provides a preview and explicit publication boundary.

A useful continuation would make raw analysis → edited plan → explicit approval a fully recorded desktop handoff. Completing that flow is different from adding another model to a dropdown.

[Tests](tests/test_core.py) · [Security](SECURITY.md) · [License](LICENSE.md)
