"""Policy: guardrails that live in code, not in prompts.

Two mechanisms:

1. **Static: Rule of Two.** Every tool is mapped to the legs of the "lethal trifecta"
   (untrusted input, private data, external effect). An agent - including what its delegates
   feed back to it - may hold at most two legs. `validate_agents` fails the build otherwise.
   In practice no agent holds `external_effect` at all: side effects go through the outbox
   (`propose_action`) and a human, which is what makes reading untrusted content tolerable.

2. **Dynamic: the guard.** A PreToolUse hook that runs before every tool call - also for
   subagents - and denies secret paths, writes outside the agent's declared paths, unlisted
   web domains, unlisted Bash commands, and delegation to undeclared subagents. Hooks run
   before permission rules and cannot be talked out of by the model.
"""

from __future__ import annotations

import fnmatch
import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .config import BackofficeConfig
from .registry import AgentSpec

LEGS = ("untrusted_input", "private_data", "external_effect")

SECRET_GLOBS = (
    "**/.env",
    "**/.env.*",
    "**/*.pem",
    "**/*.key",
    "**/*.p12",
    "**/id_rsa*",
    "**/id_ed25519*",
    "**/.ssh/**",
    "**/.aws/**",
    "**/.config/gcloud/**",
    "**/credentials*.json",
    "**/service-account*.json",
    "**/.netrc",
    "**/.git-credentials",
    "**/.git/config",
)

# Never allowed, not even in a supervised interactive session.
BASH_HARD_DENY = re.compile(
    r"""(^|[\s;&|(])(
        rm\s+-[a-z]*r[a-z]*f | rm\s+-[a-z]*f[a-z]*r | sudo | su\s | mkfs | dd\s+if= |
        git\s+push | git\s+reset\s+--hard | gh\s+pr\s+merge | gh\s+repo\s+delete |
        curl | wget | nc\s | ncat | ssh\s | scp\s | rsync\s | ftp\s |
        systemctl | crontab | chmod\s+-R\s+777 | :\(\)\s*\{
    )""",
    re.VERBOSE,
)
SHELL_CHAINING = re.compile(r"[;&|`<>]|\$\(")

PATH_KEYS = {
    "Read": ("file_path",),
    "Write": ("file_path",),
    "Edit": ("file_path",),
    "MultiEdit": ("file_path",),
    "NotebookEdit": ("notebook_path",),
    "Glob": ("path", "pattern"),
    "Grep": ("path",),
}
WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}


# --- static analysis: Rule of Two ---------------------------------------------------------


def tool_legs(tool: str, cfg: BackofficeConfig) -> set[str]:
    legs = set()
    caps = cfg.capabilities
    for leg in LEGS:
        if any(fnmatch.fnmatchcase(tool, pat) for pat in getattr(caps, leg)):
            legs.add(leg)
    return legs


def agent_legs(
    agent: AgentSpec, agents: dict[str, AgentSpec], cfg: BackofficeConfig, _seen: frozenset = frozenset()
) -> dict[str, set[str]]:
    """Map leg -> tools (or `delegate:<name>`) that give this agent that leg.

    Untrusted input is transitive: whatever a delegate read can flow back in its answer.
    Private data and external effects are not inherited - the delegate holds them, not us -
    but the delegate itself is checked on its own.
    """
    found: dict[str, set[str]] = {leg: set() for leg in LEGS}
    for tool in agent.tools:
        for leg in tool_legs(tool, cfg):
            found[leg].add(tool)
    for name in agent.delegates:
        if name in _seen or name not in agents:
            continue
        sub = agent_legs(agents[name], agents, cfg, _seen | {agent.name})
        if sub["untrusted_input"]:
            found["untrusted_input"].add(f"delegate:{name}")
    return found


def validate_agents(agents: dict[str, AgentSpec], cfg: BackofficeConfig) -> list[str]:
    errors: list[str] = []
    for agent in agents.values():
        legs = agent_legs(agent, agents, cfg)
        held = [leg for leg in LEGS if legs[leg]]
        if len(held) == 3:
            detail = "; ".join(f"{leg}: {', '.join(sorted(legs[leg]))}" for leg in LEGS)
            errors.append(
                f"{agent.name}: violates the Rule of Two (holds all three trifecta legs - {detail}). "
                "Route the side effect through propose_action or split the agent."
            )
        for tool in agent.tools:
            if tool.startswith("mcp__") and not (
                tool_legs(tool, cfg) or any(fnmatch.fnmatchcase(tool, p) for p in cfg.capabilities.no_leg)
            ):
                errors.append(
                    f"{agent.name}: MCP tool {tool} is not classified in capabilities "
                    "(untrusted_input / private_data / external_effect / no_leg)"
                )
        if "Bash" in agent.tools and not agent.bash_allow:
            errors.append(f"{agent.name}: has Bash but no backoffice.bash_allow prefixes")
        if "WebFetch" in agent.tools and not agent.web_domains:
            errors.append(f"{agent.name}: has WebFetch but no backoffice.web_domains allowlist")
        if WRITE_TOOLS & set(agent.tools) and not agent.writes:
            errors.append(f"{agent.name}: has write tools but no backoffice.writes paths")
    return errors


# --- dynamic guard ------------------------------------------------------------------------


@dataclass(frozen=True)
class Decision:
    allow: bool
    reason: str = ""

    @classmethod
    def ok(cls) -> Decision:
        return cls(True)

    @classmethod
    def deny(cls, reason: str) -> Decision:
        return cls(False, reason)


class Guard:
    """Evaluates one tool call. `agent=None` means a supervised interactive session:
    only the hard rules apply (secrets, ledger, destructive shell commands)."""

    def __init__(self, cfg: BackofficeConfig, agent: AgentSpec | None):
        self.cfg = cfg
        self.agent = agent
        self.root = cfg.root.resolve()

    # paths ---------------------------------------------------------------------------------
    def _resolve(self, raw: str) -> Path:
        p = Path(raw).expanduser()
        return (p if p.is_absolute() else self.root / p).resolve()

    def _rel(self, p: Path) -> str | None:
        try:
            return p.relative_to(self.root).as_posix()
        except ValueError:
            return None

    def _is_secret(self, p: Path) -> bool:
        s = p.as_posix()
        return any(fnmatch.fnmatch(s, g) or fnmatch.fnmatch(s, g.removeprefix("**/")) for g in SECRET_GLOBS)

    def _is_state(self, p: Path) -> bool:
        state = self.cfg.state_dir.resolve()
        return p == state or state in p.parents

    def check_path(self, tool: str, raw: str) -> Decision:
        p = self._resolve(raw)
        if self._is_secret(p):
            return Decision.deny(f"{raw} matches a secret-file pattern; secrets are never readable")
        if self._is_state(p):
            return Decision.deny(f"{raw} is inside the ledger/state dir; agents cannot touch it")
        if self.agent is None:
            return Decision.ok()
        rel = self._rel(p)
        if rel is None:
            return Decision.deny(f"{raw} is outside the back-office repo")
        if tool in WRITE_TOOLS and not any(fnmatch.fnmatch(rel, g) for g in self.agent.writes):
            allowed = ", ".join(self.agent.writes) or "(nothing)"
            return Decision.deny(f"{self.agent.name} may only write to: {allowed}; refused {rel}")
        return Decision.ok()

    # tools ---------------------------------------------------------------------------------
    def check(self, tool: str, tool_input: dict[str, Any]) -> Decision:
        for key in PATH_KEYS.get(tool, ()):
            value = tool_input.get(key)
            if not value:
                continue
            if key == "pattern" and not any(ch in value for ch in "/\\") and not value.startswith("."):
                continue  # a bare glob like "*.md" relative to `path` - checked via `path`
            d = self.check_path(tool, value)
            if not d.allow:
                return d
        if tool == "Bash":
            return self._check_bash(str(tool_input.get("command", "")))
        if tool == "WebFetch":
            return self._check_url(str(tool_input.get("url", "")))
        if tool in {"Agent", "Task"}:
            return self._check_delegate(str(tool_input.get("subagent_type", "")))
        if self.agent is not None and tool.startswith("mcp__") and tool not in self.agent.tools:
            return Decision.deny(f"{self.agent.name} is not allowed to call {tool}")
        return Decision.ok()

    def _check_bash(self, command: str) -> Decision:
        if BASH_HARD_DENY.search(command):
            return Decision.deny("command matches the hard deny list (destructive, network or push)")
        if self.agent is None:
            return Decision.ok()
        if not self.agent.bash_allow:
            return Decision.deny(f"{self.agent.name} has no shell access")
        if SHELL_CHAINING.search(command):
            return Decision.deny("shell chaining, pipes and redirects are not allowed for agents")
        try:
            argv = shlex.split(command)
        except ValueError:
            return Decision.deny("command could not be parsed")
        joined = " ".join(argv)
        if not any(joined == p or joined.startswith(p + " ") for p in self.agent.bash_allow):
            return Decision.deny(f"command not in {self.agent.name}'s bash allowlist")
        return Decision.ok()

    def _check_url(self, url: str) -> Decision:
        if self.agent is None:
            return Decision.ok()
        host = (urlparse(url).hostname or "").lower()
        if not host:
            return Decision.deny("WebFetch needs an absolute URL")
        if any(host == d or host.endswith("." + d) for d in self.agent.web_domains):
            return Decision.ok()
        return Decision.deny(f"{host} is not on {self.agent.name}'s web_domains allowlist")

    def _check_delegate(self, name: str) -> Decision:
        if self.agent is None:
            return Decision.ok()
        if name in self.agent.delegates:
            return Decision.ok()
        return Decision.deny(f"{self.agent.name} may not delegate to {name or '(unnamed)'}")


# --- audit redaction ----------------------------------------------------------------------

SENSITIVE_KEY = re.compile(r"(token|secret|password|passwd|api[_-]?key|authorization|cookie)", re.I)


def redact(value: Any, limit: int = 400) -> Any:
    """Shrink and scrub tool inputs/outputs before they enter the audit trail."""
    if isinstance(value, dict):
        return {
            k: ("[redacted]" if SENSITIVE_KEY.search(str(k)) else redact(v, limit)) for k, v in value.items()
        }
    if isinstance(value, list):
        items = [redact(v, limit) for v in value[:20]]
        return items + ([f"... {len(value) - 20} more"] if len(value) > 20 else [])
    if isinstance(value, str) and len(value) > limit:
        return value[:limit] + f"... [{len(value) - limit} chars truncated]"
    return value
