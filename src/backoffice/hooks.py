"""Hook adapters: one guard, two entry points.

* `sdk_hooks(...)`  - async callbacks for headless runs (Claude Agent SDK `hooks=`).
                      Resolves the acting agent per call, so a subagent is checked against
                      its own allowlists, not its parent's.
* `cli_hook(...)`   - `backoffice hook pre-tool-use|post-tool-use`, wired in
                      `.claude/settings.json` for interactive Claude Code sessions.
                      Exit code 2 blocks the call (documented Claude Code hook contract).
"""

from __future__ import annotations

import json
import sys
from typing import Any

from .config import BackofficeConfig
from .ledger import Ledger
from .policy import Guard, redact
from .registry import AgentSpec


def _deny(reason: str) -> dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def sdk_hooks(
    cfg: BackofficeConfig,
    ledger: Ledger,
    run_id: str,
    main: AgentSpec,
    agents: dict[str, AgentSpec],
    counters: dict[str, int] | None = None,
) -> dict[str, list[Any]]:
    from claude_agent_sdk import HookMatcher

    counters = counters if counters is not None else {}

    def acting(input_data: dict[str, Any]) -> AgentSpec:
        sub = input_data.get("agent_type")
        return agents.get(sub, main) if sub else main

    async def pre_tool_use(
        input_data: dict[str, Any], tool_use_id: str | None, context: Any
    ) -> dict[str, Any]:
        agent = acting(input_data)
        tool = input_data.get("tool_name", "")
        tool_input = input_data.get("tool_input") or {}
        decision = Guard(cfg, agent).check(tool, tool_input)
        if not decision.allow:
            counters["denied"] = counters.get("denied", 0) + 1
            ledger.audit(
                run_id,
                agent.name,
                "tool_denied",
                tool,
                {"input": redact(tool_input), "reason": decision.reason},
            )
            return _deny(decision.reason)
        counters["tool_calls"] = counters.get("tool_calls", 0) + 1
        ledger.audit(run_id, agent.name, "tool_call", tool, {"input": redact(tool_input)})
        return {}

    async def post_tool_use(
        input_data: dict[str, Any], tool_use_id: str | None, context: Any
    ) -> dict[str, Any]:
        agent = acting(input_data)
        ledger.audit(
            run_id,
            agent.name,
            "tool_result",
            input_data.get("tool_name"),
            {"response": redact(input_data.get("tool_response"), limit=200)},
        )
        return {}

    async def post_tool_failure(
        input_data: dict[str, Any], tool_use_id: str | None, context: Any
    ) -> dict[str, Any]:
        agent = acting(input_data)
        counters["tool_errors"] = counters.get("tool_errors", 0) + 1
        ledger.audit(
            run_id,
            agent.name,
            "tool_error",
            input_data.get("tool_name"),
            {"error": redact(input_data.get("error"), limit=300)},
        )
        return {}

    return {
        "PreToolUse": [HookMatcher(matcher=None, hooks=[pre_tool_use])],
        "PostToolUse": [HookMatcher(matcher=None, hooks=[post_tool_use])],
        "PostToolUseFailure": [HookMatcher(matcher=None, hooks=[post_tool_failure])],
    }


def cli_hook(event: str, cfg: BackofficeConfig, stdin: str | None = None) -> int:
    """Entry point for `.claude/settings.json` command hooks in interactive sessions."""
    data = json.loads(stdin if stdin is not None else sys.stdin.read() or "{}")
    tool = data.get("tool_name", "")
    tool_input = data.get("tool_input") or {}
    ledger = Ledger(cfg.ledger_path)
    if event == "pre-tool-use":
        # Interactive sessions are supervised by a human, so only the hard rules apply here
        # (secrets, ledger, destructive/network shell). Per-agent allowlists apply headless.
        decision = Guard(cfg, None).check(tool, tool_input)
        if not decision.allow:
            ledger.audit(
                None,
                "interactive",
                "tool_denied",
                tool,
                {"input": redact(tool_input), "reason": decision.reason},
            )
            print(f"agentic-backoffice guard: {decision.reason}", file=sys.stderr)
            return 2
        return 0
    if event == "post-tool-use":
        ledger.audit(None, "interactive", "tool_call", tool, {"input": redact(tool_input)})
        return 0
    print(f"unknown hook event {event!r}", file=sys.stderr)
    return 1
