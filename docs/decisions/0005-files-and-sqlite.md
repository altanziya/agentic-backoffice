# 0005 - Files and one SQLite ledger

**Status:** accepted

**Context.** A small team needs to read, diff and back up what its agents know and did.

**Decision.** Business context is Markdown/YAML in `company/`; agent output and memory are files
in `workspace/`; runs, actions and the audit trail are one SQLite file in WAL mode. Agents search
with grep/glob. No vector database, no server process, no dashboard.

**Consequences.** `git diff` shows what changed in the company context; `sqlite3` answers any
operational question; backup is one file copy. Revisit when a corpus outgrows grep (thousands
of documents) or when several hosts must share one ledger (then Postgres, same schema).
