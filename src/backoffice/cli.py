"""`backoffice` command line. Every operator task is one command; nothing needs a dashboard."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import logging
import shutil
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .config import BackofficeConfig, Tier, load_config
from .ledger import IllegalTransition, Ledger, iso, now
from .policy import LEGS, agent_legs, validate_agents
from .registry import RegistryError, load_agents


def _table(rows: list[list[str]], header: list[str]) -> str:
    widths = [max(len(str(x)) for x in col) for col in zip(header, *rows, strict=False)]
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    out = [fmt.format(*header), fmt.format(*("-" * w for w in widths))]
    out += [fmt.format(*(str(c) for c in r)) for r in rows]
    return "\n".join(out)


# --- validate / inspect --------------------------------------------------------------------


def validate(cfg: BackofficeConfig) -> list[str]:
    from .actions import HANDLERS

    errors: list[str] = []
    try:
        agents = load_agents(cfg.path(cfg.paths.agents_dir))
    except RegistryError as e:
        return [str(e)]
    errors += validate_agents(agents, cfg)
    skills_dir = cfg.root / ".claude" / "skills"
    for agent in agents.values():
        for skill in agent.skills:
            if not (skills_dir / skill / "SKILL.md").exists():
                errors.append(f"{agent.name}: skill {skill!r} not found in .claude/skills/")
    for name, job in cfg.jobs.items():
        if job.agent not in agents:
            errors.append(f"job {name}: unknown agent {job.agent!r}")
        try:
            job.prompt.format(date="x", run_id="x")
        except (KeyError, IndexError) as e:
            errors.append(f"job {name}: prompt has an unknown placeholder {e}")
        if job.schedule:
            from .schedule import Cron

            try:
                Cron(job.schedule)
            except ValueError as e:
                errors.append(f"job {name}: {e}")
    for name, action in cfg.actions.items():
        if action.handler not in HANDLERS:
            errors.append(f"action {name}: unknown handler {action.handler!r}")
    try:
        ZoneInfo(cfg.timezone)
    except Exception:  # noqa: BLE001
        errors.append(f"timezone {cfg.timezone!r} is not a valid IANA zone")
    return errors


def cmd_validate(cfg: BackofficeConfig, args: argparse.Namespace) -> int:
    errors = validate(cfg)
    for e in errors:
        print(f"ERROR  {e}")
    if errors:
        return 1
    agents = load_agents(cfg.path(cfg.paths.agents_dir))
    print(
        f"OK  {len(agents)} agents, {len(cfg.jobs)} jobs, {len(cfg.actions)} action kinds; "
        "Rule of Two holds for every agent."
    )
    return 0


def cmd_agents(cfg: BackofficeConfig, args: argparse.Namespace) -> int:
    agents = load_agents(cfg.path(cfg.paths.agents_dir))
    rows = []
    for a in agents.values():
        legs = agent_legs(a, agents, cfg)
        mark = "".join(code if legs[leg] else "." for leg, code in zip(LEGS, "UPE", strict=True))
        rows.append(
            [
                a.name,
                a.model or cfg.defaults.model,
                mark,
                ", ".join(a.delegates) or "-",
                ", ".join(a.writes) or "-",
            ]
        )
    print(_table(rows, ["agent", "model", "U/P/E", "delegates", "may write"]))
    print("\nU = reads untrusted input, P = private data, E = direct external effect. At most two per agent.")
    return 0


def cmd_jobs(cfg: BackofficeConfig, args: argparse.Namespace) -> int:
    from .schedule import Cron

    tz = ZoneInfo(cfg.timezone)
    local_now = datetime.now(tz)
    ledger = Ledger(cfg.ledger_path)
    rows = []
    for name, job in cfg.jobs.items():
        nxt = Cron(job.schedule).next_after(local_now) if job.schedule and job.enabled else None
        last = ledger.runs(limit=1, job=name)
        rows.append(
            [
                name,
                job.agent,
                job.schedule or "manual",
                nxt.strftime("%a %d.%m %H:%M") if nxt else "-",
                last[0]["status"] if last else "never",
            ]
        )
    print(_table(rows, ["job", "agent", "schedule", f"next ({cfg.timezone})", "last run"]))
    return 0


# --- running -------------------------------------------------------------------------------


def _print_outcome(o) -> None:  # type: ignore[no-untyped-def]
    print(
        f"{o.job}: {o.status} ({o.subtype or '-'}) run={o.run_id} cost=${o.cost_usd:.3f} "
        f"turns={o.num_turns} attempts={o.attempts} tools={o.tool_calls} denied={o.tools_denied}"
    )
    if o.report:
        print(json.dumps(o.report, indent=1, ensure_ascii=False))
    elif o.error:
        print(f"error: {o.error}")


def cmd_run(cfg: BackofficeConfig, args: argparse.Namespace) -> int:
    from .runner import Runner

    o = asyncio.run(Runner(cfg).run_job(args.job, logical_date=args.date, prompt_override=args.prompt))
    _print_outcome(o)
    return 0 if o.status == "success" else 1


def cmd_tick(cfg: BackofficeConfig, args: argparse.Namespace) -> int:
    from .runner import Runner
    from .schedule import due_jobs

    tz = ZoneInfo(cfg.timezone)
    ledger = Ledger(cfg.ledger_path)
    schedules = {n: j.schedule for n, j in cfg.jobs.items() if j.schedule and j.enabled}
    last = {}
    for n in schedules:
        t = ledger.last_started(n, trigger="schedule")
        last[n] = t.astimezone(tz) if t else None
    due = due_jobs(schedules, last, datetime.now(tz), timedelta(minutes=args.catchup))
    if not due:
        print("nothing due")
        return 0
    rc = 0
    runner = Runner(cfg)
    for job, slot in due:
        print(f"running {job} (slot {slot:%Y-%m-%d %H:%M})")
        if args.dry_run:
            continue
        o = asyncio.run(runner.run_job(job, trigger="schedule", logical_date=slot.date().isoformat()))
        _print_outcome(o)
        rc |= o.status not in {"success", "skipped", "killed"}
    return rc


# --- approvals / execution -----------------------------------------------------------------


def cmd_approvals(cfg: BackofficeConfig, args: argparse.Namespace) -> int:
    from .approvals import render_action

    ledger = Ledger(cfg.ledger_path)
    ledger.expire_overdue()
    actions = ledger.actions(status=args.status, limit=50)
    if not actions:
        print(f"no actions with status {args.status!r}")
    for a in actions:
        print("\n" + render_action(a))
    return 0


def _decide(cfg: BackofficeConfig, action_id: str, to: str, note: str | None) -> int:
    ledger = Ledger(cfg.ledger_path)
    ledger.expire_overdue()
    try:
        a = ledger.transition(action_id, to, by=f"cli:{getpass.getuser()}", note=note)
    except (IllegalTransition, KeyError) as e:
        print(f"no change: {e}")
        return 1
    print(f"{a.id}: {a.status}")
    return 0


def cmd_approve(cfg: BackofficeConfig, args: argparse.Namespace) -> int:
    rc = _decide(cfg, args.action_id, "approved", args.note)
    if rc == 0 and not args.no_execute:
        return cmd_execute(cfg, args)
    return rc


def cmd_reject(cfg: BackofficeConfig, args: argparse.Namespace) -> int:
    return _decide(cfg, args.action_id, "rejected", args.note)


def cmd_retry(cfg: BackofficeConfig, args: argparse.Namespace) -> int:
    return _decide(cfg, args.action_id, "approved", args.note or "retry")


def cmd_execute(cfg: BackofficeConfig, args: argparse.Namespace) -> int:
    from .executor import execute_approved

    rep = execute_approved(cfg, Ledger(cfg.ledger_path))
    for a in rep.executed:
        print(f"executed {a}")
    for a, e in rep.failed:
        print(f"FAILED   {a}: {e}")
    if not rep.executed and not rep.failed:
        print("nothing approved to execute")
    return 1 if rep.failed else 0


def cmd_telegram(cfg: BackofficeConfig, args: argparse.Namespace) -> int:
    from .approvals import request_pending
    from .approvals.telegram import TelegramChannel
    from .executor import execute_approved

    ledger = Ledger(cfg.ledger_path)
    channel = TelegramChannel.from_config(cfg, ledger)
    request_pending(cfg, ledger)
    channel.serve(on_approved=lambda: execute_approved(cfg, ledger))
    return 0


# --- observability -------------------------------------------------------------------------


def cmd_runs(cfg: BackofficeConfig, args: argparse.Namespace) -> int:
    rows = [
        [
            r["id"],
            r["job"],
            r["status"],
            r["started_at"][5:16].replace("T", " "),
            f"{r['cost_usd']:.3f}",
            r["num_turns"] or "-",
            (r["error"] or "")[:60],
        ]
        for r in Ledger(cfg.ledger_path).runs(limit=args.limit, job=args.job)
    ]
    print(_table(rows, ["run", "job", "status", "started (UTC)", "$", "turns", "error"]))
    return 0


def cmd_show(cfg: BackofficeConfig, args: argparse.Namespace) -> int:
    for e in reversed(Ledger(cfg.ledger_path).events(run_id=args.run_id, limit=1000)):
        detail = json.dumps(e["detail"], ensure_ascii=False)
        print(
            f"{e['ts'][11:19]}  {(e['agent'] or '-'):<16} {e['kind']:<15} {(e['tool'] or ''):<36} "
            f"{detail[:140]}"
        )
    return 0


def cmd_audit(cfg: BackofficeConfig, args: argparse.Namespace) -> int:
    ok, n, msg = Ledger(cfg.ledger_path).verify_audit()
    print(f"{'OK' if ok else 'TAMPERED'}  {n} events checked - {msg}")
    return 0 if ok else 1


def cmd_budget(cfg: BackofficeConfig, args: argparse.Namespace) -> int:
    ledger = Ledger(cfg.ledger_path)
    local = datetime.now(ZoneInfo(cfg.timezone))
    day = local.replace(hour=0, minute=0, second=0, microsecond=0)
    month = day.replace(day=1)
    print(f"today  ${ledger.spend_since(day):.2f} / ${cfg.budgets.daily_usd:.2f}")
    print(f"month  ${ledger.spend_since(month):.2f} / ${cfg.budgets.monthly_usd:.2f}")
    rows = [
        [
            n,
            f"{ledger.spend_since(month, job=n):.2f}",
            f"{j.monthly_budget_usd:.2f}" if j.monthly_budget_usd else "-",
        ]
        for n, j in cfg.jobs.items()
    ]
    print("\n" + _table(rows, ["job", "month $", "job cap $"]))
    return 0


def cmd_kill(cfg: BackofficeConfig, args: argparse.Namespace) -> int:
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    if args.state == "on":
        cfg.kill_switch.write_text(iso(now()))
        print("kill switch ON - no job will start until `backoffice kill off`")
    else:
        cfg.kill_switch.unlink(missing_ok=True)
        print("kill switch off")
    return 0


def cmd_doctor(cfg: BackofficeConfig, args: argparse.Namespace) -> int:
    """Deterministic health checks. No LLM: checking a disk does not need a model."""
    import os

    from .schedule import Cron

    problems, notes = [], []
    if not shutil.which("claude"):
        notes.append("claude CLI not on PATH (the Agent SDK uses its bundled binary; fine if runs work)")
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")):
        notes.append("no ANTHROPIC_API_KEY / CLAUDE_CODE_OAUTH_TOKEN in env (ok for an interactive login)")
    problems += validate(cfg)
    if cfg.kill_switch.exists():
        problems.append("kill switch is ON")
    ledger = Ledger(cfg.ledger_path)
    ok, _, msg = ledger.verify_audit()
    if not ok:
        problems.append(f"audit chain broken: {msg}")
    tz = ZoneInfo(cfg.timezone)
    local_now = datetime.now(tz)
    for name, job in cfg.jobs.items():
        recent = ledger.runs(limit=3, job=name)
        if len(recent) == 3 and all(r["status"] not in {"success", "skipped"} for r in recent):
            problems.append(f"{name}: last 3 runs failed ({recent[0]['error']})")
        if job.schedule and job.enabled:
            slot = Cron(job.schedule).last_before(local_now - timedelta(hours=2))
            last = ledger.last_started(name, trigger="schedule")
            if slot and (last is None or last.astimezone(tz) < slot) and ledger.runs(limit=1):
                problems.append(f"{name}: missed its {slot:%a %H:%M} slot (is `backoffice tick` scheduled?)")
    soon = [
        a
        for a in ledger.actions(status="pending")
        if a.expires_at and datetime.fromisoformat(a.expires_at) - now() < timedelta(hours=6)
    ]
    if soon:
        notes.append(f"{len(soon)} approval(s) expire within 6h: {', '.join(a.id for a in soon)}")
    usage = shutil.disk_usage(cfg.root)
    if usage.free / usage.total < 0.1:
        problems.append(f"disk almost full ({usage.free // 2**30} GiB free)")
    for n in notes:
        print(f"note     {n}")
    for p in problems:
        print(f"PROBLEM  {p}")
    if not problems:
        print("healthy")
    return 1 if problems else 0


def cmd_eval(cfg: BackofficeConfig, args: argparse.Namespace) -> int:
    from .evals import run_evals

    results, out = run_evals(cfg.root, args.case, args.trials)
    print(out.read_text())
    print(f"written to {out.relative_to(cfg.root)}")
    return 0 if all(r.passed for r in results) else 1


def cmd_demo(cfg: BackofficeConfig, args: argparse.Namespace) -> int:
    from .demo import reset_demo

    if cfg.company().get("demo") is not True:
        print(
            "refusing: company/company.yaml is not marked `demo: true`. `demo reset` deletes the "
            "ledger, workspace and company/data - it is only for the demo company."
        )
        return 1

    reset_demo(cfg)
    print("demo data regenerated relative to today; ledger and CRM reset")
    return 0


def cmd_actions(cfg: BackofficeConfig, args: argparse.Namespace) -> int:
    rows = [[k, a.tier, a.handler, a.description] for k, a in sorted(cfg.actions.items())]
    print(_table(rows, ["kind", "tier", "handler", "description"]))
    print(f"\n{Tier.T1}: auto  {Tier.T2}: human approval  {Tier.T3}: always refused")
    return 0


# --- entry point ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="backoffice", description=__doc__)
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name: str, fn, help_: str) -> argparse.ArgumentParser:  # type: ignore[no-untyped-def]
        sp = sub.add_parser(name, help=help_)
        sp.set_defaults(fn=fn)
        return sp

    add("validate", cmd_validate, "check config, agents, Rule of Two, skills, schedules")
    add("agents", cmd_agents, "agent matrix: model, trifecta legs, delegates, write paths")
    add("jobs", cmd_jobs, "jobs with schedule, next slot and last status")
    add("actions", cmd_actions, "action kinds agents may propose, with tiers")
    sp = add("run", cmd_run, "run one job now")
    sp.add_argument("job")
    sp.add_argument("--date", help="logical date (YYYY-MM-DD) for idempotency and prompts")
    sp.add_argument("--prompt", help="override the job prompt (ad-hoc task for that agent)")
    sp = add("tick", cmd_tick, "run every job whose schedule slot is due (call from cron/timer)")
    sp.add_argument("--catchup", type=int, default=90, help="minutes a missed slot stays runnable")
    sp.add_argument("--dry-run", action="store_true")
    sp = add("approvals", cmd_approvals, "list actions (default: pending)")
    sp.add_argument("--status", default="pending")
    for name, fn in (("approve", cmd_approve), ("reject", cmd_reject), ("retry", cmd_retry)):
        sp = add(name, fn, f"{name} an action")
        sp.add_argument("action_id")
        sp.add_argument("--note")
        if name == "approve":
            sp.add_argument("--no-execute", action="store_true", help="approve only")
    add("execute", cmd_execute, "perform approved actions (exactly once)")
    add("telegram", cmd_telegram, "serve Telegram approval buttons (long-running)")
    sp = add("runs", cmd_runs, "recent runs from the ledger")
    sp.add_argument("--job")
    sp.add_argument("--limit", type=int, default=20)
    sp = add("show", cmd_show, "audit trail of one run")
    sp.add_argument("run_id")
    sp = add("audit", cmd_audit, "verify the hash-chained audit trail")
    sp.add_argument("what", choices=["verify"])
    add("budget", cmd_budget, "spend vs. budgets")
    sp = add("kill", cmd_kill, "global kill switch")
    sp.add_argument("state", choices=["on", "off"])
    add("doctor", cmd_doctor, "deterministic health checks")
    sp = add("eval", cmd_eval, "run eval cases against the demo company (costs tokens)")
    sp.add_argument("--case", help="glob over case ids")
    sp.add_argument("--trials", type=int, help="override trials per case (pass^k)")
    sp = add("demo", cmd_demo, "regenerate the demo company's data relative to today")
    sp.add_argument("what", choices=["reset"])
    sp = sub.add_parser("mcp", help="run the backoffice MCP server on stdio")
    sp.set_defaults(fn=None)
    sp = sub.add_parser("hook", help="Claude Code hook entry point")
    sp.add_argument("event", choices=["pre-tool-use", "post-tool-use"])
    sp.set_defaults(fn=None)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s %(name)s: %(message)s"
    )
    if args.cmd == "mcp":
        from .mcp_server import main as mcp_main

        mcp_main()
        return 0
    try:
        cfg = load_config()
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        return 2
    if args.cmd == "hook":
        from .hooks import cli_hook

        return cli_hook(args.event, cfg)
    return int(args.fn(cfg, args) or 0)


if __name__ == "__main__":
    sys.exit(main())
