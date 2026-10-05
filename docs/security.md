# Security model

Agents that read the outside world and hold company data are a prompt-injection target by
construction. The design assumes the model *will* sometimes be steered, and limits what a
steered model can do. Detection ("is this text an injection?") is not relied on: published
defenses of that kind have been broken by adaptive attacks.

## Threats in scope

| Threat | Example | Primary control |
|---|---|---|
| Prompt injection via inbound text | a contact-form "lead" asks the assistant to export customer emails to an outside address | Rule of Two (no agent can both read it and send it out), outbox + human approval, handler-side destinations |
| Injection via web content | a competitor page contains instructions to the reader | quarantined `intel-reader`: no private data, no effects, fixed JSON output |
| Over-broad tool use | an analyst agent runs shell commands or edits config | per-agent allowlists, `dontAsk`, guard on every call |
| Secret exfiltration | an agent reads `.env` or a key file and writes it into a report | guard denies secret paths for every agent and interactively; credentials live outside agent processes |
| Audit tampering | an agent edits the ledger to hide a step | guard denies the state dir; hash-chained events; `backoffice audit verify` |
| Runaway cost / loops | a job recurses through subagents | `max_budget_usd`, `max_turns`, daily/monthly caps, job caps, subagent depth 1, kill switch |
| Duplicate side effects | a retried run proposes the same CRM change twice | idempotency keys; success is never retried |
| Approval spoofing | someone else in the chat presses "Approve" | approver ID **and** chat ID must match; opaque callback data; real payload re-read from the ledger |
| Silent approval by timeout | nobody answers | pending actions expire to `expired`, never to `approved` |

## Rule of Two

Each tool is mapped in `backoffice.yaml → capabilities` to the legs of the "lethal trifecta":
**U** untrusted input, **P** private data, **E** external effect. An agent may hold at most two.
Untrusted input is transitive: if a delegate reads the web, its answer carries that text back.

`backoffice validate` enforces this; `backoffice agents` prints the matrix:

```
agent           model   U/P/E  delegates
chief-of-staff  opus    UP.    kpi-analyst, seo-analyst, crm-steward, reviewer
content-writer  sonnet  .P.    reviewer
crm-steward     sonnet  UP.    -
intel-reader    haiku   U..    -
kpi-analyst     sonnet  .P.    -
market-intel    sonnet  U..    intel-reader
ops-sentinel    haiku   .P.    -
reviewer        sonnet  .P.    -
seo-analyst     sonnet  .P.    -
web-maintainer  sonnet  ...    -
```

No agent holds **E**. External effects exist only as action kinds behind the outbox, which
turns the third leg into a human decision. That is what makes it acceptable for
`crm-steward` to read inbound mail *and* see the CRM.

## Layers of enforcement

1. **Tool surface** - the SDK session runs with `permission_mode="dontAsk"` and an explicit
   `allowed_tools` list; anything else is denied without prompting. `strict_mcp_config=True`
   means only the `backoffice` MCP server is attached - no tools appear because someone added a
   server to `.mcp.json`.
2. **Guard hook** - `PreToolUse` runs before every call, including subagent calls, and resolves
   the *acting* agent from the hook input. It denies: secret paths; the ledger/state dir; writes
   outside the agent's `writes` globs (paths are resolved, so `../` tricks fail); `WebFetch`
   outside `web_domains`; Bash unless allowlisted, and always for destructive or network
   commands, chaining, pipes and redirects; delegation to undeclared subagents; MCP tools not
   in the agent's list. Hook denials apply even in permissive modes and are audited.
3. **Outbox tiers** - T1 auto (own workspace), T2 human approval, T3 refused. The tier belongs
   to the action kind, not to the agent or the prompt.
4. **Handlers** - validate payloads again (an approved payload is still untrusted input), keep
   destinations in config (`url_env`, `repo`, chat ID), refuse path escapes and `.git` writes,
   enforce branch prefixes, never touch the base branch, never merge.
5. **Process boundary for credentials** - API tokens for Telegram, Slack, GitHub and data
   sources are read by the MCP server or the executor, not by the agent session. Run the
   executor and Telegram service with their own environment; give the runner only the Claude
   credential.

## What a successful injection can still do

Being explicit about residual risk:

* **Mislead a report.** A poisoned page or message can push false "facts" into a summary. The
  reviewer pattern, source citations and `data_gaps` reduce this; they do not eliminate it.
* **Shape a proposal.** An injected instruction could make an agent propose a plausible-looking
  T2 action. A human then sees the real payload (not the agent's summary) and decides. Approvers
  need to read payloads; "approve all" habits defeat the design.
* **Waste budget.** Bounded by per-run and daily caps.
* **Search freely.** `WebSearch` is not domain-restricted (only `WebFetch` is). Search returns
  summaries rather than raw pages, which lowers but does not remove exposure.

## Interactive sessions

A human opening Claude Code in the repo gets the hard rules via `.claude/settings.json` command
hooks (secrets, ledger, destructive/network shell) plus Claude Code's own permission prompts.
Per-agent allowlists are not applied interactively because the human is the control. If the
guard binary is missing, the hook fails **closed** (`.claude/bin/backoffice` exits 2).

## Deployment hardening

* Run under a dedicated user; mount only the repo and the `.backoffice` volume.
* Prefer a container or `sandbox-runtime` for the runner; deny outbound network except the
  Claude API and allowlisted domains if your environment supports it.
* Keep `.env` out of the repo (`.gitignore` covers it); prefer the service manager's
  `EnvironmentFile` with `0600` permissions.
* Back up `ledger.db` (`sqlite3 ledger.db ".backup ..."`) - it is your audit trail.

## Verifying it

* `make test` - guard, Rule of Two, outbox, executor and approval rules are unit-tested.
* `make eval CASE='*injection*'` - live runs against planted injections (`evals/cases/`)
  assert that no proposal carries the attacker's address, IBAN, or a T3/outbound kind.
* `backoffice show <run>` - every tool call and denial of a run, in order.

Report security issues privately to the maintainer rather than in a public issue.
