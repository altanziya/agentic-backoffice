from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from backoffice.schedule import Cron, due_jobs

TZ = ZoneInfo("Europe/Berlin")


def at(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=TZ)


def test_basic_fields_and_ranges():
    c = Cron("*/15 9-17 * * 1-5")
    assert c.matches(at("2026-10-05T09:45"))  # Monday
    assert not c.matches(at("2026-10-05T09:46"))
    assert not c.matches(at("2026-10-04T10:00"))  # Sunday


def test_sunday_as_7_and_lists():
    assert Cron("0 18 * * 7").matches(at("2026-10-04T18:00"))
    assert Cron("0 9 * * 2,4").matches(at("2026-10-08T09:00"))  # Thursday


def test_dom_dow_or_semantics():
    c = Cron("0 9 1,15 * 1")  # 1st, 15th, or any Monday
    assert c.matches(at("2026-10-01T09:00"))
    assert c.matches(at("2026-10-05T09:00"))
    assert not c.matches(at("2026-10-06T09:00"))


@pytest.mark.parametrize("expr", ["* * *", "61 * * * *", "0 25 * * *", "0 0 * * 8", "*/0 * * * *"])
def test_invalid_expressions(expr):
    with pytest.raises(ValueError):
        Cron(expr)


def test_last_before_and_next_after():
    c = Cron("30 7 * * 1-5")
    assert c.last_before(at("2026-10-05T08:00")) == at("2026-10-05T07:30")
    assert c.next_after(at("2026-10-05T08:00")) == at("2026-10-06T07:30")
    assert c.last_before(at("2026-10-05T07:29"), horizon=timedelta(hours=1)) is None


def test_due_jobs_runs_each_slot_once_with_catchup():
    schedules = {"briefing": "30 7 * * 1-5", "weekly": "0 7 * * 1"}
    now = at("2026-10-05T07:40")
    catchup = timedelta(minutes=90)
    due = due_jobs(schedules, {}, now, catchup)
    assert [j for j, _ in due] == ["weekly", "briefing"]
    done = {"briefing": at("2026-10-05T07:31"), "weekly": None}
    assert [j for j, _ in due_jobs(schedules, done, now, catchup)] == ["weekly"]
    # a slot missed by more than the catch-up window is not run late
    assert due_jobs(schedules, {}, at("2026-10-05T12:00"), catchup) == []
