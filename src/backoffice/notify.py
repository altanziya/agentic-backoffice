"""Operator notifications (run summaries, failures). Best effort, never raises."""

from __future__ import annotations

import logging
import os

import httpx

from .config import BackofficeConfig

log = logging.getLogger(__name__)


def notify(cfg: BackofficeConfig, text: str) -> bool:
    if cfg.notify.channel == "stdout":
        print(text)
        return True
    t = cfg.approvals.telegram
    token, chat = os.environ.get(t.bot_token_env, ""), os.environ.get(t.chat_id_env, "")
    if not token or not chat:
        log.warning("notify: telegram env vars missing; message dropped: %s", text[:200])
        return False
    try:
        r = httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": text[:4096]},
            timeout=20,
        )
        ok = bool(r.json().get("ok"))
    except (httpx.HTTPError, ValueError) as e:
        log.warning("notify failed: %s", e)
        return False
    if not ok:
        # Production lesson: a silently failing notifier is how outages go unnoticed for days.
        log.warning("notify rejected by telegram: %s", r.text[:200])
    return ok
