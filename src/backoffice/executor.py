"""Executor: performs approved actions exactly once.

Runs after each job (for T1 actions) and after approvals (for T2). It is a separate step on
purpose: no agent session is alive while side effects happen, and every effect is a ledger
row with who approved it, when, and what came back.
"""

from __future__ import annotations

from dataclasses import dataclass

from .actions import HANDLERS, ActionError
from .config import BackofficeConfig
from .ledger import IllegalTransition, Ledger


@dataclass
class ExecutionReport:
    executed: list[str]
    failed: list[tuple[str, str]]


def execute_approved(cfg: BackofficeConfig, ledger: Ledger) -> ExecutionReport:
    ledger.expire_overdue()
    report = ExecutionReport([], [])
    if cfg.kill_switch.exists():
        return report  # the kill switch stops effects too, not only new runs
    for action in reversed(ledger.actions(status="approved", limit=200)):  # oldest first
        try:
            ledger.transition(action.id, "executing", by="executor")
        except IllegalTransition:
            continue  # another executor claimed it
        action_cfg = cfg.actions.get(action.kind)
        try:
            if action_cfg is None:
                raise ActionError(f"action kind {action.kind!r} was removed from the config")
            fn = HANDLERS.get(action_cfg.handler)
            if fn is None:
                raise ActionError(f"no handler named {action_cfg.handler!r}")
            result = fn(cfg, action_cfg.params, action.payload)
        except Exception as e:  # noqa: BLE001 - every failure must land in the ledger
            ledger.transition(
                action.id, "failed", by="executor", result={"error": f"{type(e).__name__}: {e}"}
            )
            report.failed.append((action.id, str(e)))
            continue
        ledger.transition(action.id, "executed", by="executor", result=result)
        report.executed.append(action.id)
    return report
