"""Telegram approval channel: inline Approve / Reject buttons, long-polling, fail closed.

`backoffice telegram` runs `serve()`. Callback handling is independent of any agent run, so
a long job never blocks approvals (production lesson: a single sequential loop let a
20-minute task freeze every approval button).
"""

from __future__ import annotations

import html
import logging
import os
import time
from dataclasses import dataclass
from typing import Any

import httpx

from ..config import BackofficeConfig
from ..ledger import Action, IllegalTransition, Ledger
from . import render_action

log = logging.getLogger(__name__)
API = "https://api.telegram.org/bot{token}/{method}"


@dataclass
class TelegramChannel:
    token: str
    chat_id: str
    approver_ids: frozenset[str]
    ledger: Ledger
    client: httpx.Client

    @classmethod
    def from_config(cls, cfg: BackofficeConfig, ledger: Ledger) -> TelegramChannel:
        t = cfg.approvals.telegram
        token = os.environ.get(t.bot_token_env, "")
        chat_id = os.environ.get(t.chat_id_env, "")
        approvers = frozenset(
            x.strip() for x in os.environ.get(t.approver_ids_env, "").split(",") if x.strip()
        )
        missing = [
            n
            for n, v in [(t.bot_token_env, token), (t.chat_id_env, chat_id), (t.approver_ids_env, approvers)]
            if not v
        ]
        if missing:
            raise RuntimeError(f"Telegram approvals need these env vars: {', '.join(missing)}")
        return cls(token, chat_id, approvers, ledger, httpx.Client(timeout=40))

    # --- Bot API ------------------------------------------------------------------------
    def _call(self, method: str, **params: Any) -> Any:
        for attempt in range(4):
            r = self.client.post(API.format(token=self.token, method=method), json=params)
            if r.status_code == 429:  # rate limited: honour retry_after
                wait = r.json().get("parameters", {}).get("retry_after", 2**attempt)
                time.sleep(float(wait))
                continue
            data = r.json()
            if not data.get("ok"):
                raise RuntimeError(f"telegram {method} failed: {data.get('description')}")
            return data["result"]
        raise RuntimeError(f"telegram {method}: still rate limited after retries")

    def send(self, text: str, buttons: list[list[dict[str, str]]] | None = None) -> None:
        params: dict[str, Any] = {
            "chat_id": self.chat_id,
            "text": text[:4096],
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if buttons:
            params["reply_markup"] = {"inline_keyboard": buttons}
        self._call("sendMessage", **params)

    # --- ApprovalChannel ----------------------------------------------------------------
    def request(self, actions: list[Action]) -> None:
        for a in actions:
            # callback_data carries only the opaque id; the payload is re-read from the ledger.
            self.send(
                render_action(a, markup=True),
                buttons=[
                    [
                        {"text": "Approve", "callback_data": f"approve:{a.id}"},
                        {"text": "Reject", "callback_data": f"reject:{a.id}"},
                    ]
                ],
            )

    # --- callback handling --------------------------------------------------------------
    def authorised(self, query: dict[str, Any]) -> bool:
        user = str(query.get("from", {}).get("id", ""))
        chat = str(query.get("message", {}).get("chat", {}).get("id", ""))
        return user in self.approver_ids and chat == self.chat_id

    def handle_callback(self, query: dict[str, Any]) -> str:
        if not self.authorised(query):
            log.warning("rejected callback from user %s", query.get("from", {}).get("id"))
            self.ledger.audit(
                None,
                None,
                "approval_unauthorised",
                None,
                {"from": query.get("from", {}).get("id"), "data": query.get("data")},
            )
            return "Not authorised."
        verb, _, action_id = str(query.get("data", "")).partition(":")
        if verb not in {"approve", "reject"} or not action_id.startswith("A-"):
            return "Unknown button."
        who = f"telegram:{query['from']['id']}"
        try:
            action = self.ledger.transition(
                action_id, "approved" if verb == "approve" else "rejected", by=who
            )
        except (IllegalTransition, KeyError) as e:
            return f"No change: {e}"
        msg = query.get("message", {})
        if msg.get("message_id"):
            label = "APPROVED" if action.status == "approved" else "REJECTED"
            self._call(
                "editMessageReplyMarkup",
                chat_id=self.chat_id,
                message_id=msg["message_id"],
                reply_markup={"inline_keyboard": []},
            )
            self.send(f"{html.escape(action.id)}: <b>{label}</b> by {html.escape(who)}")
        return f"{action.id} {action.status}"

    def serve(self, on_approved: Any = None, poll_seconds: int = 30) -> None:
        """Long-poll for button presses. `on_approved()` runs the executor after approvals."""
        offset = None
        log.info("telegram approval loop started")
        while True:
            self.ledger.expire_overdue()
            try:
                updates = self._call(
                    "getUpdates", timeout=poll_seconds, offset=offset, allowed_updates=["callback_query"]
                )
            except (httpx.HTTPError, RuntimeError) as e:
                log.warning("getUpdates failed: %s", e)
                time.sleep(5)
                continue
            approved_any = False
            for upd in updates:
                q = upd.get("callback_query")
                if q:
                    answer = self.handle_callback(q)
                    approved_any |= answer.endswith(" approved")
                    try:
                        self._call("answerCallbackQuery", callback_query_id=q["id"], text=answer[:190])
                    except RuntimeError as e:
                        log.warning("answerCallbackQuery failed: %s", e)
                # Advance only after handling: a crash re-delivers the update, and the ledger's
                # compare-and-set makes re-handling a no-op.
                offset = upd["update_id"] + 1
            if approved_any and on_approved:
                on_approved()
