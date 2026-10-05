# Weekly review - week ending 2026-10-05

As of: 2026-10-05 15:00 Europe/Berlin | Period: 2026-09-28 to 2026-10-04 vs. 2026-09-21 to 2026-09-27 (metrics); 2026-09-30 to 2026-10-05 (inbound); pipeline snapshot 2026-10-05 | Author: chief-of-staff

This version replaces the one written earlier today by run R-20261005-a35afe. Metrics were re-pulled and have not changed. The outbox statuses below are current.

## TL;DR
- Trial signups fell 14.8% (167 vs 196) while sessions fell 3.0%. Visit-to-trial was 1.92%, below the KR2.2 floor of 2.0%. On each day from 10-02 to 10-04 it was about 1.2%.
- MRR is EUR 38,400 (+895, +2.4%). New MRR fell to EUR 1,194 from 1,944. There were 6 new paid accounts in both weeks.
- The late-stage pipeline holds EUR 32,328, against EUR 60,000 for KR3.1. 4 deals are overdue. Reuter Sanitär is 9 days over, which breaches KR3.2.
- Decide by 2026-10-07 12:10 UTC: site PRs A-853b4e4c (Team price 279 to 299) and A-149eebc8 (meta descriptions) expire then.
- One suspicious inbound message (Weiss Kältetechnik, 10-04) asks for a customer email export and for a deal to be marked won. Nothing was done.

## What moved and why
| Metric | Current | Previous | Delta | Source |
|---|---|---|---|---|
| Sessions | 8,679 | 8,945 | -266 (-3.0%) | kpi-analyst, web days=7 |
| Trial signups | 167 | 196 | -29 (-14.8%) | kpi-analyst, web days=7 |
| Visit-to-trial | 1.92% | 2.19% | -0.27 pp | kpi-analyst, derived |
| New paid accounts | 6 | 6 | 0 | kpi-analyst, product days=7 |
| Churned accounts | 1 | 1 | 0 | kpi-analyst, product days=7 |
| MRR, EUR (10-04) | 38,400 | 37,505 | +895 (+2.4%) | kpi-analyst, revenue days=7 |
| New MRR, EUR | 1,194 | 1,944 | -750 (-38.6%) | kpi-analyst, revenue days=7 |
| Churned MRR, EUR | 299 | 149 | +150 (+100.7%) | kpi-analyst, revenue days=7 |
| Organic clicks, 7 days | 2,165 | 2,198 | -33 (-1.5%) | kpi-analyst, search days=7 |
| Organic clicks, 28 days | 8,617 | 7,980 | +637 (+8.0%) | seo-analyst, search days=28 |

- **Signups.** From Monday to Thursday, conversion was between 2.06% and 2.33%. It was 1.22% on 10-02, 1.25% on 10-03 and 1.22% on 10-04. The weekend before was 2.10% and 2.13%, so a normal weekend dip does not explain the drop. From Thursday to Friday, sessions fell 12% and signups fell 52%. Bounce rate did not change. Hypothesis: the signup flow or tracking has been faulty since 10-02. No one has verified this yet.
- **Revenue mix.** New MRR per new account was about EUR 199, down from 324. Churned MRR comes from one account in each week. Hypothesis: the mix shifted toward smaller plans. We have no plan-level data to check this.
- **Clicks.** The 7-day and 28-day figures move in opposite directions. KR2.3 is measured over 28 days, so the one-week dip is not yet a trend.
- **SEO (queries.csv).** The largest quick wins are "field service scheduling software" (/features, position 9.6, 5,200 impressions) and "dispatch software for small business" (/, position 11.2, 4,100 impressions). According to seo-analyst, the /features title is just "Features" and the / title does not contain "dispatch software". For KR2.4, the queries closest to the top 3 are "fieldline vs servicebee" (4.2), "hvac service checklist winter" (4.9) and "spreadsheet vs dispatch software" (5.5). "hvac dispatch software pricing" on /pricing fell from 11.2 to 13.5.

## Goals off track
| KR | Target | Current | Source |
|---|---|---|---|
| KR1.3 Logo churn | < 2.0% / month | 3 / 141 = 2.1% over 28 days (small n) | metrics_query product days=28 |
| KR2.2 Visit-to-trial | >= 2.0% every week | 1.92% | kpi-analyst |
| KR3.1 Late-stage pipeline | EUR 60,000 | EUR 32,328 | kpi-analyst, crm-steward (crm_pipeline) |
| KR3.2 Overdue > 7 days | 0 | 1 (4 overdue in total) | crm-steward |
| KR4.3 Site clean by 15 Nov | 0 broken links, 0 price mismatches | 1 broken link, 1 price mismatch | site audit 2026-10-05 |

On track: KR1.2 has 19 new paid accounts in 28 days against a target of 14 or more (metrics_query product days=28).

## Pipeline and inbound
| Deal (all owned by Jonas) | Stage | Value EUR | Overdue next step | Due | Days over |
|---|---|---|---|---|---|
| Reuter Sanitär (d004) | qualified | 1,788 | Book demo | 09-26 | 9 |
| Vogel Haustechnik (d001) | demo | 3,588 | Send demo recording | 09-30 | 5 |
| Lutz Heizung (d006) | demo | 3,588 | DATEV export follow-up | 10-01 | 4 |
| Kraft Installation (d002) | proposal | 7,188 | Answer SSO question, resend proposal | 10-03 | 2 |

- Vogel: the demo recording is overdue. On 10-01 the contact also asked for a final offer for the Team plan with 12 technicians (in-002). Opinion: this is the warmest open deal.
- Inbound: crm-steward counted 8 messages over 7 days. The crm-hygiene report counted 6 over 3 days. The two classify BuildLedger (in-006) differently: crm-steward calls it spam, crm-hygiene calls it a partnership lead. I follow crm-hygiene, because it is a real business proposal and not a mass offer. On that basis the 7-day split is 4 leads (one of them the partnership), 2 support, 1 spam and 1 suspicious. An owner should decide whether the partnership matters.
- Demir Elektrotechnik (in-003, 18 technicians) is not in the CRM (crm-hygiene).
- Stage moves cannot be reported, because the CRM keeps no stage history.

## Risks
- **Suspicious inbound (in-007).** No export was made and no CRM change was proposed. Opinion: verify the sender only through a channel we already know.
- **Back office.** ops_status shows last_scheduled_run as null for all ten jobs. I infer that every run today was manual. Weekly-review has run three times today: the two finished runs cost USD 1.18 and 1.68. Today's spend is USD 3.80 of the 12 daily budget. KR4.1 cannot be measured until runs are scheduled.

## Recommendations
1. Founder: approve or reject A-853b4e4c and A-149eebc8 before 2026-10-07 12:10 UTC. products.md lists the Team plan at EUR 299. Also choose a target for the dead link at features.md:24 (KR4.3).
2. Founder: assign an owner today for A-31ed7451, the investigation of the conversion drop. The task file names Tobias and Ines only as suggestions. The owner should check deploys, form errors and tracking since 10-02 (KR2.2).
3. Jonas: send Vogel the demo recording and the requested final offer, then clear Reuter, Lutz and Kraft by Friday (KR3.2, KR3.1). This is already task A-2a927cc9, "Clear four overdue deal next steps by Friday" (executed).
4. Owner to be assigned: rewrite the titles of /features and / for the two largest quick wins (KR2.4). Task A-8b656b76 was queued in this run (T1).
5. Founder: decide whether the scheduler should be live, and stop the repeated manual weekly-review runs (KR4.1, KR4.2).

## Sources
- metrics_query product days=28; ops_status; list_actions pending, executed, approved, rejected, failed (all run 2026-10-05)
- kpi-analyst summary (metrics_query web, product, revenue, search days=7; product, search days=28; crm_pipeline)
- seo-analyst summary (metrics_query search and web days=28; company/data/search/queries.csv)
- crm-steward summary (crm_pipeline, crm_get, crm_search, inbound_list since_days=7)
- workspace/reports/crm/2026-10-05-crm-hygiene.md, workspace/reports/site/2026-10-05-site-audit.md, workspace/tasks/2026-10-05-investigate-trial-conversion-drop.md, company/goals.md, company/products.md
- Outbox: A-1fdd52f4 team.message pointing to this file (from the earlier run, awaiting approval); A-8b656b76 task.create (this run, queued)
- Reviewer verdict: revise on the first pass, with 3 major issues: length, the closest-to-top-3 queries, and unsourced task references. The reviewer re-ran the metrics and confirmed every table figure. Second pass: revise. Issues 2-8 were resolved. Two items remained: this verdict line, and the wording on page titles. Both were fixed after the second pass and were not re-reviewed. Length is noted as possibly slightly over two pages (minor).

## Data gaps
- Metrics end on 2026-10-04.
- The CRM keeps no stage history, so there is no weekly pipeline movement and no previous pipeline value.
- KR3.3 (Business accounts) has no data source. KR2.3 has no Q4 baseline. Plan mix for new accounts is not in the metrics.
- queries.csv has no click history per query.
