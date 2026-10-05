---
name: kpi-report
description: Weekly KPI report with week-over-week deltas across traffic, signups, revenue and pipeline, every number sourced. Use for "KPI report", "weekly numbers", "how are signups trending".
---
# KPI report

## Inputs

`metrics_sources`, `metrics_query`, `crm_pipeline`, `company/goals.md` (targets), `company/company.yaml` (metric definitions), previous report in `workspace/reports/kpi/`.

## Procedure

Keep the length budget (below) in mind from the start: collect broadly, write narrowly.

1. `metrics_sources` to list sources and columns. Compare with the sources the previous report used; note additions or disappearances.
2. For each source relevant to goals (typically web, signups, revenue, search), `metrics_query days=14` (current vs. previous week). Use `days=28` where seasonality matters. Write down the values returned, not rounded estimates.
3. `crm_pipeline` for pipeline value and counts per stage.
4. Build one table per area: metric, current, previous, delta (absolute and %), target, source. Compute deltas from the returned totals and show operands. Mark small bases.
5. Anomalies: flag changes large relative to the series' recent daily variation (the tool returns the latest 14 daily rows). For each, give evidence, then "Hypothesis: ..." and what would confirm it.
6. Compare with targets in `company/goals.md`; state on-track, behind or no target.
7. Write the report with `report-format`, within the length budget below. Recommendations at most three, each concrete. Propose `task.create` for investigations that merit it (for example a funnel drop), with numbers in the justification.

## Output

`workspace/reports/kpi/{date}-kpi-weekly.md`. Run report: status, summary (headline numbers), `artifacts`, `proposed_actions`, `data_gaps`, `needs_human`.

## Length budget

A founder reads this in one minute. The budget is structural, so you can keep it while writing:
- TL;DR of at most 5 one-line bullets, the most important finding first.
- At most 3 tables (traffic and signups, revenue and accounts, pipeline), only rows that matter for goals.
- One short section per real anomaly, with at most 7 daily rows of evidence.
- No section longer than a short paragraph plus its table. Detail that does not change a decision is left out.

## Quality checks

- Each number traces to a `metrics_query` or `crm_pipeline` call in this run.
- Period boundaries are dates, not "last week".
- Percent changes next to absolute values; no percent on tiny bases without a note.
- Hypotheses labelled; no causal claim stated as fact.
- Within the structural length budget. Cut whole rows and paragraphs, not words.

## Failure handling

If a source errors or is empty, leave its table out, list it in `data_gaps`, set status `partial`. If a source's columns changed from the previous report, say so and do not compare across the change. Never carry numbers over from a previous report.
