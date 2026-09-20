# From conversation to a reviewed plan

A transcript can contain ideas, rejected suggestions and constraints alongside real intended work. Turning every sentence into a public task would lose that distinction.

[The translator](app/translator.py) constructs an extraction request while preserving the supplied source. [The analysis coordinator](app/pipeline.py) selects a provider, captures its raw response and records observed success or failure. [The schema](app/schema.py) then checks the structure of a proposed project. These are separate checks: valid JSON can still describe the wrong work.

Run `python -m examples.offline_case` to exercise the real coordinator and schema with an explicitly synthetic provider. It records two authored responses before validation: a complete JSON plan and ordinary prose. The first passes the project schema; the second stays preserved as raw analysis. Both returned text, so both receive the coordinator's supported classification. That classification is not a schema verdict or a quality judgment. No model or GitHub account is involved.

The translator currently asks for raw analysis without a fixed schema. Converting that analysis into an approved structured project remains a separate operator/application responsibility. The JSON fixture demonstrates that later boundary; it does not pretend the current prompt guarantees that shape.

[The desktop surface](app/ui.py) retains a human review step; its publishing handoff is deferred in this snapshot. [The original publishing helper](app/github_projects.py) and the independent GitHub Project Draft Publisher show the later mutation boundary. Automatic publication is not an implied consequence of successful analysis.
