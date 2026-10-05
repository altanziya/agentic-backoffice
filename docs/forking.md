# Make it yours in an afternoon

This guide takes a fork from "runs the Fieldline demo" to "runs your company's back office, with human approval on everything that leaves the building". Plan on an afternoon for the read-only part (company files, metrics, validation) and a few days of supervised runs before you trust it with anything else.

Read `docs/operations.md` for deployment and `docs/evals.md` for the test setup. This page covers what to change and in what order.

## Before you start

- Start read-only. Reports, briefings and analysis need no outside access beyond your data. Add proposals (PRs, CRM changes, messages) one at a time, later.
- You need an Anthropic credential (API key, or a subscription token from `claude setup-token`) and a place to run it. A laptop is fine for the first days.
- You do not need to connect everything. The CSV and file-based adapters that ship with the repo are enough to get real value from the KPI, SEO and briefing jobs.

## Step 1. Fork and get a baseline

```sh
git clone <your-fork-url> my-backoffice && cd my-backoffice
make setup          # venv, install, regenerate demo data, validate
make test           # offline, spends nothing
```

`make setup` runs `backoffice demo reset`, which only works while `company/company.yaml` says `demo: true`. Delete that line as soon as you put your own data in; from then on the command refuses to run. On the demo it overwrites `company/data/` (metrics, CRM, inbound, search, site), deletes `.backoffice/` and empties the `workspace/` outputs, including `workspace/site`.

Optionally run one demo job to see the loop end to end (this spends tokens, about the cost cap in `backoffice.yaml`):

```sh
.venv/bin/backoffice run kpi-weekly
.venv/bin/backoffice approvals
```

## Step 2. Replace Fieldline with your company

The agents read business context from files. Replace the content, keep the file names.

| File | What goes in it | Read by |
|---|---|---|
| `company/company.yaml` | Name, one-liner, website, stage, team and who owns what, ideal customer, competitors (with domains), news keywords by priority, KPI definitions (name, definition, source, column), approver roles | Most agents, via the `Read` tool |
| `company/brand-voice.md` | How you write, words you use and avoid, examples | `content-writer`, `reviewer` |
| `company/goals.md` | Current objectives and key results, with the KPI names they use | `chief-of-staff`, `kpi-analyst`, `crm-steward` and others, to judge what matters |
| `company/products.md` | Plans, prices, features, integrations: the facts a post or audit is checked against | `content-writer`, `web-maintainer`, `reviewer` |
| `company/content-plan.md` | Next blog topics with keyword, intent and status | `content-writer` |

`company/company.yaml` is read by agents, not parsed by the runtime (except the `demo` flag). Timezone and output language are set in `backoffice.yaml` (`timezone`, `language`).

Then find the remaining references to the demo company:

```sh
grep -rIl -i fieldline --exclude-dir=.venv --exclude-dir=.git --exclude-dir=.backoffice .
```

Expect hits in the agent prompts (`.claude/agents/*.md`), three skills (`competitor-brief`, `news-digest`, `report-format`), `AGENTS.md`, the `name:` in `backoffice.yaml`, the demo data under `company/data/`, `src/backoffice/demo.py` and the eval cases. Change the prompts and skills now. Leave `demo.py` and the demo data for step 3.

Also check these, because they are easy to miss:

- `.claude/agents/intel-reader.md` has the `web_domains` allowlist for web reading. Put your sources and competitor domains there. An empty list means no web access.
- Prompts say "DACH", "trade businesses", "blog". Adjust if your market or channels differ.

## Step 3. Give the agents your numbers

The KPI, SEO and briefing agents never touch an analytics API. They call the `metrics_*` tools of the `backoffice` MCP server, which reads `company/data/metrics/<source>.csv` (one file per source, with a `date` column and numeric columns).

### Option A: CSV export (start here)

1. Delete the demo CSVs in `company/data/metrics/` and `company/data/search/queries.csv`.
2. Write your own, one file per source, for example `web.csv`, `search.csv`, `product.csv`, `revenue.csv`. Daily rows, ISO dates.
3. List how each column aggregates over a window in `company/data/metrics/aggregations.yaml`. The default is `sum`. Use `last` for end-of-day snapshots (MRR, active accounts) and `mean` for rates (bounce rate, average position). Summing a snapshot produces a confident, wrong number, and `metrics_query` reports the aggregation it used.
4. Update the `kpis:` block in `company/company.yaml` so each KPI names its source and column. The agents use these definitions.
5. Keep search query detail in `company/data/search/queries.csv` with the same columns as the demo file, or change the `seo-weekly` skill to match yours.
6. Produce the files from your real systems on a schedule that is not an agent: a small script or an export from your BI tool, run by cron before the briefing. The agents read; they do not export. If a file stops updating, the briefing says the latest row is old, because tool results carry dates.

### Option B: write an adapter

When you want live numbers without a CSV step, implement the `Metrics` interface in `src/backoffice/data.py`: `sources()` returns source names with their columns, `query(source, days, end)` returns the same dictionary shape (`window`, `summary` with `aggregation`, `current`, `previous`, `change_pct`, and `daily`). `build_server` in `src/backoffice/mcp_server.py` constructs it. There is no plug-in registry; you edit the code and add a test. Keep the credentials in the MCP server process, read from environment variables, and use a read-only credential.

Remove or replace the demo files you no longer need (`company/data/inbound`, `company/data/site`) and the `demo` command if you do not want it around. If you delete `demo.py`, the eval harness stops working as shipped (see step 7).

## Step 4. Connect your CRM

Three ways, in order of effort.

**A. File-backed CRM (pilot).** The shipped `CRM` class keeps a SQLite database in `.backoffice/crm.db`, created from `company/data/crm/{contacts,deals,activities}.csv` when the database does not exist. Export your contacts, deals and activities to those columns and start. Be clear about what this is: approved `crm.update` actions change that local database, not your real CRM. It lets you test the read, propose, approve and execute loop on real records. It does not write back to anything. It also means `.backoffice/crm.db` holds copies of customer data.

**B. Your own adapter.** Implement the methods of the `CRM` class (`search`, `contact`, `pipeline`, `update`, `log_activity`) against your CRM's API. Reads are used by the MCP tools in `mcp_server.py`; writes happen only in the `crm.update` handler in `src/backoffice/actions/__init__.py`. Use two credentials: a read-only token for the MCP server process, a separate write token for the handler. Keep the `CRM_WRITABLE` whitelist so a proposal can only change fields you chose. The agents see the tool names only, not the vendor.

**C. A vendor MCP server.** Possible, with three catches:

1. Scheduled runs use `strict_mcp_config=True`: besides `backoffice`, a server from `.mcp.json` is attached only for agents that list it under `backoffice.mcp_servers` in their frontmatter. Add its tools to the agent's `tools` and classify every one of them in `capabilities` (including `no_leg` for reviewed harmless tools); `backoffice validate` fails on unclassified MCP tools.
2. For interactive sessions, add the server to `.mcp.json` and to `enabledMcpjsonServers` in `.claude/settings.json`.
3. The Rule of Two check only knows what you map. `capabilities` in `backoffice.yaml` matches tool names against patterns; an unmapped tool counts as no leg at all. A vendor tool such as `mcp__crm__update_contact` matches none of the shipped `external_effect` patterns (`send`, `post`, `publish`, `delete`), so `validate` would pass an agent that can write to the CRM directly. Map each tool you expose: reads to `private_data`, anything that writes or sends to `external_effect`, anything returning text written by third parties (CRM notes, email bodies) to `untrusted_input`. Then list only the exact tools an agent needs in its `tools:`. Agents are denied any `mcp__` tool not listed there.

Writing through a vendor tool gives up the outbox: the model would perform the effect itself. Prefer B for writes, and keep reads where the vendor tool is the simplest option.

## Step 5. Your website, if agents may propose changes

`site.pull_request` works on a git repository at `workspace/site` (`params.repo` in `backoffice.yaml`). To use it for real:

1. Clone your website repository to `workspace/site`. Note that `backoffice demo reset` replaces that directory; once your clone is there, do not run it.
2. Check that the paths the skills use (`content/blog/<slug>.md`, the files `site-audit` inspects) match your site's structure, and edit the `content-pipeline` and `site-audit` skills and the `web-maintainer` and `content-writer` agents if they do not.
3. The handler creates a branch with the `agent/` prefix, commits the files, and by default stops there (`push: false`). Review a few branches locally first. To open real pull requests, set `push: true` and make `git` and `gh` authenticated for the user that runs the executor. Use a credential that can push branches and open PRs, nothing else, and keep branch protection on `main` so that nothing merges without review. The handler never merges, and `gh pr merge` and `git push` are blocked for agents.

## Step 6. Adjust agents, jobs and actions

Start smaller than the demo. A good first set is `ops-check`, `kpi-weekly` and `daily-briefing`. Disable the rest with `enabled: false` on the job, or delete the entry. `backoffice validate` fails on a job that points at a missing agent, so remove agents only after their jobs.

**Agents.** Each file in `.claude/agents/` has `tools`, a `backoffice:` block with `writes`, `web_domains`, `bash_allow`, `delegates`, and skills. See `AGENTS.md` for the conventions. Principles:

- Minimum tools. Narrowest `writes` globs (always including `workspace/state/<name>.md`). No `Bash` unless you can name every command in `bash_allow`.
- `backoffice agents` prints the matrix of trifecta legs. Read it after every change. `U P E` means untrusted input, private data, external effect; the shipped agents never hold `E`.
- Keep untrusted reading in a quarantined agent without company data, as `intel-reader` does.

**Jobs.** `schedule` is a 5-field cron in the configured timezone. Set effort and `max_budget_usd` per job; set `monthly_budget_usd` on the expensive ones. `requires` lists preflight checks (`file:`, `env:`, `http:`; a trailing `?` makes a source optional so the run degrades instead of failing). `notify: always` sends the run summary every time; the default only reports failures and items needing a human.

**Actions and tiers.** Every side effect is an action kind in `backoffice.yaml` with a tier and a handler.

| Tier | Meaning | Use for |
|---|---|---|
| T1 | Auto-approved, executed after the run, audited | Writes inside your own workspace folders |
| T2 | Waits for a human, expires closed | Anything visible outside the team: PRs, CRM changes, chat messages, webhooks |
| T3 | Refused, never executed | Money, legal commitments, credentials, deletion of customer or company data |

Start at T2 for everything that leaves the workspace. Move a kind to T1 only after weeks of approvals you would have made anyway, and write the reason in the commit message. Do not turn a T3 kind into something else; add a new kind with a narrower scope if you need a limited version, and design its handler to validate its payload and take destinations from `params`.

Available handlers: `file.write`, `github.pull_request`, `crm.update`, `notify.telegram`, `webhook.post`, `refuse`. Adding one means a function in `src/backoffice/actions/__init__.py` with payload validation and a test.

**Approvals and notifications.** `approvals.channel` is `cli` or `telegram`. The CLI is enough for one person. Set `notify.channel` the same way. See `docs/operations.md` for the Telegram service.

**Budgets.** `budgets.daily_usd` and `budgets.monthly_usd` in the shipped config are demo values. Set yours from what a normal week costs, plus margin, after a supervised week.

## Step 7. Validate and run evals

```sh
.venv/bin/backoffice validate     # config, agents, Rule of Two, skills, schedules
.venv/bin/backoffice agents       # trifecta matrix, delegates, write paths
.venv/bin/backoffice jobs         # schedules and next slots
.venv/bin/backoffice actions      # kinds and tiers
make test
```

The eval harness runs jobs on a temporary copy of the repo and, in that copy, calls `reset_demo`, which writes the Fieldline demo data over `company/data/`. Your agents, skills, `company/*.md` and `company.yaml` are used as they are. Two consequences once you have forked:

- The shipped cases assert Fieldline facts (a stale price of 299 from `products.md`, planted issues in the demo site, a planted injection in the demo inbox). After you replace `products.md` they will fail or, worse, pass for the wrong reason.
- The cases stay useful as a template. Keep the demo generator as a fixture source, or replace the fixtures with data shaped like yours, and rewrite the assertions. `docs/evals.md` explains the case format and how to plant fixtures with `setup:`.

Do this before you rely on the system, and re-run `make eval` whenever you change a prompt, a skill, a model or the SDK version. It costs tokens.

## Step 8. Going live

1. **Supervised runs.** Run each job by hand (`backoffice run <job>`), read the report, then read the audit trail (`backoffice show <run_id>`): which tools ran, what was denied, what was proposed. Check every number in the report against its source.
2. **Look at denials.** A denied tool call means the agent definition or a skill asks for something policy forbids. Fix the instruction. Do not widen the policy to make the denial go away.
3. **Approve a week of proposals by hand.** `backoffice approvals`, then `approve` or `reject` with a note. Reject what you would not send yourself.
4. **Schedule it.** Deploy as in `docs/operations.md`. Keep `notify.channel: stdout` or switch to Telegram once the service is up.
5. **Watch cost.** `backoffice budget` daily for the first week.
6. **Write down the rest.** Who approves what (`approvals:` in `company/company.yaml`), who gets the alerts, who rotates tokens. See `docs/governance.md`.

## What not to change unless you know why

| Thing | Why it is there |
|---|---|
| Hard rules in `policy.py`: `BASH_HARD_DENY`, `SECRET_GLOBS`, the denial of the state directory | They block `git push`, `gh pr merge`, `curl`, `rm -rf`, secret files and the ledger. These are the last line against a manipulated session. The hook applies them to interactive sessions too |
| T3 handlers set to `refuse` | Config validation insists on it, and the outbox gives a refused action no way out. Money, legal and deletion stay with humans |
| `strict_mcp_config=True` in `Runner.build_options` | Scheduled runs see only the servers passed in code. Without it, a stray user-level server adds tools you did not review |
| `permission_mode="dontAsk"` with `allowed_tools` | A headless session cannot prompt, so the tool surface is fixed in advance. Switching to a permissive mode removes the allowlist |
| The Rule of Two check and the `capabilities` map | It is the structural answer to prompt injection. Keep the map complete when you add tools |
| Telegram approvals requiring approver ID and chat ID | One without the other is a bypass |
| Approvals expiring closed (`approvals.expire_hours`) | No answer means no |
| Idempotency keys and the retry rules (never retry a success) | They stop duplicate side effects |
| `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=1` | Delegation stays one level deep, which is what the per-agent `delegates` lists and the transitive untrusted-input check assume |
| Writes denied to `.claude/` and `.backoffice/` for agents | Agents must not edit their own instructions, policy or audit trail |
| `.claude/bin/backoffice` failing closed | If the guard cannot run, the call is blocked rather than waved through |
| Giving an agent `Bash` | The shipped agents have none. If you add it, write the narrowest `bash_allow` you can, and expect the Rule of Two to count it as external effect |

## Checklist

- [ ] `company/company.yaml`, `brand-voice.md`, `goals.md`, `products.md`, `content-plan.md` describe your company
- [ ] No remaining "Fieldline" (grep above), no `Europe/Berlin` unless that is your zone
- [ ] `timezone` set in `backoffice.yaml` (and `company.yaml`)
- [ ] `intel-reader` `web_domains` lists your sources
- [ ] Demo data replaced, `demo: true` removed from `company/company.yaml`
- [ ] Metrics CSVs or adapter in place, `aggregations.yaml` correct for snapshots and rates
- [ ] CRM path chosen (A, B or C), credentials read-only for reads
- [ ] Any extra MCP tool mapped in `capabilities`, listed in the right agents' `tools`
- [ ] Jobs trimmed to what you need; budgets set from real cost
- [ ] Action kinds and tiers reviewed; everything leaving the workspace is T2 or T3
- [ ] `backoffice validate` and `make test` pass
- [ ] Eval cases rewritten for your data; `make eval` passes
- [ ] Supervised runs read end to end, audit trails checked
- [ ] Deployed per `docs/operations.md`; kill switch and backups tested
- [ ] Owners named for approvals, alerts and token rotation
