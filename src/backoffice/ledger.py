"""The ledger: one SQLite file that is the system's memory of what happened.

* `runs`    - every job run: status, cost, turns, session id, degraded sources.
* `actions` - the outbox: side effects agents proposed, their approval state and result.
* `events`  - append-only audit trail (tool calls, denials, approvals, executions),
              hash-chained so silent edits are detectable (`backoffice audit verify`).

Agents cannot write this file: the policy guard denies every path under the state dir.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id           TEXT PRIMARY KEY,
    job          TEXT NOT NULL,
    agent        TEXT NOT NULL,
    trigger      TEXT NOT NULL DEFAULT 'manual',
    started_at   TEXT NOT NULL,
    finished_at  TEXT,
    status       TEXT NOT NULL,
    subtype      TEXT,
    session_id   TEXT,
    model        TEXT,
    cost_usd     REAL NOT NULL DEFAULT 0,
    num_turns    INTEGER,
    duration_ms  INTEGER,
    attempts     INTEGER NOT NULL DEFAULT 0,
    degraded     TEXT,
    result       TEXT,
    error        TEXT
);
CREATE INDEX IF NOT EXISTS runs_job_started ON runs(job, started_at);

CREATE TABLE IF NOT EXISTS actions (
    id            TEXT PRIMARY KEY,
    run_id        TEXT,
    job           TEXT,
    agent         TEXT,
    kind          TEXT NOT NULL,
    tier          TEXT NOT NULL,
    title         TEXT NOT NULL,
    payload       TEXT NOT NULL,
    justification TEXT NOT NULL,
    idem_key      TEXT NOT NULL UNIQUE,
    status        TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    expires_at    TEXT,
    decided_at    TEXT,
    decided_by    TEXT,
    decision_note TEXT,
    notified_at   TEXT,
    executed_at   TEXT,
    result        TEXT
);
CREATE INDEX IF NOT EXISTS actions_status ON actions(status);

CREATE TABLE IF NOT EXISTS events (
    seq       INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        TEXT NOT NULL,
    run_id    TEXT,
    agent     TEXT,
    kind      TEXT NOT NULL,
    tool      TEXT,
    detail    TEXT NOT NULL,
    prev_hash TEXT NOT NULL,
    hash      TEXT NOT NULL
);
"""

GENESIS = "0" * 64

# Action lifecycle. Only these transitions are legal; everything else is a bug.
TRANSITIONS: dict[str, set[str]] = {
    "pending": {"approved", "rejected", "expired"},
    "approved": {"executing"},
    "executing": {"executed", "failed"},
    "failed": {"approved"},  # explicit retry by an operator (`backoffice retry`)
}


def now() -> datetime:
    return datetime.now(UTC)


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat(timespec="seconds")


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def new_run_id() -> str:
    return f"R-{now():%Y%m%d}-{uuid.uuid4().hex[:6]}"


def new_action_id() -> str:
    return f"A-{uuid.uuid4().hex[:8]}"


@dataclass
class Action:
    id: str
    run_id: str | None
    job: str | None
    agent: str | None
    kind: str
    tier: str
    title: str
    payload: dict[str, Any]
    justification: str
    idem_key: str
    status: str
    created_at: str
    expires_at: str | None
    decided_at: str | None
    decided_by: str | None
    decision_note: str | None
    notified_at: str | None
    executed_at: str | None
    result: dict[str, Any] | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Action:
        d = dict(row)
        d["payload"] = json.loads(d["payload"])
        d["result"] = json.loads(d["result"]) if d["result"] else None
        return cls(**d)


class IllegalTransition(RuntimeError):
    pass


class Ledger:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        try:
            yield conn
        finally:
            conn.close()

    # --- runs -----------------------------------------------------------------------------
    def start_run(self, run_id: str, job: str, agent: str, trigger: str = "manual") -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO runs(id, job, agent, trigger, started_at, status) VALUES (?,?,?,?,?, 'running')",
                (run_id, job, agent, trigger, iso(now())),
            )
        self.audit(run_id, agent, "run_started", None, {"job": job, "trigger": trigger})

    def finish_run(self, run_id: str, *, status: str, **fields: Any) -> None:
        allowed = {
            "subtype",
            "session_id",
            "model",
            "cost_usd",
            "num_turns",
            "duration_ms",
            "attempts",
            "degraded",
            "result",
            "error",
        }
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"unknown run fields: {unknown}")
        values = {k: (canonical(v) if isinstance(v, (dict, list)) else v) for k, v in fields.items()}
        cols = ", ".join(f"{k}=?" for k in values)
        with self._conn() as c:
            c.execute(
                f"UPDATE runs SET status=?, finished_at=?{', ' + cols if cols else ''} WHERE id=?",
                (status, iso(now()), *values.values(), run_id),
            )
        self.audit(run_id, None, "run_finished", None, {"status": status, **fields})

    def record_skipped(self, job: str, agent: str, status: str, reason: str, trigger: str = "manual") -> str:
        run_id = new_run_id()
        with self._conn() as c:
            c.execute(
                "INSERT INTO runs(id, job, agent, trigger, started_at, finished_at, status, error)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (run_id, job, agent, trigger, iso(now()), iso(now()), status, reason),
            )
        self.audit(run_id, agent, "run_skipped", None, {"job": job, "status": status, "reason": reason})
        return run_id

    def runs(self, limit: int = 20, job: str | None = None) -> list[dict[str, Any]]:
        q = "SELECT * FROM runs"
        args: tuple[Any, ...] = ()
        if job:
            q += " WHERE job=?"
            args = (job,)
        q += " ORDER BY started_at DESC LIMIT ?"
        with self._conn() as c:
            return [dict(r) for r in c.execute(q, (*args, limit))]

    def last_started(self, job: str, trigger: str | None = None) -> datetime | None:
        q = "SELECT MAX(started_at) FROM runs WHERE job=?"
        args: list[Any] = [job]
        if trigger:
            q += " AND trigger=?"
            args.append(trigger)
        with self._conn() as c:
            value = c.execute(q, args).fetchone()[0]
        return datetime.fromisoformat(value) if value else None

    def spend_since(self, since: datetime, job: str | None = None) -> float:
        q = "SELECT COALESCE(SUM(cost_usd), 0) FROM runs WHERE started_at >= ?"
        args: list[Any] = [iso(since)]
        if job:
            q += " AND job = ?"
            args.append(job)
        with self._conn() as c:
            return float(c.execute(q, args).fetchone()[0])

    # --- actions (outbox) -----------------------------------------------------------------
    def propose(
        self,
        *,
        kind: str,
        tier: str,
        title: str,
        payload: dict[str, Any],
        justification: str,
        idem_key: str,
        run_id: str | None,
        job: str | None,
        agent: str | None,
        status: str,
        expires_in: timedelta | None,
    ) -> tuple[Action, bool]:
        """Insert an action unless one with the same idempotency key exists.

        Returns (action, created). A duplicate proposal returns the existing row unchanged,
        so a retried run can never queue the same side effect twice.
        """
        created_at = now()
        with self._conn() as c:
            cur = c.execute(
                "INSERT OR IGNORE INTO actions(id, run_id, job, agent, kind, tier, title, payload,"
                " justification, idem_key, status, created_at, expires_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    new_action_id(),
                    run_id,
                    job,
                    agent,
                    kind,
                    tier,
                    title,
                    canonical(payload),
                    justification,
                    idem_key,
                    status,
                    iso(created_at),
                    iso(created_at + expires_in) if expires_in else None,
                ),
            )
            created = cur.rowcount == 1
            row = c.execute("SELECT * FROM actions WHERE idem_key=?", (idem_key,)).fetchone()
        action = Action.from_row(row)
        if created:
            self.audit(
                run_id,
                agent,
                "action_proposed",
                None,
                {"action": action.id, "kind": kind, "tier": tier, "status": status},
            )
        return action, created

    def action(self, action_id: str) -> Action | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM actions WHERE id=?", (action_id,)).fetchone()
        return Action.from_row(row) if row else None

    def actions(self, status: str | None = None, limit: int = 50) -> list[Action]:
        q = "SELECT * FROM actions"
        args: tuple[Any, ...] = ()
        if status:
            q += " WHERE status=?"
            args = (status,)
        q += " ORDER BY created_at DESC LIMIT ?"
        with self._conn() as c:
            return [Action.from_row(r) for r in c.execute(q, (*args, limit))]

    def transition(
        self,
        action_id: str,
        to: str,
        *,
        by: str | None = None,
        note: str | None = None,
        result: dict[str, Any] | None = None,
    ) -> Action:
        """Compare-and-set state change. Safe against two approvers or two executors racing."""
        with self._conn() as c:
            row = c.execute("SELECT status FROM actions WHERE id=?", (action_id,)).fetchone()
            if row is None:
                raise KeyError(f"unknown action {action_id}")
            current = row["status"]
            if to not in TRANSITIONS.get(current, set()):
                raise IllegalTransition(f"{action_id}: {current} -> {to} is not allowed")
            sets = ["status=?"]
            args: list[Any] = [to]
            if to in {"approved", "rejected", "expired"}:
                sets += ["decided_at=?", "decided_by=?", "decision_note=?"]
                args += [iso(now()), by, note]
            if to in {"executed", "failed"}:
                sets += ["executed_at=?", "result=?"]
                args += [iso(now()), canonical(result or {})]
            cur = c.execute(
                f"UPDATE actions SET {', '.join(sets)} WHERE id=? AND status=?",
                (*args, action_id, current),
            )
            if cur.rowcount != 1:
                raise IllegalTransition(f"{action_id}: lost a race moving {current} -> {to}")
        self.audit(
            None, None, f"action_{to}", None, {"action": action_id, "by": by, "note": note, "result": result}
        )
        action = self.action(action_id)
        assert action is not None
        return action

    def mark_notified(self, action_id: str) -> None:
        with self._conn() as c:
            c.execute("UPDATE actions SET notified_at=? WHERE id=?", (iso(now()), action_id))

    def expire_overdue(self) -> list[str]:
        """Fail closed: pending actions past their deadline become `expired`, never `approved`."""
        with self._conn() as c:
            ids = [
                r["id"]
                for r in c.execute(
                    "SELECT id FROM actions WHERE status='pending' AND expires_at IS NOT NULL"
                    " AND expires_at < ?",
                    (iso(now()),),
                )
            ]
        expired = []
        for action_id in ids:
            try:
                self.transition(action_id, "expired", by="system", note="approval window elapsed")
                expired.append(action_id)
            except IllegalTransition:
                pass  # decided concurrently
        return expired

    # --- audit trail ----------------------------------------------------------------------
    def audit(self, run_id: str | None, agent: str | None, kind: str, tool: str | None, detail: Any) -> None:
        ts = iso(now())
        body = canonical(detail)
        with self._conn() as c:
            c.execute("BEGIN IMMEDIATE")
            try:
                last = c.execute("SELECT hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
                prev = last["hash"] if last else GENESIS
                digest = _event_hash(prev, ts, run_id, agent, kind, tool, body)
                c.execute(
                    "INSERT INTO events(ts, run_id, agent, kind, tool, detail, prev_hash, hash)"
                    " VALUES (?,?,?,?,?,?,?,?)",
                    (ts, run_id, agent, kind, tool, body, prev, digest),
                )
                c.execute("COMMIT")
            except Exception:
                c.execute("ROLLBACK")
                raise

    def events(self, run_id: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        q = "SELECT * FROM events"
        args: tuple[Any, ...] = ()
        if run_id:
            q += " WHERE run_id=?"
            args = (run_id,)
        q += " ORDER BY seq DESC LIMIT ?"
        with self._conn() as c:
            rows = [dict(r) for r in c.execute(q, (*args, limit))]
        for r in rows:
            r["detail"] = json.loads(r["detail"])
        return rows

    def verify_audit(self) -> tuple[bool, int, str]:
        """Recompute the hash chain. Returns (ok, events_checked, message)."""
        prev = GENESIS
        n = 0
        with self._conn() as c:
            for r in c.execute("SELECT * FROM events ORDER BY seq"):
                n += 1
                if r["prev_hash"] != prev:
                    return False, n, f"event {r['seq']}: prev_hash does not match predecessor"
                expect = _event_hash(
                    prev, r["ts"], r["run_id"], r["agent"], r["kind"], r["tool"], r["detail"]
                )
                if r["hash"] != expect:
                    return False, n, f"event {r['seq']}: content was modified"
                prev = r["hash"]
        return True, n, "audit chain intact"


def _event_hash(prev: str, ts: str, run_id: Any, agent: Any, kind: str, tool: Any, body: str) -> str:
    material = canonical([prev, ts, run_id, agent, kind, tool, body])
    return hashlib.sha256(material.encode()).hexdigest()
