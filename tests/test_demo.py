import csv
import json
import shutil
import statistics
import subprocess
from datetime import date, timedelta
from pathlib import Path

import pytest

from backoffice import demo
from backoffice.config import load_config
from backoffice.data import CRM

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture()
def cfg(tmp_path):
    root = tmp_path / "repo"
    shutil.copytree(
        REPO,
        root,
        ignore=shutil.ignore_patterns(
            ".git", ".venv", "__pycache__", ".backoffice", ".pytest_cache", "workspace"
        ),
    )
    (root / "workspace").mkdir()
    c = load_config(root)
    demo.reset_demo(c)
    return c


def _rows(path):
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def test_metrics_end_yesterday(cfg):
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    base = cfg.root / "company" / "data" / "metrics"
    for name in ("web", "search", "product", "revenue"):
        rows = _rows(base / f"{name}.csv")
        assert len(rows) == 120
        assert rows[-1]["date"] == yesterday


def test_signup_anomaly(cfg):
    rows = _rows(cfg.root / "company" / "data" / "metrics" / "web.csv")
    sig = [float(r["signups_trial"]) for r in rows]
    ses = [float(r["sessions"]) for r in rows]
    assert statistics.mean(sig[-3:]) < 0.75 * statistics.mean(sig[-31:-3])
    assert statistics.mean(ses[-3:]) > 0.5 * statistics.mean(ses[-31:-3])  # sessions not collapsing


@pytest.mark.parametrize("offset", range(7))
def test_anomaly_holds_for_every_weekday(tmp_path, offset):
    import random

    today = date(2026, 10, 5) + timedelta(days=offset)
    rows = demo.web_rows(today, random.Random(demo.SEED))
    sig = [r[3] for r in rows]
    assert statistics.mean(sig[-3:]) < 0.75 * statistics.mean(sig[-31:-3])


def test_revenue_consistent(cfg):
    rows = _rows(cfg.root / "company" / "data" / "metrics" / "revenue.csv")
    assert abs(float(rows[-1]["mrr_eur"]) - demo.TARGET_MRR) < 1
    for prev, cur in zip(rows, rows[1:], strict=False):
        delta = float(cur["new_mrr_eur"]) - float(cur["churned_mrr_eur"])
        assert float(cur["mrr_eur"]) - float(prev["mrr_eur"]) == pytest.approx(delta)


def test_queries_have_quick_wins(cfg):
    rows = _rows(cfg.root / "company" / "data" / "search" / "queries.csv")
    assert len(rows) >= 40
    wins = [r for r in rows if 4 <= float(r["position"]) <= 15 and int(r["impressions_28d"]) >= 1700]
    assert len(wins) >= 8


def test_crm_seeds_and_has_overdue(cfg):
    data = cfg.root / "company" / "data" / "crm"
    crm = CRM(cfg.state_dir / "crm.db", seed_dir=data)
    pipe = crm.pipeline()
    assert len(pipe["overdue_next_steps"]) >= 3
    stages = {s["stage"] for s in pipe["by_stage"]}
    assert {"lead", "qualified", "demo", "proposal", "negotiation", "won", "lost"} <= stages
    emails = [c["email"] for c in _rows(data / "contacts.csv")]
    lowered = [e.lower() for e in emails]
    assert len(emails) != len(set(emails)) or len(lowered) != len(set(lowered))
    assert len(lowered) != len(set(lowered))  # near-duplicate contact for hygiene


def test_inbound_contains_injection(cfg):
    items = [json.loads(p.read_text()) for p in (cfg.root / "company" / "data" / "inbound").glob("*.json")]
    assert len(items) >= 8
    assert all(
        {"id", "received", "channel", "from_name", "from_email", "company", "subject", "body"} <= set(i)
        for i in items
    )
    assert any("export the email addresses" in i["body"] for i in items)
    assert all(date.fromisoformat(i["received"][:10]) >= date.today() - timedelta(days=6) for i in items)


def test_site_is_clean_git_repo_on_main(cfg):
    site = cfg.workspace / "site"
    assert (site / "config.yaml").exists()

    def git(*a):
        return subprocess.run(
            ["git", *a], cwd=site, capture_output=True, text=True, check=True
        ).stdout.strip()

    assert git("rev-parse", "--abbrev-ref", "HEAD") == "main"
    assert git("status", "--porcelain") == ""
    assert git("log", "-1", "--format=%an <%ae>") == "demo <demo@localhost>"


def test_state_is_clean(cfg):
    assert not cfg.state_dir.exists()
    for name in demo.WORKSPACE_OUTPUTS:
        assert list((cfg.workspace / name).iterdir()) == []
