from __future__ import annotations

import sqlite3
from datetime import timedelta

import pytest

from backoffice.ledger import IllegalTransition, now
from backoffice.outbox import ProposalError, RunContext, describe_for_agent, propose

CTX = RunContext(run_id="R-1", job="kpi", agent="analyst", logical_date="2026-10-05")


def _propose(cfg, ledger, kind="crm.update", payload=None, **kw):
    return propose(
        cfg,
        ledger,
        CTX,
        kind=kind,
        title="t",
        justification="j",
        payload=payload if payload is not None else {"table": "deals", "id": "D1"},
        **kw,
    )


def test_tier_decides_initial_state(cfg, ledger):
    t1, _ = _propose(cfg, ledger, "report.publish", {"path": "a.md", "content": "x"})
    t2, _ = _propose(cfg, ledger, "crm.update")
    t3, _ = _propose(cfg, ledger, "payment.send", {"eur": 100})
    assert (t1.status, t2.status, t3.status) == ("approved", "pending", "refused")
    assert t2.expires_at is not None and t1.expires_at is None
    assert "NOT happened" in describe_for_agent(t2, True)
    assert "never automated" in describe_for_agent(t3, True)


def test_refused_actions_can_never_be_approved(cfg, ledger):
    t3, _ = _propose(cfg, ledger, "payment.send", {"eur": 100})
    with pytest.raises(IllegalTransition):
        ledger.transition(t3.id, "approved", by="cli")


def test_same_proposal_is_queued_once(cfg, ledger):
    a, created_a = _propose(cfg, ledger)
    b, created_b = _propose(cfg, ledger)
    assert created_a and not created_b and a.id == b.id
    assert "Already proposed" in describe_for_agent(b, created_b)
    c, created_c = _propose(cfg, ledger, payload={"table": "deals", "id": "D2"})
    assert created_c and c.id != a.id


def test_unknown_kind_and_missing_justification(cfg, ledger):
    with pytest.raises(ProposalError, match="unknown action kind"):
        _propose(cfg, ledger, "email.blast")
    with pytest.raises(ProposalError, match="justification"):
        propose(cfg, ledger, CTX, kind="crm.update", title="t", justification=" ", payload={})


def test_transitions_are_compare_and_set(cfg, ledger):
    a, _ = _propose(cfg, ledger)
    ledger.transition(a.id, "approved", by="alice")
    with pytest.raises(IllegalTransition):  # second approver loses
        ledger.transition(a.id, "approved", by="bob")
    with pytest.raises(IllegalTransition):  # cannot jump to executed
        ledger.transition(a.id, "executed")
    ledger.transition(a.id, "executing")
    done = ledger.transition(a.id, "executed", result={"ok": True})
    assert done.decided_by == "alice" and done.result == {"ok": True}


def test_pending_actions_expire_closed(cfg, ledger):
    a, _ = _propose(cfg, ledger)
    with sqlite3.connect(cfg.ledger_path) as c:
        c.execute(
            "UPDATE actions SET expires_at=? WHERE id=?", ((now() - timedelta(minutes=1)).isoformat(), a.id)
        )
    assert ledger.expire_overdue() == [a.id]
    assert ledger.action(a.id).status == "expired"
    with pytest.raises(IllegalTransition):
        ledger.transition(a.id, "approved")


def test_audit_chain_detects_tampering(cfg, ledger):
    ledger.start_run("R-1", "kpi", "analyst")
    _propose(cfg, ledger)
    ledger.audit("R-1", "analyst", "tool_call", "Read", {"file_path": "x"})
    ok, n, _ = ledger.verify_audit()
    assert ok and n >= 3
    with sqlite3.connect(cfg.ledger_path) as c:
        c.execute("UPDATE events SET detail='{\"file_path\":\"y\"}' WHERE kind='tool_call'")
    ok, _, msg = ledger.verify_audit()
    assert not ok and "modified" in msg


def test_spend_and_last_started(ledger):
    ledger.start_run("R-a", "kpi", "analyst", trigger="schedule")
    ledger.finish_run("R-a", status="success", cost_usd=0.42)
    ledger.record_skipped("kpi", "analyst", "budget_blocked", "cap", trigger="schedule")
    assert ledger.spend_since(now() - timedelta(hours=1)) == pytest.approx(0.42)
    assert ledger.spend_since(now() - timedelta(hours=1), job="other") == 0
    assert ledger.last_started("kpi", trigger="schedule") is not None
    assert ledger.last_started("kpi", trigger="manual") is None
    with pytest.raises(ValueError):
        ledger.finish_run("R-a", status="success", bogus=1)
