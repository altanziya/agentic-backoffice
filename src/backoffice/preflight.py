"""Preflight: check a job's data sources before spending tokens.

Production lesson: an agent that discovers a dead API halfway through either times out after
20 minutes or quietly reports zeros. Checking first lets a run fail fast (required source
down) or run *degraded* with the gap stated in the prompt, so the report says "source X was
unavailable" instead of inventing a number.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import httpx

from .config import BackofficeConfig


@dataclass
class PreflightResult:
    ok: list[str] = field(default_factory=list)
    degraded: list[str] = field(default_factory=list)  # optional sources that are down
    failed: list[str] = field(default_factory=list)  # required sources that are down

    @property
    def passed(self) -> bool:
        return not self.failed


def _check(cfg: BackofficeConfig, spec: str) -> tuple[bool, str]:
    kind, _, target = spec.partition(":")
    if kind == "env":
        return bool(os.environ.get(target)), f"env var {target}"
    if kind == "file":
        return cfg.path(target).exists(), f"file {target}"
    if kind == "http":
        try:
            r = httpx.head(target, timeout=8, follow_redirects=True)
            return r.status_code < 500, f"{target} (HTTP {r.status_code})"
        except httpx.HTTPError as e:
            return False, f"{target} ({type(e).__name__})"
    return False, f"unknown preflight check {spec!r}"


def run_preflight(cfg: BackofficeConfig, requires: list[str]) -> PreflightResult:
    res = PreflightResult()
    for raw in requires:
        optional = raw.endswith("?")
        ok, label = _check(cfg, raw.rstrip("?"))
        if ok:
            res.ok.append(label)
        elif optional:
            res.degraded.append(label)
        else:
            res.failed.append(label)
    return res
