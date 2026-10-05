"""Runner behaviour with a scripted stand-in for the Agent SDK's `query()`."""

from __future__ import annotations

import pytest
from claude_agent_sdk import ResultMessage

from backoffice.runner import Runner, job_lock


def result(
    subtype="success",
    *,
    cost=0.10,
    turns=4,
    session="S-1",
    is_error=False,
    structured=None,
    errors=None,
    api_error_status=None,
):
    return ResultMessage(
        subtype=subtype,
        duration_ms=1000,
        duration_api_ms=900,
        is_error=is_error,
        num_turns=turns,
        session_id=session,
        total_cost_usd=cost,
        errors=errors,
        structured_output=structured
        if structured is not None
        else (
            {
                "status": "ok",
                "summary": "done",
                "artifacts": [],
                "proposed_actions": [],
                "data_gaps": [],
                "needs_human": [],
            }
            if subtype == "success"
            else None
        ),
        api_error_status=api_error_status,
    )


class Script:
    """Each call to query() plays the next scripted attempt: a ResultMessage or an exception."""

    def __init__(self, *attempts):
        self.attempts = list(attempts)
        self.calls = []

    def __call__(self, *, prompt, options):
        self.calls.append((prompt, options))
        step = self.attempts.pop(0)

        async def gen():
            if isinstance(step, Exception):
                raise step
            yield step

        return gen()


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    async def instant(_):
        return None

    monkeypatch.setattr("backoffice.runner.asyncio.sleep", instant)


async def test_success_is_recorded_and_never_retried(cfg, ledger):
    script = Script(result(cost=0.12))
    out = await Runner(cfg, query_fn=script).run_job("kpi", logical_date="2026-10-05")
    assert out.status == "success" and out.attempts == 1 and len(script.calls) == 1
    assert out.report["summary"] == "done"
    run = ledger.runs(limit=1)[0]
    assert run["status"] == "success" and run["cost_usd"] == pytest.approx(0.12)


async def test_options_encode_the_safety_model(cfg):
    script = Script(result())
    await Runner(cfg, query_fn=script).run_job("kpi", logical_date="2026-10-05")
    prompt, opts = script.calls[0]
    assert prompt == "Report for 2026-10-05."
    assert opts.permission_mode == "dontAsk"
    assert opts.strict_mcp_config is True
    assert "Skill" in opts.allowed_tools and "Bash" not in opts.allowed_tools
    assert opts.max_budget_usd == 0.5 and opts.max_turns == 5
    assert opts.env["CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH"] == "1"
    assert opts.output_format["type"] == "json_schema"
    assert "No human is watching" in opts.system_prompt["append"]
    assert set(opts.hooks) == {"PreToolUse", "PostToolUse", "PostToolUseFailure"}


async def test_delegates_become_sdk_subagents(cfg, monkeypatch):
    monkeypatch.setenv("BACKOFFICE_TEST_REQUIRED", "1")
    script = Script(result())
    await Runner(cfg, query_fn=script).run_job("briefing")
    _, opts = script.calls[0]
    assert set(opts.agents) == {"reader", "analyst"}
    assert opts.agents["reader"].tools == ["WebFetch", "WebSearch", "Read"]
    # delegates run synchronously: the orchestrator must see findings before it reports
    assert opts.agents["reader"].background is False
    # the output language reaches delegates too, not only the main agent
    assert opts.agents["reader"].prompt.endswith("Write your answer in English.")
    assert opts.env["CLAUDE_CODE_DISABLE_BACKGROUND_TASKS"] == "1"
    # the main session must be allowed to run its delegates' tools
    assert {"WebFetch", "mcp__backoffice__metrics_query"} <= set(opts.allowed_tools)


async def test_transient_failure_is_retried_fresh(cfg):
    script = Script(RuntimeError("CLI connection lost"), result())
    out = await Runner(cfg, query_fn=script).run_job("kpi")
    assert out.status == "success" and out.attempts == 2
    assert script.calls[1][1].resume is None


async def test_max_turns_resumes_the_session_with_more_room(cfg):
    script = Script(result("error_max_turns", session="S-9", is_error=True), result())
    out = await Runner(cfg, query_fn=script).run_job("kpi")
    assert out.status == "success"
    second = script.calls[1][1]
    assert second.resume == "S-9" and second.max_turns == 7
    assert script.calls[1][0] == "Continue and finish the task."
    assert out.cost_usd == pytest.approx(0.20)  # both attempts count


async def test_budget_stop_and_auth_errors_are_not_retried(cfg):
    script = Script(result("error_max_budget_usd", is_error=True))
    out = await Runner(cfg, query_fn=script).run_job("kpi")
    assert out.status == "failed" and len(script.calls) == 1

    script = Script(result("error_during_execution", is_error=True, api_error_status=401))
    out = await Runner(cfg, query_fn=script).run_job("kpi")
    assert out.status == "failed" and len(script.calls) == 1


async def test_third_party_401_in_tool_output_is_not_an_auth_error(cfg):
    # production lesson: grepping logs for "401" stopped runs when a scraper cookie expired
    script = Script(
        result(
            "error_during_execution", is_error=True, errors=["tool fetch returned 401 from api.example.com"]
        ),
        result(),
    )
    out = await Runner(cfg, query_fn=script).run_job("kpi")
    assert out.status == "success" and len(script.calls) == 2


async def test_gates_skip_without_spending(cfg, ledger, monkeypatch):
    script = Script()
    runner = Runner(cfg, query_fn=script)

    cfg.kill_switch.parent.mkdir(parents=True, exist_ok=True)
    cfg.kill_switch.write_text("on")
    assert (await runner.run_job("kpi")).status == "killed"
    cfg.kill_switch.unlink()

    out = await runner.run_job("briefing")  # required env var missing
    assert out.status == "preflight_failed" and "BACKOFFICE_TEST_REQUIRED" in out.error

    ledger.start_run("R-x", "kpi", "analyst")
    ledger.finish_run("R-x", status="success", cost_usd=5.0)  # daily cap is 5
    assert (await runner.run_job("kpi")).status == "budget_blocked"

    assert script.calls == []


async def test_overlapping_run_is_skipped(cfg):
    script = Script(result())
    with job_lock(cfg.state_dir, "kpi") as got:
        assert got
        out = await Runner(cfg, query_fn=script).run_job("kpi")
    assert out.status == "skipped" and "in progress" in out.error and script.calls == []


async def test_t1_proposals_are_executed_after_the_run(cfg, ledger):
    from backoffice.outbox import RunContext, propose

    class ProposingScript(Script):
        def __call__(self, *, prompt, options):
            env = options.env
            ctx = RunContext(
                env["BACKOFFICE_RUN_ID"],
                env["BACKOFFICE_JOB"],
                env["BACKOFFICE_AGENT"],
                env["BACKOFFICE_DATE"],
            )
            propose(
                cfg,
                ledger,
                ctx,
                kind="report.publish",
                title="t",
                justification="j",
                payload={"path": "r.md", "content": "hi"},
            )
            return super().__call__(prompt=prompt, options=options)

    out = await Runner(cfg, query_fn=ProposingScript(result())).run_job("kpi")
    assert len(out.executed) == 1
    assert (cfg.root / "workspace/published/r.md").read_text() == "hi"


async def test_extra_mcp_servers_are_opt_in_per_agent(cfg, repo):
    import json

    (repo / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"analytics": {"command": "analytics-mcp"}, "unused": {"command": "x"}}})
    )
    path = repo / ".claude/agents/analyst.md"
    path.write_text(path.read_text().replace("backoffice:\n", "backoffice:\n  mcp_servers: [analytics]\n"))
    script = Script(result())
    await Runner(cfg, query_fn=script).run_job("kpi")
    servers = script.calls[0][1].mcp_servers
    assert set(servers) == {"analytics", "backoffice"}
