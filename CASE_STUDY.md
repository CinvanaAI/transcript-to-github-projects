# From conversation to a reviewed plan

A transcript can contain ideas, rejected suggestions and constraints alongside real intended work. Turning every sentence into a public task would lose that distinction.

[The translator](app/translator.py) constructs an extraction request while preserving the supplied source. [The analysis coordinator](app/pipeline.py) selects a provider, captures its raw response and records observed success or failure. [The schema](app/schema.py) then checks the structure of a proposed project. These are separate checks: valid JSON can still describe the wrong work.

Run `python -m examples.offline_case` to exercise the real coordinator and schema with an explicitly synthetic provider. The fixture records the original response before validating the plan. Change the response in the example to explore schema rejection; no model or GitHub account is involved.

[The desktop surface](app/ui.py) retains a human review step; its publishing handoff is deferred in this snapshot. [The original publishing helper](app/github_projects.py) and the independent GitHub Project Draft Publisher show the later mutation boundary. Automatic publication is not an implied consequence of successful analysis.
