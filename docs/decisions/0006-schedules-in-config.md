# 0006 - Schedules live in config; the host only calls `tick`

**Status:** accepted

**Context.** Cron on the host knows nothing about the company's timezone, budgets or previous
runs, and a second copy of every schedule drifts from the registry.

**Decision.** Jobs declare a cron expression in `backoffice.yaml`, interpreted in the company
timezone. The host runs `backoffice tick` every few minutes (systemd timer or cron).
`tick` runs each job whose latest slot has no scheduled run yet, within a catch-up window.

**Consequences.** One source of truth, DST-correct, missed slots after a reboot run once,
`doctor` reports slots that were missed entirely. GitHub Actions cron is not used as the
scheduler: its runners are ephemeral, so the ledger (idempotency, budgets, audit) would not
persist between ticks.
