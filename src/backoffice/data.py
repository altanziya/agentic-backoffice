"""Data adapters behind the MCP tools.

The shipped adapters read the demo company's files (`company/data/`): a SQLite CRM seeded
from CSV, daily metrics as CSV, and an inbound inbox as JSON. To connect real systems,
implement the same small interfaces (HubSpot/Pipedrive for `CRM`, GA4/Search Console/Stripe
for `Metrics`) or attach an existing MCP server in `.mcp.json`, opt agents in via
`backoffice.mcp_servers`, and map its tools in `capabilities` - the agents only see tool
names, not vendors.
"""

from __future__ import annotations

import csv
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import yaml

CRM_SCHEMA = """
CREATE TABLE IF NOT EXISTS contacts (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, email TEXT, company TEXT, role TEXT,
    stage TEXT, owner TEXT, last_touch TEXT, notes TEXT
);
CREATE TABLE IF NOT EXISTS deals (
    id TEXT PRIMARY KEY, contact_id TEXT, title TEXT, stage TEXT, value_eur REAL,
    next_step TEXT, next_step_due TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS activities (
    id INTEGER PRIMARY KEY AUTOINCREMENT, contact_id TEXT, ts TEXT, kind TEXT, summary TEXT
);
"""

# Fields the crm.update action may change. Anything else is rejected by the handler.
CRM_WRITABLE = {
    "contacts": {"stage", "owner", "last_touch", "notes", "role", "email"},
    "deals": {"stage", "value_eur", "next_step", "next_step_due", "updated_at"},
}


class CRM:
    def __init__(self, db_path: Path, seed_dir: Path | None = None):
        self.db_path = db_path
        self.seed_dir = seed_dir
        if not db_path.exists() and seed_dir and seed_dir.is_dir():
            self.seed_from_csv(seed_dir)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def seed_from_csv(self, seed_dir: Path) -> None:
        with self._conn() as c:
            c.executescript(CRM_SCHEMA)
            for table in ("contacts", "deals", "activities"):
                path = seed_dir / f"{table}.csv"
                if not path.exists():
                    continue
                with path.open(newline="", encoding="utf-8") as fh:
                    rows = list(csv.DictReader(fh))
                if not rows:
                    continue
                cols = list(rows[0])
                c.executemany(
                    f"INSERT OR REPLACE INTO {table}({', '.join(cols)}) "
                    f"VALUES ({', '.join('?' for _ in cols)})",
                    [tuple(r[k] or None for k in cols) for r in rows],
                )

    def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        like = f"%{query.lower()}%"
        with self._conn() as c:
            return [
                dict(r)
                for r in c.execute(
                    "SELECT id, name, company, role, stage, owner, last_touch FROM contacts "
                    "WHERE lower(name) LIKE ? OR lower(company) LIKE ? OR lower(email) LIKE ? "
                    "ORDER BY last_touch DESC LIMIT ?",
                    (like, like, like, limit),
                )
            ]

    def contact(self, contact_id: str) -> dict[str, Any] | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM contacts WHERE id=?", (contact_id,)).fetchone()
            if not row:
                return None
            out = dict(row)
            out["deals"] = [
                dict(r) for r in c.execute("SELECT * FROM deals WHERE contact_id=?", (contact_id,))
            ]
            out["activities"] = [
                dict(r)
                for r in c.execute(
                    "SELECT ts, kind, summary FROM activities WHERE contact_id=? ORDER BY ts DESC LIMIT 10",
                    (contact_id,),
                )
            ]
        return out

    def pipeline(self, today: date | None = None) -> dict[str, Any]:
        with self._conn() as c:
            stages = [
                dict(r)
                for r in c.execute(
                    "SELECT stage, COUNT(*) AS deals, COALESCE(SUM(value_eur),0) AS value_eur "
                    "FROM deals GROUP BY stage ORDER BY value_eur DESC"
                )
            ]
            overdue = [
                dict(r)
                for r in c.execute(
                    "SELECT d.id, d.title, d.stage, d.next_step, d.next_step_due, c.name AS contact "
                    "FROM deals d LEFT JOIN contacts c ON c.id = d.contact_id "
                    "WHERE d.next_step_due IS NOT NULL AND d.next_step_due < ? "
                    "AND d.stage NOT IN ('won','lost') ORDER BY d.next_step_due",
                    ((today or date.today()).isoformat(),),
                )
            ]
        return {"by_stage": stages, "overdue_next_steps": overdue}

    def update(self, table: str, record_id: str, fields: dict[str, Any]) -> dict[str, Any]:
        if table not in CRM_WRITABLE:
            raise ValueError(f"table {table!r} is not writable; allowed: {sorted(CRM_WRITABLE)}")
        bad = set(fields) - CRM_WRITABLE[table]
        if bad:
            raise ValueError(f"fields {sorted(bad)} are not writable on {table}")
        if not fields:
            raise ValueError("no fields to update")
        with self._conn() as c:
            before = c.execute(f"SELECT * FROM {table} WHERE id=?", (record_id,)).fetchone()
            if before is None:
                raise KeyError(f"{table} record {record_id!r} not found")
            sets = ", ".join(f"{k}=?" for k in fields)
            c.execute(f"UPDATE {table} SET {sets} WHERE id=?", (*fields.values(), record_id))
        return {
            "table": table,
            "id": record_id,
            "before": {k: dict(before)[k] for k in fields},
            "after": fields,
        }

    def log_activity(self, contact_id: str, ts: str, kind: str, summary: str) -> None:
        with self._conn() as c:
            if c.execute("SELECT 1 FROM contacts WHERE id=?", (contact_id,)).fetchone() is None:
                raise KeyError(f"contact {contact_id!r} not found")
            c.execute(
                "INSERT INTO activities(contact_id, ts, kind, summary) VALUES (?,?,?,?)",
                (contact_id, ts, kind, summary),
            )


class Metrics:
    """Daily metrics as `company/data/metrics/<source>.csv` with a `date` column.

    Columns are aggregated over the window by `sum` unless `aggregations.yaml` in the same
    directory says otherwise: `last` for end-of-day snapshots (MRR, active accounts) and
    `mean` for rates (bounce rate, average position). Summing a snapshot is the classic
    way a reporting agent produces a confident, wrong number.
    """

    def __init__(self, metrics_dir: Path):
        self.dir = metrics_dir
        agg_file = metrics_dir / "aggregations.yaml"
        self.aggregations: dict[str, dict[str, str]] = (
            yaml.safe_load(agg_file.read_text(encoding="utf-8")) or {} if agg_file.exists() else {}
        )

    @staticmethod
    def _aggregate(values: list[float], how: str) -> float | None:
        if not values:
            return None
        if how == "last":
            return values[-1]
        if how == "mean":
            return sum(values) / len(values)
        return sum(values)

    def sources(self) -> dict[str, list[str]]:
        out = {}
        for path in sorted(self.dir.glob("*.csv")):
            with path.open(newline="", encoding="utf-8") as fh:
                header = next(csv.reader(fh), [])
            out[path.stem] = [h for h in header if h != "date"]
        return out

    def query(self, source: str, days: int = 28, end: date | None = None) -> dict[str, Any]:
        path = self.dir / f"{source}.csv"
        if not path.exists():
            raise KeyError(f"unknown metrics source {source!r}; available: {sorted(self.sources())}")
        with path.open(newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        if not rows:
            return {"source": source, "rows": [], "summary": {}}
        last = end or max(date.fromisoformat(r["date"]) for r in rows)
        start = last - timedelta(days=days - 1)
        prev_start = start - timedelta(days=days)
        cur = [r for r in rows if start <= date.fromisoformat(r["date"]) <= last]
        prev = [r for r in rows if prev_start <= date.fromisoformat(r["date"]) < start]
        summary = {}
        how_by_col = self.aggregations.get(source, {})
        for col in rows[0]:
            if col == "date":
                continue
            how = how_by_col.get(col, "sum")
            try:
                a = self._aggregate([float(r[col]) for r in cur], how)
                b = self._aggregate([float(r[col]) for r in prev], how)
            except (TypeError, ValueError):
                continue  # non-numeric column
            change = None if not b or a is None else round((a - b) / b * 100, 1)
            summary[col] = {
                "aggregation": how,
                "current": None if a is None else round(a, 3),
                "previous": None if b is None else round(b, 3),
                "change_pct": change,
            }
        return {
            "source": source,
            "window": {"start": start.isoformat(), "end": last.isoformat(), "days": days},
            "summary": summary,
            "daily": cur[-14:],  # keep tool output small; totals above cover the full window
        }


class Inbound:
    """Inbound messages (contact forms, emails) as JSON files. Always untrusted content."""

    def __init__(self, inbound_dir: Path):
        self.dir = inbound_dir

    def list(self, since_days: int = 7, today: date | None = None) -> list[dict[str, Any]]:
        cutoff = (today or date.today()) - timedelta(days=since_days)
        items = []
        for path in sorted(self.dir.glob("*.json")):
            item = json.loads(path.read_text(encoding="utf-8"))
            if date.fromisoformat(item["received"][:10]) >= cutoff:
                items.append(item)
        return items
