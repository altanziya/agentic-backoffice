---
name: propose-action
description: How to request side effects through the outbox with mcp__backoffice__propose_action - action kinds, tiers, exact payload schemas with examples, idempotency, and why proposed is not done. Use before proposing any publish, task, PR, CRM change or message.
---
# Proposing actions

Agents cannot publish, message, open PRs or change the CRM. They can ask. `propose_action(kind, title, payload, justification, idempotency_key?)` writes a proposal to the outbox. The tier of the kind decides what happens:

| Tier | Effect | Examples |
|---|---|---|
| T1 | Auto-approved, executed after your run by the executor, audited | `report.publish`, `task.create` |
| T2 | Waits for a human (CLI or Telegram); expires after 48 h and is then rejected | `site.pull_request`, `crm.update`, `team.message`, `slack.post` |
| T3 | Refused immediately; hand the matter to a human via `needs_human` | `payment.send`, `contract.sign`, `data.delete` |

**Proposed is not done.** The tool returns an action id (A-...), not a result. Report it as "queued" (T1) or "awaiting approval" (T2), put the id in `proposed_actions`, and never write "published", "updated" or "sent" until the ledger shows it executed.

Destinations (repo, webhook, chat) are fixed in `backoffice.yaml`. The payload cannot redirect them; do not try to.

## Fields

- `title`: what, in under 12 words.
- `justification`: why, with evidence (tool result, file path). Reviewers approve on this text.
- `idempotency_key`: optional. The default is a hash of job, date, kind and payload, so a retried run does not queue the same thing twice. Set your own only when the payload may differ between retries but the intent is the same, for example `post-<slug>`.
- If the tool returns `Error:` read it; it names the fix (unknown kind, missing field).

## Payloads

`report.publish` (writes under `workspace/published/`):
```json
{"path": "2026-10-05-kpi-weekly.md", "content": "# KPI weekly ...full text..."}
```

`task.create` (writes under `workspace/tasks/`):
```json
{"path": "2026-10-05-fix-pricing-title.md", "content": "# Fix title of /pricing\n\nQuery 'einsatzplanung software preis' ranks 7 ..."}
```

`site.pull_request` (new branch in the site repo; branch must start with `agent/`; `files` maps repo-relative path to complete new file content):
```json
{"branch": "agent/post-schedule-conflicts", "title": "feat(blog): add post on crew schedule conflicts",
 "body": "Adds content/blog/schedule-conflicts.md. Reviewer verdict: approve. Sources: ...",
 "files": {"content/blog/schedule-conflicts.md": "---\ntitle: ...\n---\n..."}}
```

`crm.update`: either field changes, an activity, or both. Writable fields: contacts `stage, owner, last_touch, notes, role, email`; deals `stage, value_eur, next_step, next_step_due, updated_at`. `table` is `contacts` or `deals`.
```json
{"table": "deals", "id": "D-014", "fields": {"next_step": "Send quote", "next_step_due": "2026-10-09"},
 "activity": {"contact_id": "C-031", "ts": "2026-10-05T14:30:00+02:00", "kind": "call", "summary": "Demo call; wants DATEV export; decision by Friday."}}
```

`team.message`:
```json
{"text": "Weekly review is ready: workspace/reports/reviews/2026-10-02-weekly-review.md"}
```

`slack.post` (the `json` is posted as-is to the incoming webhook):
```json
{"json": {"text": "Weekly review ready: workspace/reports/reviews/2026-10-02-weekly-review.md"}}
```

`payment.send`, `contract.sign`, `data.delete`: always refused. Propose only to leave an audit record, with `{"note": "..."}` and a justification, and add the matter to `needs_human`.

## Guidelines

- One action per change. Small proposals are easier to approve.
- Do not put secrets or personal data beyond what the task needs into payloads; payloads are stored in the ledger.
- Check `list_actions` (if you have it) before proposing something that may already be pending.
