"""The outbox: agents propose side effects, they never perform them.

`propose_action` is the only door from "the model decided something" to "something happened
outside". The tier of the action kind (from `backoffice.yaml`) - not the agent, not the
prompt - decides what happens next:

    T1  auto-approved, executed by the executor, audited
    T2  waits for a human (CLI or Telegram), expires closed after `expire_hours`
    T3  refused immediately; the agent is told to hand the matter to a human

Proposals carry an idempotency key, so a retried run cannot queue the same effect twice.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from .config import BackofficeConfig, Tier
from .ledger import Action, Ledger, canonical


@dataclass(frozen=True)
class RunContext:
    run_id: str | None
    job: str | None
    agent: str | None
    logical_date: str  # e.g. 2026-10-05 - part of the default idempotency key


class ProposalError(ValueError):
    pass


def default_idem_key(ctx: RunContext, kind: str, payload: dict[str, Any]) -> str:
    material = canonical([ctx.job or "interactive", ctx.logical_date, kind, payload])
    return hashlib.sha256(material.encode()).hexdigest()[:32]


def propose(
    cfg: BackofficeConfig,
    ledger: Ledger,
    ctx: RunContext,
    *,
    kind: str,
    title: str,
    payload: dict[str, Any],
    justification: str,
    idempotency_key: str | None = None,
) -> tuple[Action, bool]:
    action_cfg = cfg.actions.get(kind)
    if action_cfg is None:
        known = ", ".join(sorted(cfg.actions)) or "(none configured)"
        raise ProposalError(f"unknown action kind {kind!r}. Known kinds: {known}")
    if not title.strip() or not justification.strip():
        raise ProposalError("title and justification are required - say what and why")
    if not isinstance(payload, dict):
        raise ProposalError("payload must be a JSON object")

    if action_cfg.tier == Tier.T3:
        status = "refused"
    elif action_cfg.tier == Tier.T1:
        status = "approved"
    else:
        status = "pending"

    key = idempotency_key or default_idem_key(ctx, kind, payload)
    if status == "refused":
        # Recorded for the audit trail, never executable (no legal transition out of 'refused').
        return ledger.propose(
            kind=kind,
            tier=action_cfg.tier,
            title=title,
            payload=payload,
            justification=justification,
            idem_key=key,
            run_id=ctx.run_id,
            job=ctx.job,
            agent=ctx.agent,
            status=status,
            expires_in=None,
        )
    return ledger.propose(
        kind=kind,
        tier=action_cfg.tier,
        title=title,
        payload=payload,
        justification=justification,
        idem_key=key,
        run_id=ctx.run_id,
        job=ctx.job,
        agent=ctx.agent,
        status=status,
        expires_in=timedelta(hours=cfg.approvals.expire_hours) if status == "pending" else None,
    )


def describe_for_agent(action: Action, created: bool) -> str:
    """What the agent is told. Deliberately explicit that nothing has happened yet."""
    if not created:
        return f"Already proposed earlier as {action.id} (status: {action.status}). Not queued again."
    if action.status == "refused":
        return (
            f"{action.id} refused: '{action.kind}' is a T3 action (money, legal, credentials "
            "or deletion) and is never automated. Tell the human in your report instead."
        )
    if action.status == "approved":
        return (
            f"{action.id} queued (T1, auto-approved). It will be executed after this run; "
            "do not assume it already happened."
        )
    return (
        f"{action.id} queued for human approval (T2). It has NOT happened. "
        "Mention it in your report as 'awaiting approval'."
    )
