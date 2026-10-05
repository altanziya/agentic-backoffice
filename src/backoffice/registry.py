"""Agent registry: `.claude/agents/*.md` is the single source of truth for every agent.

The same Markdown file is used by Claude Code interactively (as a subagent) and by the
headless runtime (as the main agent of a job, or as a delegate). Runtime-only settings live
in a `backoffice:` block in the frontmatter, which Claude Code ignores.

    ---
    name: kpi-analyst
    description: Builds the weekly KPI report from metrics. Use for KPI questions.
    tools: Read, Grep, Glob, Write, mcp__backoffice__metrics_query
    model: sonnet
    backoffice:
      writes: ["workspace/reports/**"]
      delegates: [reviewer]
    ---
    You are the KPI analyst ...
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

FRONTMATTER_DELIM = "---"


@dataclass(frozen=True)
class AgentSpec:
    name: str
    description: str
    prompt: str
    tools: tuple[str, ...]
    model: str | None = None
    effort: str | None = None
    skills: tuple[str, ...] = ()
    writes: tuple[str, ...] = ()  # glob patterns (repo-relative) this agent may Write/Edit
    web_domains: tuple[str, ...] = ()  # allowlist for WebFetch; empty = WebFetch denied
    bash_allow: tuple[str, ...] = ()  # command prefixes allowed for Bash; empty = Bash denied
    delegates: tuple[str, ...] = ()  # subagents this agent may call via the Agent tool
    mcp_servers: tuple[str, ...] = ()  # extra servers from .mcp.json to attach in headless runs
    path: Path | None = field(default=None, compare=False)

    def uses(self, tool: str) -> bool:
        return tool in self.tools


class RegistryError(ValueError):
    pass


def _split_frontmatter(text: str, source: Path) -> tuple[dict[str, Any], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != FRONTMATTER_DELIM:
        raise RegistryError(f"{source}: missing YAML frontmatter")
    try:
        end = next(i for i, line in enumerate(lines[1:], 1) if line.strip() == FRONTMATTER_DELIM)
    except StopIteration:
        raise RegistryError(f"{source}: unterminated YAML frontmatter") from None
    meta = yaml.safe_load("\n".join(lines[1:end])) or {}
    if not isinstance(meta, dict):
        raise RegistryError(f"{source}: frontmatter must be a mapping")
    body = "\n".join(lines[end + 1 :]).strip()
    return meta, body


def _as_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return tuple(t.strip() for t in value.split(",") if t.strip())
    return tuple(str(v).strip() for v in value)


def parse_agent(path: Path) -> AgentSpec:
    meta, body = _split_frontmatter(path.read_text(encoding="utf-8"), path)
    for required in ("name", "description"):
        if not meta.get(required):
            raise RegistryError(f"{path}: frontmatter field {required!r} is required")
    if meta["name"] != path.stem:
        raise RegistryError(f"{path}: name {meta['name']!r} must match file name {path.stem!r}")
    if not body:
        raise RegistryError(f"{path}: agent prompt (body) is empty")
    extra = meta.get("backoffice") or {}
    return AgentSpec(
        name=meta["name"],
        description=str(meta["description"]).strip(),
        prompt=body,
        tools=_as_tuple(meta.get("tools")),
        model=meta.get("model"),
        effort=meta.get("effort"),
        skills=_as_tuple(meta.get("skills")),
        writes=_as_tuple(extra.get("writes")),
        web_domains=_as_tuple(extra.get("web_domains")),
        bash_allow=_as_tuple(extra.get("bash_allow")),
        delegates=_as_tuple(extra.get("delegates")),
        mcp_servers=_as_tuple(extra.get("mcp_servers")),
        path=path,
    )


def load_agents(agents_dir: Path) -> dict[str, AgentSpec]:
    if not agents_dir.is_dir():
        raise RegistryError(f"agents directory not found: {agents_dir}")
    agents = {p.stem: parse_agent(p) for p in sorted(agents_dir.glob("*.md"))}
    for agent in agents.values():
        for d in agent.delegates:
            if d not in agents:
                raise RegistryError(f"{agent.name}: delegates to unknown agent {d!r}")
            if d == agent.name:
                raise RegistryError(f"{agent.name}: an agent cannot delegate to itself")
        if agent.delegates and "Agent" not in agent.tools:
            raise RegistryError(f"{agent.name}: has delegates but no 'Agent' tool")
    return agents
