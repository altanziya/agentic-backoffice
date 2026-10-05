# 0007 - Every headless run ends in a structured report

**Status:** accepted

**Context.** Free-text final answers are hard to notify on, compare across runs, or assert on in
evals.

**Decision.** Headless sessions use the SDK's `output_format` with a JSON schema: `status`
(ok / partial / blocked), `summary`, `artifacts`, `proposed_actions`, `data_gaps`,
`needs_human`. Human-facing detail goes into Markdown reports under `workspace/reports/`.

**Consequences.** The notifier sends `summary` and `needs_human`; evals assert on fields;
`data_gaps` makes "a source was down" a first-class outcome instead of a silent zero.
