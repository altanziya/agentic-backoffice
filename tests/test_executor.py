from __future__ import annotations

import subprocess

import pytest

from backoffice.actions import ActionError, github_pull_request
from backoffice.executor import execute_approved
from backoffice.outbox import RunContext, propose

CTX = RunContext(run_id="R-1", job="kpi", agent="analyst", logical_date="2026-10-05")


def test_t1_action_executes_exactly_once(cfg, ledger):
    a, _ = propose(
        cfg,
        ledger,
        CTX,
        kind="report.publish",
        title="t",
        justification="j",
        payload={"path": "kpi/w40.md", "content": "# KPIs"},
    )
    first = execute_approved(cfg, ledger)
    second = execute_approved(cfg, ledger)
    assert first.executed == [a.id] and second.executed == []
    assert (cfg.root / "workspace/published/kpi/w40.md").read_text() == "# KPIs"
    assert ledger.action(a.id).status == "executed"


def test_pending_t2_is_not_executed_until_approved(cfg, ledger):
    a, _ = propose(
        cfg,
        ledger,
        CTX,
        kind="crm.update",
        title="t",
        justification="j",
        payload={"table": "deals", "id": "D1", "fields": {"stage": "won"}},
    )
    assert execute_approved(cfg, ledger).executed == []
    assert ledger.action(a.id).status == "pending"


def test_handler_failure_lands_in_ledger_and_can_be_retried(cfg, ledger):
    a, _ = propose(
        cfg,
        ledger,
        CTX,
        kind="report.publish",
        title="t",
        justification="j",
        payload={"path": "../../escape.md", "content": "x"},
    )
    rep = execute_approved(cfg, ledger)
    assert rep.failed and rep.failed[0][0] == a.id and "escapes" in rep.failed[0][1]
    assert ledger.action(a.id).status == "failed"
    ledger.transition(a.id, "approved", by="cli", note="retry")
    assert ledger.action(a.id).status == "approved"


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def site(cfg):
    repo = cfg.root / "workspace/site"
    repo.mkdir(parents=True)
    _git(repo, "init", "-q", "-b", "main")
    (repo / "index.md").write_text("old")
    _git(repo, "add", ".")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")
    return repo


def test_pull_request_handler_commits_on_branch_only(cfg, site):
    params = cfg.actions["site.pull_request"].params
    payload = {"branch": "agent/fix-index", "title": "Fix index", "files": {"index.md": "new"}}
    out = github_pull_request(cfg, params, payload)
    assert out["status"] == "committed"
    assert (site / "index.md").read_text() == "old"  # back on main, untouched
    show = subprocess.run(
        ["git", "-C", str(site), "show", "agent/fix-index:index.md"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert show.stdout == "new"
    assert github_pull_request(cfg, params, payload)["status"] == "exists"


def test_pull_request_handler_validates_payload(cfg, site):
    params = cfg.actions["site.pull_request"].params
    with pytest.raises(ActionError, match="branch must start with"):
        github_pull_request(cfg, params, {"branch": "main", "title": "x", "files": {}})
    with pytest.raises(ActionError, match="escapes"):
        github_pull_request(
            cfg, params, {"branch": "agent/x", "title": "x", "files": {"../../outside.md": "x"}}
        )
    with pytest.raises(ActionError, match=".git"):
        github_pull_request(
            cfg, params, {"branch": "agent/y", "title": "x", "files": {".git/hooks/pre-commit": "x"}}
        )
