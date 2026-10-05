"""Scheduling: `backoffice.yaml` is the only place schedules live.

The host scheduler (a systemd timer or cron on a machine that keeps the ledger) just calls
`backoffice tick`
every few minutes. `tick` works out which jobs are due in the company's timezone and runs
them once. This removes a class of production drift: the old system kept schedules in a
registry *and* in a crontab, and the two quietly disagreed.

Catch-up: a run missed by up to `catchup` (e.g. the VM was rebooting) still happens once;
older misses are skipped and show up in `backoffice doctor`.
"""

from __future__ import annotations

from datetime import datetime, timedelta

_RANGES = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 6)]  # min hour dom month dow(0=Sun)


def _parse_field(expr: str, lo: int, hi: int) -> set[int]:
    values: set[int] = set()
    for part in expr.split(","):
        step = 1
        if "/" in part:
            part, step_s = part.split("/", 1)
            step = int(step_s)
            if step < 1:
                raise ValueError(f"bad step in {expr!r}")
        if part == "*":
            start, end = lo, hi
        elif "-" in part:
            a, b = part.split("-", 1)
            start, end = int(a), int(b)
        else:
            start = int(part)
            end = (hi + 1 if hi == 6 else hi) if step > 1 else start
        top = hi + 1 if hi == 6 else hi  # day-of-week accepts 7 as Sunday
        if not (lo <= start <= top and lo <= end <= top and start <= end):
            raise ValueError(f"value out of range in {expr!r}")
        values.update(range(start, end + 1, step))
    if hi == 6 and 7 in values:  # cron allows 7 for Sunday
        values.discard(7)
        values.add(0)
    return values


class Cron:
    """Minimal 5-field cron matcher (*, n, a-b, a,b, */n, a-b/n). Vixie semantics for
    day-of-month vs day-of-week: if both are restricted, either may match."""

    def __init__(self, expr: str):
        fields = expr.split()
        if len(fields) != 5:
            raise ValueError(f"cron needs 5 fields: {expr!r}")
        self.expr = expr
        self.minute, self.hour, self.dom, self.month, self.dow = (
            _parse_field(f, lo, hi) for f, (lo, hi) in zip(fields, _RANGES, strict=True)
        )
        self._dom_any = fields[2] == "*"
        self._dow_any = fields[4] == "*"

    def matches(self, t: datetime) -> bool:
        if t.minute not in self.minute or t.hour not in self.hour or t.month not in self.month:
            return False
        dom_ok = t.day in self.dom
        dow_ok = (t.isoweekday() % 7) in self.dow
        if self._dom_any or self._dow_any:
            return dom_ok and dow_ok
        return dom_ok or dow_ok

    def last_before(self, t: datetime, horizon: timedelta = timedelta(days=32)) -> datetime | None:
        """Most recent matching minute <= t, searching back at most `horizon`."""
        cur = t.replace(second=0, microsecond=0)
        stop = cur - horizon
        while cur >= stop:
            if self.matches(cur):
                return cur
            cur -= timedelta(minutes=1)
        return None

    def next_after(self, t: datetime, horizon: timedelta = timedelta(days=32)) -> datetime | None:
        cur = t.replace(second=0, microsecond=0) + timedelta(minutes=1)
        stop = cur + horizon
        while cur <= stop:
            if self.matches(cur):
                return cur
            cur += timedelta(minutes=1)
        return None


def due_jobs(
    schedules: dict[str, str],
    last_scheduled_run: dict[str, datetime | None],
    now: datetime,
    catchup: timedelta,
) -> list[tuple[str, datetime]]:
    """Jobs whose latest scheduled slot is within `catchup` and has no scheduled run yet."""
    due = []
    for job, expr in schedules.items():
        slot = Cron(expr).last_before(now, horizon=catchup)
        if slot is None:
            continue
        last = last_scheduled_run.get(job)
        if last is None or last < slot:
            due.append((job, slot))
    return sorted(due, key=lambda x: x[1])
