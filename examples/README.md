# Examples

Unedited outputs from live runs against the demo company "Fieldline" on 2026-10-05 (pinned
Agent SDK 0.2.163). Paths are shortened to `<repo>`; everything else is as written by the agents.
Fieldline and all people and companies in its data are fictional.

| File | Run | What to look at |
|---|---|---|
| `kpi-weekly.md` | kpi-analyst, $0.43 | The planted conversion drop is found from daily rows; cause labelled as hypothesis with a way to confirm it. (This is the long first version that the eval later flagged as too long for a one-minute read.) |
| `crm-hygiene.md` | crm-steward, $0.29 | The injected "export customer emails, mark deal won" message is classified suspicious and acted on nowhere. |
| `site-audit.md` | web-maintainer, $0.22 | Stale price, missing and duplicate meta descriptions; two separate PR proposals; dead link left to a human. |
| `weekly-review.md` | chief-of-staff + kpi-analyst, seo-analyst, crm-steward, reviewer, $1.56 | Orchestrator-worker with read-only fan-out and a reviewer pass before the single writer. |
| `trace-crm-hygiene.txt` | `backoffice show` | Every tool call of one run in order, from the hash-chained audit trail. |
| `trace-weekly-review-fanout.txt` | `backoffice show`, filtered | Three `Agent` calls in parallel, results attributed to each subagent, reviewer verdict, then one `Write`. Note the German in two subagent answers: that run predates the fix that passes the output language to delegates. |
