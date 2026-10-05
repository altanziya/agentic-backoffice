---
name: seo-weekly
description: Weekly SEO analysis - search performance, quick wins at positions 4-15, content gaps, concrete fix tasks. Use for "SEO report", "which queries should we improve", "ranking changes".
---
# SEO weekly

## Inputs

`metrics_sources`, `metrics_query` (sources `search` and `web`), `company/products.md`, `company/content-plan.md`, previous report in `workspace/reports/seo/`.

## Procedure

1. `metrics_sources` and confirm `search` columns (query, page, clicks, impressions, position or as listed). Adapt to the actual column names.
2. `metrics_query source=search days=28` and `source=web days=28`. Record totals and deltas vs. the previous period.
3. Quick wins: rows with position between 4 and 15 and meaningful impressions (state the threshold you used, for example top quartile by impressions). Rank by impressions. For the top five to eight, name the page, query, position, impressions, and one specific fix: title wording, heading, missing section, internal link, schema.
4. Winners and losers: queries or pages with the largest position or click change. State period and size; label causes as hypotheses.
5. Content gaps: queries with impressions where no page targets the intent. Cross-check `company/content-plan.md`; mark which are planned, which are not.
6. Check claims against `company/products.md`: do not recommend targeting capabilities the product lacks.
7. Write the report (`report-format`): TL;DR, totals table, quick wins table, movers, gaps, recommendations.
8. Propose `task.create` for each concrete fix, at most five per run, path `{date}-seo-<slug>.md`, content with query, page, current numbers, the fix and the expected gain stated as an expectation, not a promise.

## Output

`workspace/reports/seo/{date}-seo-weekly.md`. Run report with `proposed_actions` listing task ids.

## Quality checks

- Every number comes from a `metrics_query` call in this run.
- Each quick win has page, query, fix; none are generic advice.
- Small samples (few impressions) flagged.
- No ranking cause stated as fact.

## Failure handling

If `search` is unavailable, report on `web` only and record the gap; status `partial`. If rows lack a page column, say that page-level fixes cannot be assigned and give query-level advice only.
