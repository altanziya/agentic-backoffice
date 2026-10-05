# Decision records

Short records of choices that shape the system, with the alternative that was rejected.

| # | Decision |
|---|---|
| [0001](0001-workflows-first.md) | Code decides when and which agent runs; agents judge inside a bounded job |
| [0002](0002-outbox-instead-of-tool-permissions.md) | Side effects go through an outbox, not through in-session permission prompts |
| [0003](0003-single-writer.md) | Parallel readers, one writer |
| [0004](0004-claude-code-files-as-registry.md) | `.claude/agents/*.md` is the agent registry for both interactive and headless use |
| [0005](0005-files-and-sqlite.md) | Files and one SQLite ledger; no vector DB, no server |
| [0006](0006-schedules-in-config.md) | Schedules live in `backoffice.yaml`; the host only calls `tick` |
| [0007](0007-structured-run-report.md) | Every headless run ends in a schema-validated report |
