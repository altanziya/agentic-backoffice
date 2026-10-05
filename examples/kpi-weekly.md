# KPI weekly - week 2026-09-28 to 2026-10-04

As of: 2026-10-05 Europe/Berlin (latest data row: 2026-10-04) | Period: 2026-09-28 to 2026-10-04 (7 days, Mon-Sun) vs 2026-09-21 to 2026-09-27 | Author: kpi-analyst

## TL;DR
- Trial conversion broke on 2026-10-02: visit-to-trial rate went from 2.10-2.34% per day to 1.22%, 1.25%, 1.22% on 10-02, 10-03, 10-04, while sessions stayed normal. Weekly rate is 1.92% (167 / 8,679), below the 2.0% floor in KR2.2.
- Trial signups: 167 vs 196 (-29, -14.8%). Sessions: 8,679 vs 8,945 (-266, -3.0%).
- MRR EUR 38,400 on 2026-10-04 vs EUR 37,505 on 2026-09-27 (+EUR 895, +2.4%). New MRR fell to EUR 1,194 from EUR 1,944 with the same 6 new paid accounts (n=6 each week).
- Pipeline in demo/proposal/negotiation is EUR 32,328 (6 deals) against the EUR 60,000 target. Four open deals have overdue next steps; one is 9 days past due.
- Search is flat: 2,165 clicks vs 2,198 (-33, -1.5%).

## Traffic and search

Weekly window 2026-09-28 to 2026-10-04 vs 2026-09-21 to 2026-09-27.

| Metric | Current | Previous | Delta | Target | Source |
|---|---|---|---|---|---|
| Sessions | 8,679 | 8,945 | -266 (-3.0%) | none | web, days=7 |
| Users | 6,837 | 6,936 | -99 (-1.4%) | none | web, days=7 |
| Bounce rate (mean, share) | 0.479 | 0.480 | -0.001 (-0.1%) | none | web, days=7 |
| Search clicks | 2,165 | 2,198 | -33 (-1.5%) | see below | search, days=7 |
| Search impressions | 74,079 | 75,029 | -950 (-1.3%) | none | search, days=7 |
| Avg position (mean; lower is better) | 11.329 | 11.429 | -0.100 (-0.9%) | none | search, days=7 |

Organic clicks, 28-day window 2026-09-07 to 2026-10-04: 8,617 vs 7,980 (+637, +8.0%) (search, days=28). KR2.3 asks for +25% over the quarter. The tool gives no quarter-start baseline. If this window is taken as the baseline, the goal is 8,617 x 1.25 = 10,771 clicks per 28 days. Status: too early to judge.

KR2.4 (5 quick-win queries into the top 3): `company/data/search/queries.csv` holds `position` and `position_prev` only, not a quarter baseline. No query moved from above 3.0 to 3.0 or better between those two columns. Status: 0 of 5 visible, not measurable properly.

## Signups and conversion

| Metric | Current | Previous | Delta | Target | Source |
|---|---|---|---|---|---|
| Trial signups (7 days) | 167 | 196 | -29 (-14.8%) | none weekly | web, days=7 |
| Visit-to-trial rate (signups / sessions) | 1.92% (167 / 8,679) | 2.19% (196 / 8,945) | -0.27 pp | at or above 2.0% every week (KR2.2) | web, days=7 |
| Trial signups (28 days, 2026-09-07 to 10-04) | 747 | 735 | +12 (+1.6%) | at least 330 per month (KR2.1) | web, days=28 |

KR2.1: on track. 747 in 28 days is well above 330 per month. The target looks low against the run-rate; see `needs_human`.
KR2.2: behind this week (1.92% < 2.0%).

### Anomaly: conversion halved from 2026-10-02

Daily visit-to-trial rate, computed from web daily rows:

| Date | Sessions | Trial signups | Rate |
|---|---|---|---|
| 2026-09-26 (Sat) | 668 | 14 | 2.10% |
| 2026-09-27 (Sun) | 563 | 12 | 2.13% |
| 2026-09-28 to 10-01 (Mon-Thu) | 1,504 / 1,506 / 1,577 / 1,488 | 35 / 31 / 36 / 33 | 2.06% to 2.33% |
| 2026-10-02 (Fri) | 1,312 | 16 | 1.22% |
| 2026-10-03 (Sat) | 719 | 9 | 1.25% |
| 2026-10-04 (Sun) | 573 | 7 | 1.22% |

Evidence:
- Over 2026-09-21 to 10-01, weekday signups stayed between 31 and 36 per day. On 10-02 they were 16.
- Weekend sessions on 10-03 and 10-04 (719, 573) match the previous weekend (668, 563). Traffic did not fall; the share starting a trial did.
- At a 2.2% rate, 10-02 to 10-04 would have produced about 57 trials (1,312 + 719 + 573 sessions x 2.2%); the actual count was 32. About 25 are missing (estimate from the 2.2% assumption).
- Sessions on 10-02 (1,312) were below the 1,443-1,651 range of the previous nine weekdays, so part of that day's drop is traffic.

Hypothesis: a fault in the trial signup flow or in trial-start tracking began on 2026-10-02. Confirm by: deploys on 10-01 to 10-02, form errors and script failures, and a comparison of trial starts in the app database with web analytics for 10-02 to 10-04. If the app database shows normal trial counts, the fault is in tracking only and the real funnel is intact.

Why it matters: trials lead new paid accounts by about 3 weeks (company.yaml), so a real drop would show in `new_paid` around 2026-10-23.

Follow-up proposed: task.create A-31ed7451 (queued, T1; not yet executed).

## Revenue and accounts

Weekly window 2026-09-28 to 2026-10-04 vs 2026-09-21 to 2026-09-27. MRR is a snapshot at the last day of each window.

| Metric | Current | Previous | Delta | Target | Source |
|---|---|---|---|---|---|
| MRR (EUR) | 38,400 | 37,505 | +895 (+2.4%) | EUR 46,000 by 2026-12-31 (KR1.1) | revenue, days=7 |
| New MRR (EUR) | 1,194 | 1,944 | -750 (-38.6%) | none | revenue, days=7 |
| Churned MRR (EUR) | 299 | 149 | +150 (+100.7%) | none | revenue, days=7 |
| Active accounts (end of window) | 141 | 136 | +5 (+3.7%) | none | product, days=7 |
| New paid accounts | 6 | 6 | 0 (0%) | at least 14 per month (KR1.2) | product, days=7 |
| Churned accounts | 1 | 1 | 0 (0%) | see below | product, days=7 |
| Jobs scheduled | 11,002 | 11,175 | -173 (-1.5%) | none | product, days=7 |

Checks: net new MRR 1,194 - 299 = 895, which equals 38,400 - 37,505. Active accounts 136 + 6 - 1 = 141.

- KR1.1: MRR is EUR 38,400. Reaching EUR 46,000 by 12-31 needs +EUR 7,600 in 88 days, about EUR 605 per week. This week added EUR 895 net. Status: on pace this week; one week is a short base.
- KR1.2: 19 new paid accounts in the 28 days 2026-09-07 to 10-04 (product, days=28; previous 17), against 14 per month. Status: ahead. The window is 28 days, not a calendar month.
- KR1.3: 3 churned accounts in the same 28 days (previous 1) over 141 active accounts = 2.13%, against a ceiling of 2.0%. n=3: one account moves the rate by 0.7 pp. Status: at the limit, small base. The denominator is the end-of-window account count, not a start-of-month count.

### Watch item: lower revenue per new account
New MRR per new paid account was EUR 199 (1,194 / 6) vs EUR 324 (1,944 / 6) the week before. Base is 6 accounts each week, so treat it with care.
Hypothesis: the mix shifted toward lower-priced plans. Confirm with plan-level data for the 12 accounts won since 2026-09-21; the metrics sources have no plan column.

## Pipeline

Source: `crm_pipeline` (run 2026-10-05). The tool returns a snapshot only, so there is no previous-period value and no delta.

| Stage | Deals | Value (EUR) |
|---|---|---|
| Proposal | 2 | 14,376 |
| Demo | 3 | 10,764 |
| Negotiation | 1 | 7,188 |
| **Demo + proposal + negotiation (KR3.1)** | **6** | **32,328** |
| Qualified | 4 | 10,752 |
| Lead | 1 | 1,788 |
| Won | 1 | 3,588 |
| Lost | 2 | 3,576 |

- KR3.1: EUR 32,328 vs EUR 60,000 target = 54% (32,328 / 60,000). Gap EUR 27,672. Status: behind.
- Open pipeline including qualified and lead: EUR 44,868 across 11 deals (32,328 + 10,752 + 1,788).
- KR3.3 (5 new Business-plan accounts): not measurable; no tool returns plan per account.

Overdue next steps, days counted to 2026-10-05:

| Deal | Stage | Next step | Due | Days overdue |
|---|---|---|---|---|
| d004 Reuter Sanitär - Starter plan | qualified | Book demo | 2026-09-26 | 9 |
| d001 Vogel Haustechnik - Team plan | demo | Send maintenance-contract demo recording | 2026-09-30 | 5 |
| d006 Lutz Heizung - Team plan | demo | Follow up on DATEV export question | 2026-10-01 | 4 |
| d002 Kraft Installation - Business plan | proposal | Answer SSO question, resend proposal | 2026-10-03 | 2 |

KR3.2 asks for no deal more than 7 days overdue. d004 is at 9 days. Status: behind. Three of the four overdue deals sit in stages that count toward KR3.1.

## Recommendations
1. Check the trial signup flow and tracking for 2026-10-02 onward today (task A-31ed7451). Reason: three days at 1.22-1.25% against a normal 2.1-2.3%.
2. Jonas: clear the four overdue next steps, starting with d004 (9 days). Reason: KR3.2 is breached and three of the four deals are in the KR3.1 stages.
3. Pull plan-level data for the 12 accounts won in the last two weeks to test the plan-mix hypothesis behind lower new MRR per account.

## Sources
- `metrics_sources` (run 2026-10-05)
- `metrics_query source=web days=7`, `days=14`, `days=28` (run 2026-10-05)
- `metrics_query source=product days=7`, `days=14`, `days=28` (run 2026-10-05)
- `metrics_query source=revenue days=7`, `days=14` (run 2026-10-05)
- `metrics_query source=search days=7`, `days=14`, `days=28` (run 2026-10-05)
- `crm_pipeline` (run 2026-10-05)
- `company/goals.md`, `company/company.yaml`, `company/data/search/queries.csv`

## Data gaps
- No previous KPI report exists in `workspace/reports/kpi/`, and `workspace/state/kpi-analyst.md` did not exist. All deltas come from the tool's own previous-period values.
- Latest data row is 2026-10-04; 2026-10-05 is not yet in the sources, so the week ends 10-04.
- `metrics_query` returns the previous period as the window of equal length before the current one; no quarter-start baseline for KR2.3 and KR2.4.
- No plan-level data: KR3.3 and the plan-mix hypothesis cannot be checked.
- `crm_pipeline` has no history, so pipeline deltas are not available.
