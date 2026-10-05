"""Action handlers: the code that performs approved side effects.

Handlers run in the executor process, outside any agent session, with credentials the agents
never see. Each handler validates its payload itself - an approved action is still untrusted
input to the handler. Destinations (URLs, repos, chats) come from `params` in
`backoffice.yaml`, never from the payload, so a manipulated proposal cannot redirect data.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

from ..config import BackofficeConfig
from ..data import CRM

Handler = Callable[[BackofficeConfig, dict[str, Any], dict[str, Any]], dict[str, Any]]
HANDLERS: dict[str, Handler] = {}


class ActionError(RuntimeError):
    pass


def handler(name: str) -> Callable[[Handler], Handler]:
    def deco(fn: Handler) -> Handler:
        HANDLERS[name] = fn
        return fn

    return deco


def _require(payload: dict[str, Any], *keys: str) -> None:
    missing = [k for k in keys if k not in payload]
    if missing:
        raise ActionError(f"payload is missing {missing}")


def _inside(root: Path, rel: str) -> Path:
    target = (root / rel).resolve()
    if root.resolve() not in target.parents:
        raise ActionError(f"path {rel!r} escapes {root}")
    if ".git" in target.parts:
        raise ActionError("refusing to write inside .git")
    return target


@handler("file.write")
def file_write(cfg: BackofficeConfig, params: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    """Write one file under params.root (e.g. publish a report to the team folder)."""
    _require(payload, "path", "content")
    root = cfg.path(params.get("root", cfg.paths.workspace + "/published"))
    root.mkdir(parents=True, exist_ok=True)
    target = _inside(root, str(payload["path"]))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(str(payload["content"]), encoding="utf-8")
    return {"written": str(target.relative_to(cfg.root)), "bytes": len(str(payload["content"]))}


@handler("crm.update")
def crm_update(cfg: BackofficeConfig, params: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    """Update whitelisted CRM fields and/or log an activity. payload: {table, id, fields} and/or
    {activity: {contact_id, ts, kind, summary}}."""
    crm = CRM(cfg.state_dir / "crm.db", seed_dir=cfg.path(cfg.paths.company_dir) / "data" / "crm")
    out: dict[str, Any] = {}
    if "fields" in payload:
        _require(payload, "table", "id", "fields")
        out["update"] = crm.update(payload["table"], payload["id"], dict(payload["fields"]))
    if "activity" in payload:
        a = payload["activity"]
        _require(a, "contact_id", "ts", "kind", "summary")
        crm.log_activity(a["contact_id"], a["ts"], a["kind"], a["summary"])
        out["activity_logged"] = a["contact_id"]
    if not out:
        raise ActionError("payload needs 'fields' (with table, id) and/or 'activity'")
    return out


def _git(repo: Path, *args: str) -> str:
    res = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if res.returncode != 0:
        raise ActionError(f"git {' '.join(args)} failed: {res.stderr.strip()[:300]}")
    return res.stdout.strip()


@handler("github.pull_request")
def github_pull_request(
    cfg: BackofficeConfig, params: dict[str, Any], payload: dict[str, Any]
) -> dict[str, Any]:
    """Commit files on a new branch of params.repo and (if params.push) open a PR via `gh`.

    payload: {branch, title, body, files: {relative/path: new content}}
    Idempotent: an existing branch is reported, not overwritten. Never touches the base branch.
    """
    _require(payload, "branch", "title", "files")
    repo = cfg.path(params["repo"])
    base = params.get("base", "main")
    branch = str(payload["branch"])
    prefix = params.get("branch_prefix", "agent/")
    if not branch.startswith(prefix):
        raise ActionError(f"branch must start with {prefix!r}")
    if not (repo / ".git").exists():
        raise ActionError(f"{repo} is not a git repository")
    if _git(repo, "branch", "--list", branch):
        return {"status": "exists", "branch": branch}
    current = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    _git(repo, "switch", "-c", branch, base)
    try:
        for rel, content in dict(payload["files"]).items():
            target = _inside(repo, rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(str(content), encoding="utf-8")
            _git(repo, "add", "--", rel)
        _git(
            repo,
            "-c",
            "user.name=agentic-backoffice",
            "-c",
            "user.email=agents@localhost",
            "commit",
            "-m",
            str(payload["title"]),
        )
        result: dict[str, Any] = {
            "status": "committed",
            "branch": branch,
            "commit": _git(repo, "rev-parse", "HEAD"),
        }
        if params.get("push"):
            _git(repo, "push", "-u", "origin", branch)
            pr = subprocess.run(
                [
                    "gh",
                    "pr",
                    "create",
                    "--base",
                    base,
                    "--head",
                    branch,
                    "--title",
                    str(payload["title"]),
                    "--body",
                    str(payload.get("body", "")),
                ],
                cwd=repo,
                capture_output=True,
                text=True,
            )
            if pr.returncode != 0:
                raise ActionError(f"gh pr create failed: {pr.stderr.strip()[:300]}")
            result.update(status="pr_opened", url=pr.stdout.strip())
        return result
    finally:
        _git(repo, "switch", current)


@handler("notify.telegram")
def notify_telegram(cfg: BackofficeConfig, params: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    """Send a message to the team chat configured in params (never a payload-supplied chat)."""
    _require(payload, "text")
    token = os.environ.get(params.get("bot_token_env", "TELEGRAM_BOT_TOKEN"), "")
    chat = os.environ.get(params.get("chat_id_env", "TELEGRAM_CHAT_ID"), "")
    if not token or not chat:
        raise ActionError("telegram token/chat env vars are not set")
    r = httpx.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat, "text": str(payload["text"])[:4096]},
        timeout=20,
    )
    if not r.json().get("ok"):
        raise ActionError(f"telegram send failed: {r.json().get('description')}")
    return {"sent": True}


@handler("webhook.post")
def webhook_post(cfg: BackofficeConfig, params: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    """POST the payload's `json` to the URL in env var params.url_env (Slack, n8n, Zapier ...)."""
    _require(payload, "json")
    url = os.environ.get(params.get("url_env", ""), "")
    if not url.startswith("https://"):
        raise ActionError(f"env var {params.get('url_env')!r} must hold an https URL")
    r = httpx.post(url, json=payload["json"], timeout=20)
    if r.status_code >= 300:
        raise ActionError(f"webhook returned HTTP {r.status_code}")
    return {"status_code": r.status_code}


@handler("refuse")
def refuse(cfg: BackofficeConfig, params: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    raise ActionError("T3 actions are never executed automatically")
