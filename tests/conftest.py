from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from backoffice.config import BackofficeConfig, load_config
from backoffice.ledger import Ledger

CONFIG = """
name: test
timezone: Europe/Berlin
defaults: {model: haiku, max_turns: 5, max_budget_usd: 0.5, timeout_minutes: 1, retries: 1}
budgets: {daily_usd: 5, monthly_usd: 50}
approvals: {channel: cli, expire_hours: 1}
capabilities:
  untrusted_input: [WebFetch, WebSearch, mcp__backoffice__inbound_list]
  private_data: ["mcp__backoffice__crm_*", "mcp__backoffice__metrics_*"]
  external_effect: [Bash, "mcp__*__send*"]
  no_leg: [mcp__backoffice__propose_action]
actions:
  report.publish: {tier: T1, handler: file.write, params: {root: workspace/published}}
  crm.update: {tier: T2, handler: crm.update}
  site.pull_request:
    tier: T2
    handler: github.pull_request
    params: {repo: workspace/site, base: main, branch_prefix: "agent/"}
  payment.send: {tier: T3, handler: refuse}
jobs:
  kpi:
    agent: analyst
    prompt: "Report for {date}."
    schedule: "0 7 * * 1"
  briefing:
    agent: boss
    prompt: "Brief for {date}."
    requires: ["env:BACKOFFICE_TEST_REQUIRED"]
"""

AGENTS = {
    "analyst": """
        ---
        name: analyst
        description: Analyses metrics.
        tools: Read, Grep, Write, mcp__backoffice__metrics_query, mcp__backoffice__propose_action
        model: sonnet
        backoffice:
          writes: ["workspace/reports/**"]
        ---
        You analyse metrics.
        """,
    "reader": """
        ---
        name: reader
        description: Reads the web.
        tools: WebFetch, WebSearch, Read
        backoffice:
          web_domains: [example.com]
        ---
        You read web pages and return JSON.
        """,
    "boss": """
        ---
        name: boss
        description: Orchestrates.
        tools: Read, Agent, mcp__backoffice__crm_search, mcp__backoffice__propose_action
        backoffice:
          delegates: [reader, analyst]
        ---
        You orchestrate.
        """,
}


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "backoffice.yaml").write_text(CONFIG)
    agents = tmp_path / ".claude" / "agents"
    agents.mkdir(parents=True)
    for name, body in AGENTS.items():
        (agents / f"{name}.md").write_text(textwrap.dedent(body).strip() + "\n")
    (tmp_path / "workspace").mkdir()
    return tmp_path


@pytest.fixture
def cfg(repo: Path) -> BackofficeConfig:
    return load_config(repo)


@pytest.fixture
def ledger(cfg: BackofficeConfig) -> Ledger:
    return Ledger(cfg.ledger_path)
