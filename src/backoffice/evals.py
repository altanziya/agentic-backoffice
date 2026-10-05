"""Evals: does a job still do the right thing after a prompt, skill, model or SDK change?

A case (`evals/cases/*.yaml`) runs a real job against the demo company in a throwaway copy
of the repo, then scores the *trajectory* (which tools, which denials, which proposals, what
cost) and the *outcome* (report fields, files written, optional LLM-judge rubric).

Deterministic checks come first; the judge is only used where a rule cannot decide (tone,
usefulness). Unattended jobs are scored pass^k: a case passes only if all k trials pass,
because a scheduled job that works 2 out of 3 mornings is a broken job.
"""

from __future__ import annotations

import asyncio
import fnmatch
import json
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from .config import load_config
from .demo import reset_demo
from .ledger import Ledger
from .runner import Runner, RunOutcome

COPY_IGNORE = shutil.ignore_patterns(
    ".git",
    ".venv",
    "venv",
    ".backoffice",
    "__pycache__",
    "*.pyc",
    ".pytest_cache",
    "evals/results",
    "workspace",
    "node_modules",
)


@dataclass
class Trial:
    outcome: RunOutcome
    events: list[dict[str, Any]]
    actions: list[dict[str, Any]]
    root: Path
    judge: dict[str, Any] | None = None

    @property
    def tools_called(self) -> list[str]:
        return [e["tool"] for e in self.events if e["kind"] == "tool_call"]

    @property
    def tools_denied(self) -> list[dict[str, Any]]:
        return [e for e in self.events if e["kind"] == "tool_denied"]

    def files(self, pattern: str) -> list[Path]:
        return sorted(p for p in self.root.glob(pattern) if p.is_file())


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class CaseResult:
    case_id: str
    trials: list[list[CheckResult]] = field(default_factory=list)
    costs: list[float] = field(default_factory=list)

    @property
    def passed(self) -> bool:  # pass^k
        return bool(self.trials) and all(all(c.passed for c in t) for t in self.trials)

    @property
    def pass_rate(self) -> float:
        if not self.trials:
            return 0.0
        return sum(all(c.passed for c in t) for t in self.trials) / len(self.trials)


# --- deterministic checks ------------------------------------------------------------------


def _check(name: str, spec: Any, trial: Trial) -> CheckResult:  # noqa: C901 - flat dispatch
    o = trial.outcome
    report = o.report or {}
    if name == "status":
        return CheckResult(name, o.status == spec, f"run status {o.status!r}")
    if name == "report_status":
        allowed = spec if isinstance(spec, list) else [spec]
        return CheckResult(name, report.get("status") in allowed, f"report status {report.get('status')!r}")
    if name == "max_cost_usd":
        return CheckResult(name, o.cost_usd <= float(spec), f"${o.cost_usd:.3f} (limit ${spec})")
    if name == "max_turns":
        return CheckResult(name, (o.num_turns or 0) <= int(spec), f"{o.num_turns} turns (limit {spec})")
    if name == "tool_called":
        hit = [t for t in trial.tools_called if fnmatch.fnmatchcase(t, spec)]
        return CheckResult(f"{name}:{spec}", bool(hit), f"{len(hit)} call(s)")
    if name == "tool_not_called":
        hit = [t for t in trial.tools_called if fnmatch.fnmatchcase(t, spec)]
        return CheckResult(f"{name}:{spec}", not hit, f"{len(hit)} call(s)")
    if name == "max_denied":
        n = len(trial.tools_denied)
        reasons = "; ".join(
            f"{e['tool']} {json.dumps(e['detail'].get('input'))[:120]} -> {e['detail'].get('reason', '')}"
            for e in trial.tools_denied[:3]
        )
        return CheckResult(name, n <= int(spec), f"{n} denial(s) {reasons}".strip())
    if name == "action_proposed":
        kind, minimum = spec["kind"], int(spec.get("min", 1))
        n = sum(1 for a in trial.actions if fnmatch.fnmatchcase(a["kind"], kind))
        return CheckResult(f"{name}:{kind}", n >= minimum, f"{n} proposed (min {minimum})")
    if name == "no_action":
        kind = spec["kind"] if isinstance(spec, dict) else spec
        n = sum(1 for a in trial.actions if fnmatch.fnmatchcase(a["kind"], kind))
        return CheckResult(f"{name}:{kind}", n == 0, f"{n} proposed")
    if name == "no_action_payload_contains":
        hits = [a["id"] for a in trial.actions if str(spec).lower() in json.dumps(a["payload"]).lower()]
        return CheckResult(f"{name}:{spec}", not hits, f"found in {hits}" if hits else "clean")
    if name == "artifact":
        files = trial.files(spec["glob"])
        if not files:
            return CheckResult(f"{name}:{spec['glob']}", False, "no file written")
        text = files[-1].read_text(encoding="utf-8", errors="replace")
        missing = [s for s in spec.get("contains", []) if s.lower() not in text.lower()]
        forbidden = [s for s in spec.get("not_contains", []) if s.lower() in text.lower()]
        lines = len(text.splitlines())
        too_long = "max_lines" in spec and lines > int(spec["max_lines"])
        ok = not missing and not forbidden and not too_long
        return CheckResult(
            f"{name}:{spec['glob']}",
            ok,
            f"missing={missing} forbidden={forbidden} lines={lines}" if not ok else files[-1].name,
        )
    if name == "data_gaps_mention":
        gaps = " ".join(report.get("data_gaps", [])).lower()
        return CheckResult(
            f"{name}:{spec}", str(spec).lower() in gaps, f"data_gaps={report.get('data_gaps')}"
        )
    if name == "judge":
        j = trial.judge or {}
        score = j.get("score")
        ok = score is not None and score >= int(spec.get("min_score", 4))
        return CheckResult(name, ok, f"score {score}: {j.get('reason', 'no judge result')}"[:300])
    return CheckResult(name, False, f"unknown check {name!r}")


def score(checks: list[dict[str, Any]], trial: Trial) -> list[CheckResult]:
    results = []
    for item in checks:
        ((name, spec),) = item.items()
        results.append(_check(name, spec, trial))
    return results


# --- LLM judge -----------------------------------------------------------------------------

JUDGE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["score", "reason"],
    "properties": {"score": {"type": "integer", "minimum": 1, "maximum": 5}, "reason": {"type": "string"}},
}


async def run_judge(spec: dict[str, Any], trial: Trial, model: str = "sonnet") -> dict[str, Any]:
    from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

    files = trial.files(spec["glob"]) if "glob" in spec else []
    subject = files[-1].read_text(encoding="utf-8") if files else json.dumps(trial.outcome.report)
    prompt = (
        "You are grading the output of an automated business agent. Score 1-5 against the "
        "rubric; 5 = a careful senior teammate would send it as is. Be strict and concrete.\n\n"
        f"<rubric>\n{spec['rubric']}\n</rubric>\n\n<output>\n{subject[:30000]}\n</output>"
    )
    opts = ClaudeAgentOptions(
        model=spec.get("model", model),
        allowed_tools=[],
        permission_mode="dontAsk",
        max_turns=2,
        setting_sources=[],
        output_format={"type": "json_schema", "schema": JUDGE_SCHEMA},
    )
    async for m in query(prompt=prompt, options=opts):
        if isinstance(m, ResultMessage) and isinstance(m.structured_output, dict):
            return m.structured_output
    return {"score": None, "reason": "judge returned no structured result"}


# --- runner ------------------------------------------------------------------------------


def load_cases(cases_dir: Path, only: str | None = None) -> list[dict[str, Any]]:
    cases = []
    for path in sorted(cases_dir.glob("*.yaml")):
        case = yaml.safe_load(path.read_text(encoding="utf-8"))
        case.setdefault("id", path.stem)
        if only is None or fnmatch.fnmatch(case["id"], only):
            cases.append(case)
    return cases


async def run_case(source_root: Path, case: dict[str, Any], trials: int | None = None) -> CaseResult:
    result = CaseResult(case["id"])
    for _ in range(trials or int(case.get("trials", 1))):
        with tempfile.TemporaryDirectory(prefix=f"eval-{case['id']}-") as tmp:
            root = Path(tmp) / "repo"
            shutil.copytree(source_root, root, ignore=COPY_IGNORE)
            cfg = load_config(root)
            reset_demo(cfg)  # same company state for every trial, dated relative to today
            for setup in case.get("setup", []):  # e.g. drop a poisoned fixture in place
                target = root / setup["path"]
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(setup["content"], encoding="utf-8")
            cfg.notify.channel = "stdout"
            cfg.approvals.channel = "cli"
            outcome = await Runner(cfg).run_job(
                case["job"], trigger="eval", prompt_override=case.get("prompt"), post_run=False
            )
            ledger = Ledger(cfg.ledger_path)
            trial = Trial(
                outcome=outcome,
                events=ledger.events(run_id=outcome.run_id, limit=2000),
                actions=[a.__dict__ for a in ledger.actions(limit=500)],
                root=root,
            )
            judge_spec = next((c["judge"] for c in case.get("checks", []) if "judge" in c), None)
            if judge_spec and outcome.status == "success":
                trial.judge = await run_judge(judge_spec, trial)
            result.trials.append(score(case.get("checks", []), trial))
            result.costs.append(outcome.cost_usd)
    return result


def render_markdown(results: list[CaseResult]) -> str:
    lines = ["| case | pass^k | trials passed | cost (avg) | failed checks |", "|---|---|---|---|---|"]
    for r in results:
        failed = sorted({c.name + ": " + c.detail for t in r.trials for c in t if not c.passed})
        avg = sum(r.costs) / len(r.costs) if r.costs else 0
        lines.append(
            f"| {r.case_id} | {'PASS' if r.passed else 'FAIL'} | "
            f"{int(r.pass_rate * len(r.trials))}/{len(r.trials)} | ${avg:.3f} | "
            f"{'<br>'.join(failed)[:400] or '-'} |"
        )
    return "\n".join(lines)


def run_evals(root: Path, only: str | None, trials: int | None) -> tuple[list[CaseResult], Path]:
    cases = load_cases(root / "evals" / "cases", only)
    if not cases:
        raise SystemExit(f"no eval cases matched {only!r}")
    results = [asyncio.run(run_case(root, c, trials)) for c in cases]
    out_dir = root / "evals" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = out_dir / f"{stamp}.md"
    out.write_text(render_markdown(results) + "\n", encoding="utf-8")
    (out_dir / f"{stamp}.json").write_text(
        json.dumps(
            [
                {
                    "case": r.case_id,
                    "passed": r.passed,
                    "pass_rate": r.pass_rate,
                    "costs": r.costs,
                    "trials": [[c.__dict__ for c in t] for t in r.trials],
                }
                for r in results
            ],
            indent=1,
        ),
        encoding="utf-8",
    )
    return results, out
