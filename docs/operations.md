# Operations

Runbook for running agentic-backoffice on a small VM. It assumes one Linux host, one operator, and the layout used by the files in `deploy/`.

| Path | Purpose |
|---|---|
| `/opt/backoffice` | Your fork, checked out, with `.venv/` |
| `/opt/backoffice/.backoffice/` | Ledger (`ledger.db`), job locks, kill switch, and the demo CRM database (`crm.db`). The state that matters. Never in git |
| `/opt/backoffice/workspace/` | Agent output: reports, drafts, tasks, published files, per-agent memory, the website checkout |
| `/etc/backoffice.env` | Secrets, loaded by the service manager. Never in the repo |
| `/var/lib/backoffice` | Home directory of the `backoffice` user (the bundled Claude Code CLI keeps its own state there) |

## How it runs

Nothing is a daemon except the optional approval service. The host calls `backoffice tick` every five minutes. `tick` reads the schedules in `backoffice.yaml`, works out which jobs have a slot that is due in the company timezone (`timezone` in the config, not the host's), and runs each once, one after another. A job is one bounded Agent SDK session. After each run the runner executes approved T1 actions and asks for approval of pending T2 actions.

Behaviours worth knowing before you operate it:

- **A slot is consumed by any scheduled attempt.** A scheduled run of any outcome (success, failed, skipped, killed, budget-blocked, preflight-failed) counts as the slot's run. `tick` does not retry a failed job at the next tick; the runner's own retries (`retries`, default 1) happen inside the run. After you fix a cause, run the job yourself with `backoffice run <job>`.
- **Catch-up is bounded.** A slot missed by the host (reboot, timer stopped) is still run if it is within `tick --catchup` minutes (default 90). Older misses are skipped and show up in `backoffice doctor`.
- **`tick` exits non-zero if a job failed**, was blocked by the budget, or failed preflight. Under systemd that shows the unit as failed (`systemctl --failed`); the timer keeps firing. Skipped and killed jobs do not count.
- **Overlap is handled per job** with a lock file in `.backoffice/locks/`. A second start of the same job is recorded as `skipped` ("previous run still in progress").

## Install on a VM

Prerequisites: Python 3.11 or newer, git, network access to the Anthropic API (and Telegram if you use it).

```sh
sudo useradd --system --create-home --home-dir /var/lib/backoffice \
  --shell /usr/sbin/nologin backoffice
sudo git clone <your-fork-url> /opt/backoffice
sudo chown -R backoffice:backoffice /opt/backoffice
sudo -u backoffice python3 -m venv /opt/backoffice/.venv
sudo -u backoffice /opt/backoffice/.venv/bin/pip install -e /opt/backoffice
sudo -u backoffice -H sh -c 'cd /opt/backoffice && .venv/bin/backoffice validate'
```

`backoffice demo reset` refuses to run unless `company/company.yaml` contains `demo: true`; remove that line in your fork. On the demo it regenerates the demo data in `company/data/`, delete `.backoffice/` (ledger, locks, CRM database) and empty `workspace/` outputs. They exist to reset the demo, and evals call the same function on a throwaway copy only.

Create the env file (see [Credentials](#credentials-and-environment)), then install the units:

```sh
sudo install -m 600 -o root -g root /dev/null /etc/backoffice.env
sudoedit /etc/backoffice.env
sudo cp /opt/backoffice/deploy/systemd/backoffice-tick.service \
        /opt/backoffice/deploy/systemd/backoffice-tick.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now backoffice-tick.timer
systemctl list-timers backoffice-tick.timer
```

Check it:

```sh
sudo -u backoffice -H sh -c 'cd /opt/backoffice && .venv/bin/backoffice tick --dry-run'
sudo systemctl start backoffice-tick.service     # a real tick, now
journalctl -u backoffice-tick.service -n 50
```

`tick --dry-run` prints which jobs are due and runs nothing.

To run one job by hand with the same environment the service has:

```sh
sudo systemd-run --pty --wait --collect --uid=backoffice \
  -p WorkingDirectory=/opt/backoffice -p EnvironmentFile=/etc/backoffice.env \
  -E HOME=/var/lib/backoffice -E BACKOFFICE_ROOT=/opt/backoffice \
  /opt/backoffice/.venv/bin/backoffice run ops-check
```

A shell alias saves typing for the read-only and approval commands, which need no secrets:

```sh
alias bo='sudo -u backoffice -H env BACKOFFICE_ROOT=/opt/backoffice /opt/backoffice/.venv/bin/backoffice'
bo approvals
```

### The unit files

| File | Purpose |
|---|---|
| `deploy/systemd/backoffice-tick.service` | One `backoffice tick`, `Type=oneshot`. Runs as `backoffice`, `EnvironmentFile=/etc/backoffice.env`, `NoNewPrivileges`, `ProtectSystem=strict` with `ReadWritePaths` limited to the repo and the home directory, `PrivateTmp`, `ProtectHome`, and a `TimeoutStartSec` ceiling |
| `deploy/systemd/backoffice-tick.timer` | `OnCalendar=*:0/5`, `Persistent=true` so a run is triggered on boot if slots were missed while the host was off |
| `deploy/systemd/backoffice-telegram.service` | `backoffice telegram`, `Restart=always`, same hardening |
| `deploy/crontab.example` | One-line cron alternative |
| `deploy/Dockerfile` | Image with the package and non-root user; repo and state mounted at run time |

The hardening settings were written for a typical Debian or Ubuntu host. They have not been verified on every distribution. After a change, run `systemd-analyze security backoffice-tick.service` and a real tick, and loosen only what breaks.

### Telegram approvals

Set `approvals.channel: telegram` in `backoffice.yaml` and these variables in the env file: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `TELEGRAM_APPROVER_IDS` (comma-separated user IDs). A button press is accepted only if the user is in the approver list and the chat matches the configured chat. Then:

```sh
sudo cp /opt/backoffice/deploy/systemd/backoffice-telegram.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now backoffice-telegram.service
```

The service never starts agents. It sends buttons for pending actions, records approve and reject decisions in the ledger, and runs the executor after an approval. Two processes (the tick and this service) write the same SQLite ledger; this is safe, because state changes are compare-and-set and the database runs in WAL mode with a busy timeout. If the service is down, buttons stay unanswered, and pending actions expire closed after `approvals.expire_hours`. You can still decide with `backoffice approve <id>` and `backoffice reject <id>`.

## Cron instead of systemd

Use `deploy/crontab.example`. It calls `tick` every five minutes under `flock` so a slow tick cannot overlap the next one, loads the env file, and sends output to syslog. Cron has no equivalent of `Persistent=true`: after a reboot, the next tick still catches up within the catch-up window.

For cron the env file must be readable by the `backoffice` user (mode 0640, group `backoffice`), because cron runs as that user rather than as root. Keep the file outside the repo either way. Cron is a poor fit for the Telegram service; use systemd for that one.

## Docker

`deploy/Dockerfile` builds an image with the package installed under a non-root user (uid 10001). It does not contain your agents, skills, company files, or state. Mount the repo and keep `.backoffice/` persistent; the header of the Dockerfile has a complete `docker run` command with a read-only root filesystem, dropped capabilities and tmpfs mounts.

```sh
docker build -f deploy/Dockerfile -t agentic-backoffice .
```

Notes:

- The container runs one `backoffice tick` and exits (`CMD ["backoffice", "tick"]`). Schedule the `docker run` from the host with a timer or cron entry, every five minutes. The schedule inside `backoffice.yaml` stays the single source.
- The Claude Agent SDK package bundles the Claude Code CLI, so the image has no separate Node.js or `claude` install.
- Pass secrets at run time (`--env-file`, or your orchestrator's secret mechanism). Nothing is baked into the image. Keep the build context free of `.env` files; `.gitignore` already excludes them, but Docker does not read it.
- If `.backoffice/` is not on a persistent volume, you lose the ledger, budgets, idempotency keys and audit trail on every run. This is the same failure as running on an ephemeral CI runner; see below.
- The Dockerfile installs `git`, which the `site.pull_request` handler needs. Install `gh` too only if you set `push: true` for that action.
- This image was written for this repo but not built in the environment where the docs were written. Build and test it before you rely on it.

## Credentials and environment

Variables are read by the process that needs them, from the environment. See `.env.example`.

| Variable | Needed for |
|---|---|
| `ANTHROPIC_API_KEY` | Claude access with an API key. Set this or the OAuth token |
| `CLAUDE_CODE_OAUTH_TOKEN` | Claude access with a subscription plan. Create it with `claude setup-token` on a machine where you are logged in |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | Telegram approvals and notifications (`approvals.channel` or `notify.channel` set to `telegram`), and the `team.message` action |
| `TELEGRAM_APPROVER_IDS` | Comma-separated Telegram user IDs allowed to approve |
| `SLACK_WEBHOOK_URL` | Only for the `slack.post` action (`url_env` in `backoffice.yaml`). Must be an `https://` URL |
| `BACKOFFICE_ROOT` | Repo root. The units set it; otherwise the CLI looks for `backoffice.yaml` upward from the working directory |
| `BACKOFFICE_KILL` | Set to `1` to block all job starts (see kill switch) |

Rules:

- Use one Claude credential, not both. A subscription token is subject to the plan's usage limits; an API key is billed per token. The budgets in `backoffice.yaml` track cost as reported by the SDK either way.
- `/etc/backoffice.env` uses plain `KEY=value` lines (no `export`). Mode 0600 owned by root for systemd, 0640 with group `backoffice` for cron.
- Agents cannot read secrets. The guard denies `.env`, key, credential and similar path patterns, and in headless runs anything outside the repo. Data credentials belong to the MCP server process and the action handlers, not to the agent's tools.
- `backoffice doctor` only notes whether a Claude credential is in the environment. It does not test that it works. An invalid credential shows up as a failed run with an `AUTH ERROR` notification.

## Daily routine

About five minutes:

```sh
bo approvals          # pending T2 actions; approve or reject
bo approve A-1a2b3c4d --note "ok"
bo reject  A-5e6f7a8b --note "wrong price"
bo doctor             # deterministic health checks
bo budget             # spend today and this month, per job
bo runs --limit 20    # recent runs, status, cost, errors
```

`bo approve` approves and executes in one step; `--no-execute` approves only. Approvals expire (`expire_hours`, 48 in the shipped config), and expired means rejected. `bo approvals --status expired` lists what lapsed; `--status failed` lists actions whose handler errored, which you can re-queue with `bo retry <action_id>` after fixing the cause.

Look at a run in detail:

```sh
bo show R-20261005-abc123      # audit trail: tool calls, denials, proposals
```

`doctor` exits non-zero when there is a problem. It checks configuration validity, the kill switch, the audit chain, the last three runs of each job, missed schedule slots, approvals expiring within six hours (as a note), and free disk space. The `ops-check` job (daily, with the `ops-sentinel` agent) adds an interpretation of the ledger on top, and `.claude/skills/ops-check/references/runbook.md` maps symptoms to fixes.

Weekly: run `bo audit verify`, confirm the latest backup restores, skim `workspace/state/*.md` (agent memory files), and glance at denied tool calls. Repeated denials mean an agent definition or skill asks for something policy forbids; fix the instruction, do not widen the policy.

Something outside this system should tell you when the host or the timer itself is down, because a stopped timer produces no failed runs. A dead-man's switch that expects a ping after each tick, or a monitor on the VM, covers it.

## Kill switch

```sh
bo kill on       # creates .backoffice/KILL; no job starts until 'bo kill off'
bo kill off
```

Setting `BACKOFFICE_KILL=1` in the environment has the same effect for job starts. Every blocked start is recorded as a `killed` run. What it does not do:

- It does not stop a session that is already running. Stop the unit (`sudo systemctl stop backoffice-tick.service`) or kill the process.
- Approved actions are not executed while the switch is on: the executor checks it before running any handler. Approvals are still recorded, so the queue is intact when you turn it off.
- Slots that fall in the kill window are consumed, not queued. After `bo kill off`, start what you need with `bo run <job>`.

## Budgets

| Limit | Where | Enforced by |
|---|---|---|
| Per run | `max_budget_usd` (defaults, per job) | Agent SDK, includes subagents |
| Per run | `max_turns`, `timeout_minutes` | Agent SDK and runner |
| Per job per month | `monthly_budget_usd` on the job | Runner, before the session starts |
| All jobs per day, per month | `budgets.daily_usd`, `budgets.monthly_usd` | Runner, before the session starts |

Days and months are computed in the company timezone. The check happens before a run starts, using costs of runs that have finished, so spend can exceed a daily or monthly limit by up to one run (and a run in progress is not cut off at the daily limit). Choose limits with that margin in mind. A run refused by a budget is recorded as `budget_blocked` and the operator is notified; raise the limit deliberately, after reading the cost per run in `bo runs`.

## Backups

`.backoffice/ledger.db` is the system's memory: runs, the approval queue, and the audit chain. It is SQLite in WAL mode, so do not copy the file with `cp` while jobs may be running. Use the SQLite online backup:

```sh
sudo apt-get install -y sqlite3
sudo -u backoffice mkdir -p /var/backups/backoffice
sudo -u backoffice sqlite3 /opt/backoffice/.backoffice/ledger.db \
  ".backup '/var/backups/backoffice/ledger-$(date +%F).db'"
```

Run it daily from cron or a timer, keep a few weeks, and copy the result off the host. Do the same for `/opt/backoffice/.backoffice/crm.db` if you use the shipped file-backed CRM adapter, because that file then holds the live CRM state. Back up `workspace/` as well (reports, drafts, memory files); it is not in git.

Restore: stop the services, copy the backup over `.backoffice/ledger.db` (and remove any `ledger.db-wal` and `ledger.db-shm` next to it), start the services, then run `bo audit verify` and `bo doctor`. The ledger contains personal data when your agents handle CRM records; see `docs/governance.md` for retention.

## Rotating tokens

| Credential | Steps |
|---|---|
| Claude OAuth token | Run `claude setup-token` where you are logged in, replace `CLAUDE_CODE_OAUTH_TOKEN` in `/etc/backoffice.env`. The next tick uses it; the Telegram service does not use it |
| Anthropic API key | Create a new key in the console, replace `ANTHROPIC_API_KEY`, revoke the old one |
| Telegram bot token | Revoke and reissue with the bot's owner in Telegram, replace `TELEGRAM_BOT_TOKEN`, `sudo systemctl restart backoffice-telegram.service` |
| Slack webhook | Regenerate in Slack, replace `SLACK_WEBHOOK_URL` |
| Any adapter credential you added | Same pattern: replace in the env file, restart long-running units |

Verify with a cheap run, for example `bo run ops-check` through the `systemd-run` command above (its budget cap is 0.30 USD in the shipped config). An expired Claude credential stops the run at once with an `AUTH ERROR` notification instead of retrying. Put the expiry of any long-lived token in a calendar.

## Upgrading the Agent SDK

The SDK version is pinned in `pyproject.toml` on purpose, because its behaviour (options, hooks, result fields, bundled CLI) moves between releases. Treat a bump as a change to the system.

1. On a development machine, change the pin and reinstall: `.venv/bin/pip install -e '.[dev]'`.
2. `make test` (offline), then `make validate`.
3. Run the evals, with several trials for the cases that matter: `make eval TRIALS=3`. This spends tokens; see `docs/evals.md`.
4. Compare cost and failures with the previous results in `evals/results/`. Read at least one real run's audit trail (`backoffice show <run_id>`) for new tool behaviour.
5. Commit, deploy (`git pull` on the host, `.venv/bin/pip install -e .`), and watch the next day's runs.

To roll back: revert the commit and reinstall.

## Why not GitHub Actions cron as the scheduler

It looks convenient and does not work well here. A scheduled workflow runs on a fresh, ephemeral runner, and this system keeps state that has to survive between runs:

- **Ledger.** `.backoffice/ledger.db` holds the run history, the approval queue and the audit chain. On a fresh runner it starts empty every time. Pending approvals vanish, and `doctor` and `ops-check` have nothing to read.
- **Budgets.** Daily and monthly limits are computed from the ledger. With an empty ledger they never trigger.
- **Idempotency and scheduling.** `tick` decides what is due from the last scheduled run in the ledger, and proposals de-duplicate by key in the ledger. Without it, every tick sees every slot in the catch-up window as unrun, and retried runs queue the same actions again.
- **Locks and kill switch.** Both are files in `.backoffice/`.
- **Workarounds are fragile.** Persisting the database with the cache or as an artifact races when two workflow runs overlap, and loses data on a cache miss.
- **Timing.** Workflow cron is best-effort: runs are delayed, sometimes skipped, and scheduled workflows in inactive repositories are disabled. Approvals need a long-running service anyway.

GitHub Actions is fine for what it is good at here: running `make test` and `backoffice validate` on pull requests. (The docstring in `schedule.py` mentions GitHub Actions as a possible host for `tick`; it is only workable if the runner has a persistent `.backoffice/`, for example a self-hosted runner, and at that point you have a VM.)
