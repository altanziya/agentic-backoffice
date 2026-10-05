"""Typed configuration: `backoffice.yaml` (system) + `company/company.yaml` (business context).

Everything an operator can change lives in these two files. The code never hardcodes paths,
IDs, schedules or models (lesson from production: hardcoded GA4 IDs and home-directory paths
caused two multi-day outages and made the system impossible to fork).
"""

from __future__ import annotations

import os
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CONFIG_FILENAME = "backoffice.yaml"


class Tier(StrEnum):
    """Risk tiers for side effects. The tier, not the prompt, decides what needs a human."""

    T0 = "T0"  # read-only / analysis. Runs unattended.
    T1 = "T1"  # writes to our own workspace (reports, drafts). Auto-approved, still audited.
    T2 = "T2"  # visible outside the team (PR, CRM write, message, publish). Human approval.
    T3 = "T3"  # money, legal, credentials, deletion. Never automated; proposals are refused.


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BudgetConfig(_Strict):
    daily_usd: float = 10.0
    monthly_usd: float = 150.0


class TelegramConfig(_Strict):
    bot_token_env: str = "TELEGRAM_BOT_TOKEN"
    chat_id_env: str = "TELEGRAM_CHAT_ID"
    # Comma-separated Telegram user IDs allowed to approve. Checked together with the chat ID
    # (AND, not OR - the original system accepted either, which is one ID away from a bypass).
    approver_ids_env: str = "TELEGRAM_APPROVER_IDS"


class ApprovalConfig(_Strict):
    channel: Literal["cli", "telegram"] = "cli"
    expire_hours: float = 48.0
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)


class NotifyConfig(_Strict):
    channel: Literal["stdout", "telegram"] = "stdout"


class TelemetryConfig(_Strict):
    otlp_endpoint: str | None = None
    service_name: str = "agentic-backoffice"
    log_tool_details: bool = False


class ActionConfig(_Strict):
    """A kind of side effect an agent may *propose*. Agents never execute these themselves."""

    tier: Tier
    handler: str
    description: str = ""
    params: dict[str, Any] = Field(default_factory=dict)


class CapabilityMap(_Strict):
    """Maps tool-name patterns to the three legs of the 'lethal trifecta' (Rule of Two).

    `backoffice validate` refuses any agent whose tools cover all three legs.
    Patterns use fnmatch syntax against the tool name (e.g. `mcp__backoffice__crm_*`).
    """

    untrusted_input: list[str] = Field(default_factory=list)
    private_data: list[str] = Field(default_factory=list)
    external_effect: list[str] = Field(default_factory=list)
    # Tools reviewed and found to hold none of the legs. Every MCP tool an agent uses must
    # match one of the four lists, so a newly attached vendor tool cannot slip through
    # `validate` unclassified.
    no_leg: list[str] = Field(default_factory=list)


class JobConfig(_Strict):
    agent: str
    prompt: str
    description: str = ""
    schedule: str | None = None  # 5-field cron, interpreted in `timezone`
    model: str | None = None  # overrides the agent's model
    effort: Literal["low", "medium", "high", "xhigh", "max"] | None = None
    max_turns: int | None = None
    max_budget_usd: float | None = None
    monthly_budget_usd: float | None = None
    timeout_minutes: int | None = None
    retries: int | None = None
    # Preflight checks: `env:NAME`, `file:path`, `http:https://...`. Missing optional
    # sources (suffix `?`) degrade the run instead of failing it.
    requires: list[str] = Field(default_factory=list)
    # "always": send the run summary to the notify channel (e.g. the daily briefing).
    # "failure": only failed / blocked runs and items that need a human.
    notify: Literal["always", "failure"] = "failure"
    enabled: bool = True

    @field_validator("schedule")
    @classmethod
    def _cron_has_five_fields(cls, v: str | None) -> str | None:
        if v is not None and len(v.split()) != 5:
            raise ValueError(f"schedule must be a 5-field cron expression, got {v!r}")
        return v


class Defaults(_Strict):
    model: str = "sonnet"
    effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    max_turns: int = 30
    max_budget_usd: float = 1.0
    timeout_minutes: int = 20
    retries: int = 1


class Paths(_Strict):
    workspace: str = "workspace"
    state_dir: str = ".backoffice"
    agents_dir: str = ".claude/agents"
    company_dir: str = "company"


class BackofficeConfig(_Strict):
    name: str = "agentic-backoffice"
    timezone: str = "UTC"
    # Output language for reports and messages. Stated explicitly in every run: without it,
    # a user-level CLAUDE.md on the host can silently switch the language of a run.
    language: str = "English"
    company_file: str = "company/company.yaml"
    paths: Paths = Field(default_factory=Paths)
    defaults: Defaults = Field(default_factory=Defaults)
    budgets: BudgetConfig = Field(default_factory=BudgetConfig)
    approvals: ApprovalConfig = Field(default_factory=ApprovalConfig)
    notify: NotifyConfig = Field(default_factory=NotifyConfig)
    telemetry: TelemetryConfig = Field(default_factory=TelemetryConfig)
    capabilities: CapabilityMap = Field(default_factory=CapabilityMap)
    actions: dict[str, ActionConfig] = Field(default_factory=dict)
    jobs: dict[str, JobConfig] = Field(default_factory=dict)

    # Set by `load_config`, not by the YAML file.
    root: Path = Field(default=Path("."), exclude=True)

    @model_validator(mode="after")
    def _t3_actions_have_no_handler_execution(self) -> BackofficeConfig:
        for name, action in self.actions.items():
            if action.tier == Tier.T3 and action.handler != "refuse":
                raise ValueError(f"action {name!r} is T3; its handler must be 'refuse'")
        return self

    # --- resolved paths -------------------------------------------------------------------
    def path(self, rel: str) -> Path:
        p = Path(rel)
        return p if p.is_absolute() else (self.root / p)

    @property
    def workspace(self) -> Path:
        return self.path(self.paths.workspace)

    @property
    def state_dir(self) -> Path:
        return self.path(self.paths.state_dir)

    @property
    def ledger_path(self) -> Path:
        return self.state_dir / "ledger.db"

    @property
    def kill_switch(self) -> Path:
        return self.state_dir / "KILL"

    def job(self, name: str) -> JobConfig:
        try:
            return self.jobs[name]
        except KeyError:
            known = ", ".join(sorted(self.jobs)) or "(none)"
            raise KeyError(f"unknown job {name!r}; known jobs: {known}") from None

    def company(self) -> dict[str, Any]:
        path = self.path(self.company_file)
        if not path.exists():
            return {}
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def find_root(start: Path | None = None) -> Path:
    """Walk up from `start` (or $BACKOFFICE_ROOT, or cwd) to the directory holding backoffice.yaml."""
    env_root = os.environ.get("BACKOFFICE_ROOT")
    if start is None and env_root:
        return Path(env_root).resolve()
    here = (start or Path.cwd()).resolve()
    for candidate in [here, *here.parents]:
        if (candidate / CONFIG_FILENAME).exists():
            return candidate
    raise FileNotFoundError(
        f"no {CONFIG_FILENAME} found in {here} or its parents; run from your back-office repo "
        "or set BACKOFFICE_ROOT"
    )


def load_config(root: Path | None = None) -> BackofficeConfig:
    root = find_root(root)
    raw = yaml.safe_load((root / CONFIG_FILENAME).read_text(encoding="utf-8")) or {}
    cfg = BackofficeConfig.model_validate(raw)
    cfg.root = root
    return cfg
