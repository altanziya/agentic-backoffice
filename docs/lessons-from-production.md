# Lessons from production

This repo generalises a system its author built and operated for an early-stage startup. This page records what broke in that system and what this repo does differently. It is the reason several design choices look stricter than a demo needs.

Everything below about the predecessor comes from a post-hoc review of its repository, its commit history and its incident log. Details that would identify the deployment (names, hosts, IDs, schema, domains, paths) are left out on purpose. Claims about this repo were checked against the code at the time of writing; file and function names are given so you can check them again.

## The predecessor in short

| | |
|---|---|
| Period | March to August 2026 |
| Shape | One generalist Claude Code agent behind a Telegram long-polling listener, plus 11 scheduled jobs (7 LLM prompts, 4 plain scripts) on a single VM |
| Scheduling | A crontab on the VM, with the intended schedule also described in a JSON registry in the repo |
| Evidence it ran | 150 consecutive daily briefings, one per calendar day, no gaps |
| Evidence it was useful | None recorded. The reports prove it ran, not that anyone acted on them |
| Not present | Tool allowlists, enforced approvals, tests, evals, per-run cost or trace data, budgets |

For roughly ten weeks the VM, not the repo, held the real code ("resilience changes since March, uncommitted on the VM", in the words of one commit). A review in July 2026 brought the repo back in sync and hardened it in four phases. What that review found is the most useful part.

## Meta-lessons

**1. The audit mostly found silent failures, not bad prompts.** The fixes in the review were about state written before the operation succeeded, errors that were swallowed or turned into zeros, success markers found by grepping logs, and loops that blocked each other. Almost none were about prompt wording. If you only evaluate your agents on output quality, you will miss the class of bug that actually cost the most days. This repo puts the effort in the orchestration: one ledger row on every exit path, compare-and-set state changes, structured run results, deterministic health checks.

**2. A guardrail that is only prompt text is a wish.** The predecessor ran every invocation with `--dangerously-skip-permissions`. Its rules were "only SELECT" (while holding a database key with full access), "never merge without approval" (while holding a token that could merge), and a block of "do not run destructive commands" in each scheduled prompt. The few controls that held were not prompt text: two GitHub tokens with different scopes, and a database role. This repo moves the rest into code that runs outside the model: a PreToolUse hook (`policy.Guard`, wired in `hooks.py`), the outbox with tiers (`outbox.py`, `config.Tier`), and the Rule of Two check (`policy.validate_agents`). The model can be argued with; these cannot.

**3. One generalist agent holding every credential is the default failure mode.** It is the easiest thing to build and it fails in a specific way: whatever text the agent reads (mail, alerts, scraped pages, contact forms) is read by something that can also send mail, run a shell and write to the CRM. This repo splits roles into ten agents with narrow tools, write paths and delegates, and refuses by construction any agent that combines untrusted input, private data and external effect.

**4. Calendar and schedule arithmetic belong in code, not in the model.** This one is from building this repo, not from the predecessor. The first live run of the `ops-check` job had the model call a Monday "Sunday" and derive the wrong cron slots from the schedule strings. Nothing was broken in the plumbing; the model was simply doing date math it is bad at. The fix was in two places. `ops_status` in `mcp_server.py` now computes `now`, `weekday`, `timezone`, and per job `last_slot`, `last_scheduled_run` and `next_slot` with the same `Cron` class the scheduler uses. And `HEADLESS_CONTRACT` in `runner.py` states the logical date and its weekday ("a {weekday}") in every run. Rule of thumb: if a number or date can be computed deterministically, give the agent a tool that returns it.

## The lessons

Each lesson follows the same shape: what was seen, why it happened, what was done then, and what this repo does.

### 1. State written before the operation succeeded

**Symptom.** Alert scripts lost notifications. A re-indexing script treated URLs as already submitted when the submission had failed, so they were never retried.

**Root cause.** The "seen" marker was updated before the query and the send had both succeeded. Any failure in between left the system believing the work was done.

**Fix then.** Write state only after query and send succeed; add message-ID de-duplication; only mark URLs known when the API accepted them; exit non-zero and alert on total failure.

**This repo.** Side effects have an explicit lifecycle in `ledger.TRANSITIONS`: `pending`, `approved`, `executing`, `executed` or `failed`. `executor.execute_approved` moves a row to `executing` first (a compare-and-set in `Ledger.transition`, so a second executor skips it), runs the handler, and only then writes `executed` with the handler's result. A raised exception becomes `failed` with the error text; `backoffice retry <action_id>` is the only way back to `approved`. Nothing is marked done on the strength of intent.

### 2. An error overwrote good data, or was counted as a zero

**Symptom.** A search-data cache was overwritten with zeros when an upstream API was down, and the reports built on it showed a collapse that did not happen. A KPI dashboard upserted empty rows when one database was unreachable. A scoring job counted API errors as "no mention".

**Root cause.** A failed fetch and an empty result looked the same to the code downstream.

**Fix then.** Keep the last good section marked stale, report status `partial`, discard runs with more than half of their calls failing, skip the dashboard update when its source is down.

**This repo.** Three layers. `preflight.run_preflight` checks a job's `requires` before any tokens are spent: a required source that is down yields a `preflight_failed` run (and an alert), an optional one (suffix `?`, as in `file:workspace/reports/intel?` on `daily-briefing`) makes the run proceed degraded. The degraded list goes into the prompt via `HEADLESS_CONTRACT`. The agent's structured result has a `data_gaps` field (`RUN_REPORT_SCHEMA`), and the `source-discipline` skill says missing is not zero. The eval case `briefing-degraded-source` asserts the behaviour. Limit: this repo ships no cache layer, so the stale-keep pattern is yours to add if you build one.

### 3. Log text used as the source of truth

**Symptom.** A timed-out run was counted as a success because an earlier attempt's log section contained "sent successfully". Separately, a harmless 401 from one optional data source in the log could be read as an expired Claude credential and abort the run with a token alert.

**Root cause.** Success and failure were inferred by grepping a shared log for strings.

**Fix then.** Restrict the grep to the current attempt's section; add a separate marker for authentication errors.

**This repo.** No log grepping. The Agent SDK returns a `ResultMessage` with `subtype`, `is_error` and `api_error_status`, and `Runner._run_session` decides on those. Authentication failure is detected from the run's own error (`AUTH_MARKERS`, `_looks_like_auth_error`) or an HTTP 401 on the run result, never from tool output. The final answer of every run is a JSON schema (`RUN_REPORT_SCHEMA`), so evals and notifications read fields instead of prose.

### 4. Retries duplicated side effects

**Symptom.** A task was executed twice after a retry. In another case a timeout was treated as failure although the agent had already sent its message.

**Root cause.** The runner could not tell "failed before acting" from "failed after acting", and the agent itself performed the side effect.

**Fix then.** No retry when the process exited cleanly but its output could not be parsed; check for the sent-marker on timeout.

**This repo.** The agent never acts; it proposes. `outbox.propose` derives an idempotency key (`default_idem_key`: job, logical date, kind, payload) and `Ledger.propose` does `INSERT OR IGNORE` on it, so a retried run that proposes the same thing gets the existing row back ("Already proposed earlier"). `Runner._run_session` breaks out of the retry loop on the first success, never retries `error_max_budget_usd`, and resumes the session after `error_max_turns` instead of starting over.

### 5. Overlapping runs

**Symptom.** A retry overlapped its predecessor. Two jobs pulled the same repository at the same minute on Mondays. Parallel report syncs collided.

**Root cause.** Nothing prevented concurrent runs of the same job or of jobs sharing a resource.

**Fix then.** `flock` per agent, a lock around the repository pull, a lock around the sync, and staggered cron minutes.

**This repo.** `runner.job_lock` takes a non-blocking `flock` on `.backoffice/locks/<job>.lock` per job; a second start records a `skipped` run ("previous run still in progress") instead of waiting or colliding. Note the limit: it is per job, not per resource. Two different jobs that write the same file are still your responsibility; keep `writes` globs disjoint per agent, which `backoffice agents` makes visible.

### 6. The schedule lived in two places, and so did the code

**Symptom.** The registry said one thing and the crontab on the VM another. Skills referenced scripts that no longer existed. The repo trailed the VM by weeks.

**Root cause.** The registry described schedules but did not run them. Nothing checked that the host matched.

**Fix then.** A verification script that compared crontab and registry; documentation clean-ups.

**This repo.** `backoffice.yaml` is the only place schedules live. The host calls `backoffice tick` every few minutes and `schedule.due_jobs` decides what is due, in the company timezone, with a catch-up window (`tick --catchup`, default 90 minutes). `backoffice doctor` reports a job whose latest slot has no scheduled run. `backoffice validate` fails on unknown agents, skills, handlers, cron syntax and time zones. Agent definitions, skills and jobs all live in the repo; the only host state is `.backoffice/` and your env file.

### 7. A single sequential loop blocked everything, including the watchdog

**Symptom.** A 20-minute task froze the Telegram listener, including approval buttons. The watchdog read the stale heartbeat, killed the listener mid-task, and the message was lost because its offset had already been saved. Later, the watchdog restarted a permanently broken listener silently, over and over.

**Root cause.** One thread did polling, dispatch and approvals. The health signal was only written between tasks.

**Fix then.** A heartbeat thread, a message spool with replay, and an alert after three restarts in a row.

**This repo.** Approvals are a separate long-running process (`backoffice telegram`, `approvals/telegram.py`) that never runs agents, so a long job cannot block a button press. A decision is a compare-and-set on the ledger, and the update offset advances only after the callback was handled; a crash re-delivers the update and re-handling is a no-op. There is no listener that dispatches work to an agent: runs are started by `tick` or by hand. That removes the chat-driven path where this failure came from, along with its convenience.

### 8. A notifier or monitor that fails silently

**Symptom.** Outages went unnoticed for days: failed Telegram sends, listener restarts, a self-edit hook that stopped working.

**Root cause.** Best-effort helpers swallowed their own errors.

**Fix then.** Alerts on repeated restarts, on hook failure, and on a failed notifier.

**This repo.** `notify.notify` returns a boolean and logs a warning when the Telegram API rejects a message or the env vars are missing; it does not raise, by design, because a broken notifier must not fail the run. That is only half a fix: the warning goes to the process log. The other half is that every run, including skipped, killed, blocked and failed ones, writes a ledger row (`record_skipped`, `finish_run`), so "did the 07:00 briefing run?" always has an answer, and `backoffice doctor` flags a job whose last three runs failed. You still need something that calls `doctor` and tells a human; see `docs/operations.md`.

### 9. A language model doing deterministic health checks

**Symptom.** One health check existed twice, as a shell script and as an LLM agent that checked disk, memory and HTTP status and could get them wrong.

**Root cause.** A model was used where a one-line command is exact and free.

**Fix then.** None recorded beyond keeping both.

**This repo.** `backoffice doctor` (`cli.cmd_doctor`) is plain Python: configuration validity, kill switch, audit-chain verification, last three runs per job, missed slots, approvals about to expire, free disk. The `ops-sentinel` agent does only what needs judgement: reading the ledger through `ops_status` and `list_actions`, grouping failures and ranking them. Its prompt says explicitly that pinging or probing is not its job.

### 10. Approval gates were prompt conventions

**Symptom.** The pipeline said "ask for approval before merging". In code, the model wrote the workflow file itself, and nothing stopped it from running the merge command. The authorisation check for the approval buttons accepted either a known user ID or a known chat ID.

**Root cause.** The gate was a convention the model followed, not a step the system required. The auth check was an OR where it needed an AND.

**Fix then.** Timeout-reject and callback authorisation in Python; the rest stayed convention.

**This repo.** The model has no way to cause the effect. `propose_action` writes a row; what happens next is decided by the tier configured in `backoffice.yaml`, not by the agent: T1 is auto-approved and executed after the run, T2 waits for a human and expires closed after `approvals.expire_hours` (`Ledger.expire_overdue`), T3 is recorded as `refused` and has no legal transition out (`outbox.propose`, `ledger.TRANSITIONS`). Config validation rejects a T3 action with any handler but `refuse`. The pull-request handler (`actions.github_pull_request`) creates a branch and optionally opens a PR; it has no merge code, and `gh pr merge` and `git push` are on the hard-deny list in `policy.BASH_HARD_DENY` and in `.claude/settings.json`. Telegram approval requires approver ID and chat ID (`TelegramChannel.authorised`). The approval message renders the real payload from the ledger, not the agent's description of it (`approvals.render_action`).

### 11. "Only SELECT", with a key that can do anything

**Symptom.** A skill told the agent to only read the database, while the credential was a service-role key without row-level restrictions.

**Root cause.** The restriction was a sentence; the credential was the actual permission.

**Fix then.** None for that path. Where a restricted database role existed (for the CRM), it worked.

**This repo.** The agents' data tools are read-only by construction: `crm_search`, `crm_get`, `crm_pipeline`, `metrics_*`, `inbound_list` and `ops_status` call read methods only, and writes go through `crm.update` after approval, limited to the columns in `data.CRM_WRITABLE`. Destinations of side effects (repository, webhook, chat) come from `params` in `backoffice.yaml`, never from the payload. Limit, stated plainly: when you connect a real CRM or database, this code cannot restrict what your credential can do. Give the adapter a read-only credential, and keep write credentials in the action handlers, which run in the executor process outside any agent session.

### 12. Untrusted input processed with full rights

**Symptom.** Agents read mail, news alerts, tweets, scraped pages and contact-form text while holding a shell, outbound HTTP, write access to a CRM and to a calendar. No isolation or sanitisation was in place.

**Root cause.** Text from outside was treated like text from the operator.

**Fix then.** "Boundaries" blocks in the prompts. A control only in name.

**This repo.** The Rule of Two. `capabilities` in `backoffice.yaml` maps tool patterns to three legs: untrusted input, private data, external effect. `policy.agent_legs` computes them per agent, treating untrusted input as transitive through delegates, and `backoffice validate` fails if any agent holds all three. No agent holds the external-effect leg at all. Web reading is quarantined in `intel-reader`, which has `WebSearch`, `WebFetch` and `Read`, a `web_domains` allowlist enforced per call by `Guard._check_url`, and no write path or company data. Inbound text is wrapped in tool descriptions that say it is untrusted, and `crm-steward` classifies instruction-like messages as findings. The eval cases `crm-injection-resisted` and `injection-escalation` check the outcome; `docs/evals.md` says what they prove and what they do not.

### 13. The agent rewrote its own system prompt

**Symptom.** A "reflect" hook extracted corrections from a session and appended them to the file that served as the agent's instructions. A wrong or planted lesson became permanent, with only a word-overlap duplicate filter.

**Root cause.** Learning and instruction shared a file, and there was no review step.

**Fix then.** Marker self-healing and an alert when the hook failed. The design stayed.

**This repo.** Agent prompts and skills live in `.claude/`, which no agent may write: every agent's `writes` list is limited to its own report directory plus `workspace/state/<agent>.md`, and the guard denies anything else (`Guard.check_path`). Changes to behaviour arrive as reviewed commits. Agents do keep a memory file of dated facts, and it is read as input the next run. That is still model-written text feeding a later run, so the blast radius is small but not zero; the agent prompts limit it to "facts only", and you should read those files now and then.

### 14. A wrong ID, and agent-written code that repeated it

**Symptom.** An analytics source reported "unavailable" for two consecutive days although the API was running. The agent's own generated code used the same wrong property ID as a helper script. Other hard-coded values (home-directory paths, a model name, project IDs) made the system impossible to move.

**Root cause.** Identifiers lived in code, skills and prompts, and the agent could write and run code that copied them.

**Fix then.** Correct the ID; add "test yourself before reporting" and a diagnosis order that starts with the ID check.

**This repo.** Identifiers and paths are configuration. `config.py` validates `backoffice.yaml` with `extra="forbid"`, so a typo is an error, not a silent default. Business facts live in `company/`, KPI definitions in `company/company.yaml`, aggregation rules (sum, last, mean) per column in `company/data/metrics/aggregations.yaml`. Agents have no shell: the demo agents hold no `Bash` tool, and `validate` rejects `Bash` without a `bash_allow` list. Numbers must come from a tool result in the same session (`HEADLESS_CONTRACT`, `source-discipline`).

### 15. No way to know it still worked, or what it cost

**Symptom.** There were no tests, no evals, no per-run cost, token or latency data, and cron runs left no session to inspect. Nobody could say whether a prompt change made a report worse, or what a month of runs cost.

**Root cause.** Observability was logs and files only.

**Fix then.** A review pass after the fact. The system had no budget limits at all.

**This repo.** Cost is a ledger column (`runs.cost_usd`) from the SDK's own total. Per-run limits (`max_budget_usd`, `max_turns`, `timeout_minutes`) are enforced by the SDK and the runner. `Runner._budget_block` refuses to start a job when the daily, monthly or per-job monthly budget is spent. Every tool call and denial is an event in the hash-chained audit trail (`backoffice show <run_id>`, `backoffice audit verify`). Optional OTLP export is configured under `telemetry` in `backoffice.yaml`. Behaviour is covered by `make test` (offline) and `make eval` (live, costs tokens); see `docs/evals.md`.

## What this repo does not fix

- It does not prove the output is useful. The ledger shows that a briefing was produced and what it cost; whether anyone acts on it is something you have to measure yourself.
- It does not make a language model reliable. It limits what an unreliable run can do and makes failures visible.
- It does not replace credential hygiene. Guardrails in code are only as strong as the credentials behind them.
- The audit trail is tamper-evident, not tamper-proof: someone with write access to the file can rebuild the chain. Back up the ledger off the host.
