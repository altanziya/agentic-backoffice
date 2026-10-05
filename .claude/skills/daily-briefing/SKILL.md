---
name: daily-briefing
description: Produce the one-page morning briefing from live metrics, pipeline, pending approvals, ops status and the latest reports of other jobs. Use for "daily briefing", "morning briefing", "what do I need to know today".
---
# Daily briefing

Purpose: one page a founder reads in two minutes. Coordination is file-based: other jobs (news digest, ops check, CRM hygiene) already wrote reports; you read them and add live numbers. No delegation needed.

## Inputs

- Latest file in each of `workspace/reports/intel/`, `workspace/reports/ops/`, `workspace/reports/crm/` and, on Mondays, `workspace/reports/kpi/` and `seo/` (Glob, sort by file name date).
- Live: `metrics_sources`, `metrics_query` (web, signups, revenue: 7 days), `crm_pipeline`, `list_actions status=pending`, `ops_status`.
- `company/goals.md` for what counts as important.

## Procedure

1. Glob the report directories. Note each file's date. A report older than 2 days (older than 4 on Mondays) is stale: use it only with its date shown, and list the gap.
2. Query live metrics for the last 7 days and compare with the previous 7 (the tool returns deltas). Pick at most three numbers that moved or sit off target.
3. Call `crm_pipeline`: stage totals and overdue next steps.
4. Call `list_actions status=pending`; list each with kind, title, age and `expires_at`. Flag any expiring within 24 hours.
5. Call `ops_status`; note failed runs and spend vs. budget. Take detail from the latest ops report; do not duplicate it.
6. Read the latest intel digest; take its top two items.
7. Write the briefing. Order: needs a decision today (approvals, overdue deals, suspicious inbound), numbers, news, ops. Apply `report-format` and keep it to one screen (about 350 words).
8. Do not propose actions unless something is clearly time-critical and small (for example a `team.message` is not needed; the notification already goes out).

## Output

`workspace/reports/briefings/{date}-daily-briefing.md`

Run report: status `ok` (or `partial` with stale or missing inputs in `data_gaps`), summary of 3-6 sentences, `artifacts` with the path, `proposed_actions` (normally empty), `needs_human` listing pending approvals older than 24 h and anything else only a human can decide.

## Quality checks

- Every number was returned by a tool in this session or appears in a cited report with its date.
- Pending approvals in the text equal the `list_actions` result.
- Stale or missing inputs are named, not smoothed over.
- No section is filler: drop empty sections.

## Failure handling

If a live source fails, write the briefing without it and add a data gap. If `workspace/reports/` has no inputs at all, produce a metrics-and-approvals-only briefing and status `partial`. Never invent a number or reuse one from an older briefing.
