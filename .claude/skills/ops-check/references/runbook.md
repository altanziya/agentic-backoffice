# Runbook: symptom, likely cause, fix

Commands are run by a human. Statuses and subtypes are as recorded in the ledger (`backoffice runs`, `backoffice show <run_id>`).

| Symptom (ledger) | Likely cause | Fix |
|---|---|---|
| Runs fail with an authentication error; several jobs at once; error mentions login or expired token | Claude auth expired (OAuth token or API key) | Log in again or refresh the key on the host; run `backoffice doctor`; `backoffice run <job>` for the most important job. Check that the key is in the environment, not in files. |
| `budget_blocked` | Daily or monthly budget reached (`budgets` in `backoffice.yaml`), or a job's own `monthly_budget_usd` | Check `backoffice budget`. If spend is legitimate, raise the limit deliberately; if one job spiked, find it with `backoffice runs --job <job>` and look at cost per run. Do not raise limits to clear an alert without reading the spike. |
| `preflight_failed` | A `requires` condition not met, for example a missing file the job depends on (`file:workspace/reports/intel?`), or a data source down | Read the error in `backoffice show <run_id>`; start the upstream job (`backoffice run <job>`) or restore the source; then retry. |
| `timeout` | Run exceeded `timeout_minutes`; large source, slow tool, or a loop | Look at the audit trail for repeated calls. Narrow the brief or raise `timeout_minutes` for that job only. |
| `error_max_turns` | Hit `max_turns`; the task is too broad or the agent is retrying | Inspect tool calls in `backoffice show`. Split the job, tighten the skill, or raise `max_turns` for that job. Raising alone hides loops. |
| Repeated `tools_denied` in a run | The prompt or skill asks for something policy forbids: a write outside `writes`, an unlisted domain, a tool not in `tools`, delegation to an undeclared agent | Treat as a defect in the agent definition or skill, not an incident. Read the denial reasons in the audit trail, fix the instruction (or deliberately extend `writes`/`web_domains` in the agent file, reviewed). Never weaken the guard to silence it. |
| Pending action past or near `expires_at`; later `expired` | Nobody decided within `expire_hours` (48); expiry means rejected | `backoffice approvals` and approve or reject now. If it already expired, ask the agent to propose again (next run) and consider the Telegram channel for faster decisions. |
| Action `failed` | Handler error: payload invalid, repo not a git repo, branch exists with different content, env var for webhook missing, destination down | `backoffice show` on the action's run and the action row for the error. Fix the cause (payload, env, repo) then `backoffice retry <action_id>`. Handlers are idempotent; an existing branch is reported, not overwritten. |
| Missed schedule slot: no run for a job in its last slot, no `skipped` or `failed` row | `backoffice tick` is not being called (cron or timer stopped, host asleep), or the catch-up window (default 90 minutes) passed | Check the scheduler on the host (`deploy/`), run `backoffice tick` manually, `backoffice jobs` to see next slots. Run the job with `backoffice run <job>` if it is still needed. |
| Job `skipped` | Overlap lock held by a previous run, or the kill switch is on | `backoffice runs` for a long-running previous run; `backoffice kill off` if the switch was left on. |
| Cost spike on one run | Large inputs, many retries, or a delegate loop | Compare turns and cost to the job's median; read the audit trail; tighten the brief or `max_budget_usd`. |

## Reading a failure

1. `backoffice runs --job <job>`: pattern over time.
2. `backoffice show <run_id>`: audit trail with tool calls and denials.
3. `backoffice doctor`: deterministic checks.
4. Fix the cause, then `backoffice run <job>` (`backoffice retry` is for failed *actions*). A successful run is never repeated automatically.
