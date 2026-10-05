from __future__ import annotations

import textwrap

import pytest

from backoffice.policy import Guard, agent_legs, redact, validate_agents
from backoffice.registry import RegistryError, load_agents, parse_agent


def agents_of(cfg):
    return load_agents(cfg.path(cfg.paths.agents_dir))


# --- Rule of Two ------------------------------------------------------------------------


def test_shipped_fixture_agents_respect_rule_of_two(cfg):
    assert validate_agents(agents_of(cfg), cfg) == []


def test_untrusted_input_flows_back_from_delegates(cfg):
    agents = agents_of(cfg)
    legs = agent_legs(agents["boss"], agents, cfg)
    assert legs["untrusted_input"] == {"delegate:reader"}
    assert legs["private_data"] == {"mcp__backoffice__crm_search"}
    assert not legs["external_effect"]


def test_trifecta_is_rejected(cfg, repo):
    (repo / ".claude/agents/boss.md").write_text(
        textwrap.dedent("""
        ---
        name: boss
        description: Too powerful.
        tools: Read, Agent, Bash, mcp__backoffice__crm_search
        backoffice:
          delegates: [reader]
          bash_allow: ["git status"]
        ---
        You orchestrate.
        """).strip()
    )
    errors = validate_agents(agents_of(cfg), cfg)
    assert len(errors) == 1 and "Rule of Two" in errors[0] and "boss" in errors[0]


def test_capability_misconfigurations_are_reported(cfg, repo):
    (repo / ".claude/agents/analyst.md").write_text(
        textwrap.dedent("""
        ---
        name: analyst
        description: d
        tools: Read, Write, WebFetch, Bash
        ---
        body
        """).strip()
    )
    errors = " ".join(validate_agents(agents_of(cfg), cfg))
    assert "bash_allow" in errors and "web_domains" in errors and "writes" in errors


def test_registry_rejects_bad_definitions(tmp_path):
    p = tmp_path / "x.md"
    p.write_text("---\nname: y\ndescription: d\n---\nbody")
    with pytest.raises(RegistryError, match="must match file name"):
        parse_agent(p)
    p.write_text("no frontmatter")
    with pytest.raises(RegistryError, match="missing YAML frontmatter"):
        parse_agent(p)


def test_registry_rejects_delegation_without_agent_tool(cfg, repo):
    path = repo / ".claude/agents/boss.md"
    path.write_text(path.read_text().replace("tools: Read, Agent,", "tools: Read,"))
    with pytest.raises(RegistryError, match="no 'Agent' tool"):
        agents_of(cfg)


# --- Guard -----------------------------------------------------------------------------


@pytest.fixture
def analyst(cfg):
    return Guard(cfg, agents_of(cfg)["analyst"])


@pytest.mark.parametrize(
    "path",
    [".env", "config/.env.production", "keys/deploy.pem", "/home/x/.ssh/id_rsa", "service-account-prod.json"],
)
def test_secrets_are_never_readable(cfg, path):
    for guard in (Guard(cfg, None), Guard(cfg, agents_of(cfg)["analyst"])):
        d = guard.check("Read", {"file_path": path})
        assert not d.allow and "secret" in d.reason


def test_ledger_is_off_limits_even_interactively(cfg):
    d = Guard(cfg, None).check("Write", {"file_path": ".backoffice/ledger.db"})
    assert not d.allow and "ledger" in d.reason


def test_writes_are_limited_to_declared_paths(analyst):
    assert analyst.check("Write", {"file_path": "workspace/reports/kpi/w40.md"}).allow
    d = analyst.check("Write", {"file_path": "backoffice.yaml"})
    assert not d.allow and "may only write" in d.reason
    assert not analyst.check("Edit", {"file_path": "/etc/passwd"}).allow
    assert not analyst.check("Write", {"file_path": "workspace/reports/../../backoffice.yaml"}).allow


def test_reads_outside_repo_denied_for_agents(analyst):
    assert not analyst.check("Read", {"file_path": "/etc/hosts"}).allow
    assert analyst.check("Read", {"file_path": "company/goals.md"}).allow
    assert analyst.check("Glob", {"pattern": "*.md", "path": "company"}).allow


@pytest.mark.parametrize(
    "cmd",
    [
        "rm -rf /",
        "git push origin main",
        "curl https://evil.example",
        "echo hi && wget x",
        "sudo ls",
        "gh pr merge 3",
    ],
)
def test_bash_hard_deny_applies_to_everyone(cfg, cmd):
    assert not Guard(cfg, None).check("Bash", {"command": cmd}).allow


def test_bash_needs_allowlist_and_no_chaining(cfg, repo):
    from backoffice.registry import AgentSpec

    agent = AgentSpec(
        name="ops", description="d", prompt="p", tools=("Bash",), bash_allow=("git status", "git diff")
    )
    g = Guard(cfg, agent)
    assert g.check("Bash", {"command": "git status"}).allow
    assert g.check("Bash", {"command": "git diff --stat"}).allow
    assert not g.check("Bash", {"command": "git statusx"}).allow
    assert not g.check("Bash", {"command": "git status; ls"}).allow
    assert not g.check("Bash", {"command": "git diff > out.txt"}).allow
    assert not g.check("Bash", {"command": "ls"}).allow


def test_web_fetch_domain_allowlist(cfg):
    g = Guard(cfg, agents_of(cfg)["reader"])
    assert g.check("WebFetch", {"url": "https://example.com/a"}).allow
    assert g.check("WebFetch", {"url": "https://news.example.com/a"}).allow
    assert not g.check("WebFetch", {"url": "https://example.com.evil.net/a"}).allow
    assert not g.check("WebFetch", {"url": "not a url"}).allow


def test_delegation_and_mcp_allowlists(cfg):
    agents = agents_of(cfg)
    boss = Guard(cfg, agents["boss"])
    assert boss.check("Agent", {"subagent_type": "reader"}).allow
    assert not boss.check("Agent", {"subagent_type": "general-purpose"}).allow
    assert not boss.check("Task", {"subagent_type": "analyst-2"}).allow
    assert boss.check("mcp__backoffice__crm_search", {}).allow
    assert not boss.check("mcp__backoffice__inbound_list", {}).allow


def test_redact_scrubs_and_truncates():
    out = redact(
        {
            "api_key": "sk-123",
            "nested": {"Authorization": "Bearer x"},
            "text": "a" * 1000,
            "items": list(range(30)),
        }
    )
    assert out["api_key"] == "[redacted]"
    assert out["nested"]["Authorization"] == "[redacted]"
    assert "truncated" in out["text"]
    assert len(out["items"]) == 21


def test_unclassified_mcp_tools_fail_validation(cfg, repo):
    path = repo / ".claude/agents/analyst.md"
    path.write_text(path.read_text().replace("tools: Read,", "tools: Read, mcp__hubspot__update_contact,"))
    errors = " ".join(validate_agents(agents_of(cfg), cfg))
    assert "mcp__hubspot__update_contact is not classified" in errors
