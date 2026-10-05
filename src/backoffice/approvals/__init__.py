"""Human approval channels.

A channel only *asks*; the decision is a compare-and-set on the ledger, so two approvers,
a double-tap, or a retried webhook can never approve or execute an action twice.

Rules carried over from production:
* show the real payload, not the agent's summary of it (summaries can be steered)
* verify the approver *and* the chat, not one or the other
* no answer means no: pending actions expire closed
"""

from __future__ import annotations

import html
import json
from typing import Protocol

from ..config import BackofficeConfig
from ..ledger import Action, Ledger

PREVIEW_CHARS = 1500


def render_action(action: Action, *, markup: bool = False) -> str:
    esc = html.escape if markup else (lambda s: s)
    payload = json.dumps(action.payload, indent=1, ensure_ascii=False)
    if len(payload) > PREVIEW_CHARS:
        payload = payload[:PREVIEW_CHARS] + f"\n... ({len(payload) - PREVIEW_CHARS} more chars)"
    head = f"{action.id} · {action.kind} · {action.tier}"
    lines = [
        f"<b>{esc(head)}</b>" if markup else head,
        esc(action.title),
        "",
        f"Why: {esc(action.justification)}",
        f"Proposed by: {esc(action.agent or '?')} "
        f"(job {esc(action.job or '-')}, run {esc(action.run_id or '-')})",
        f"Expires: {esc(action.expires_at or 'never')}",
        "",
        f"<pre>{esc(payload)}</pre>" if markup else payload,
    ]
    return "\n".join(lines)


class ApprovalChannel(Protocol):
    def request(self, actions: list[Action]) -> None: ...


class CliChannel:
    """Prints requests; decide with `backoffice approve <id>` / `backoffice reject <id>`."""

    def request(self, actions: list[Action]) -> None:
        for a in actions:
            print("\n" + render_action(a))
            print(f"\n  -> backoffice approve {a.id}    |    backoffice reject {a.id} --note '...'")


def get_channel(cfg: BackofficeConfig, ledger: Ledger) -> ApprovalChannel:
    if cfg.approvals.channel == "telegram":
        from .telegram import TelegramChannel

        return TelegramChannel.from_config(cfg, ledger)
    return CliChannel()


def request_pending(cfg: BackofficeConfig, ledger: Ledger) -> int:
    """Expire overdue actions, then send every pending action that was not sent yet."""
    ledger.expire_overdue()
    fresh = [a for a in ledger.actions(status="pending", limit=200) if not a.notified_at]
    if fresh:
        get_channel(cfg, ledger).request(fresh)
        for a in fresh:
            ledger.mark_notified(a.id)
    return len(fresh)
