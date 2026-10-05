# Governance

This page maps the controls in this repo to the expectations people usually mean by "AI governance", and says what they do and do not give you.

**This is not a compliance claim and not legal advice.** The mapping to the EU AI Act is "inspired by" and "maps to", not "satisfies". Whether and how any law applies to your deployment depends on facts this repo cannot know. Ask a lawyer who knows your situation.

## Why this matters for a small team

A back office run by agents does real things with real data: it reads your CRM, drafts text customers will see, and proposes changes to your website and your records. Small teams usually have no compliance function, so the useful governance is the kind that is built into how the system runs:

- you can see what happened (who proposed what, who approved it, what it cost),
- a human decides anything with outside effect,
- the system stops when a limit is reached,
- you can show a customer, an auditor or a new colleague how this works without reconstructing it from chat logs.

The controls below exist because the predecessor of this repo had none of them enforced; see `docs/lessons-from-production.md`.

## What the EU AI Act likely means for a system like this

The EU AI Act (Regulation (EU) 2024/1689) sorts AI systems by risk. For internal business-process agents doing marketing, SEO, CRM hygiene, KPI reporting and ops monitoring, a few points matter:

**Probably not high-risk.** High-risk systems are listed in Article 6 and Annex III: for example biometric identification, critical infrastructure, education and exam scoring, employment and worker management (recruitment, performance evaluation, task allocation based on personal traits), access to essential services such as credit scoring, law enforcement, migration, justice. Marketing, SEO, CRM and KPI work is typically not on that list. Be careful when you extend the system: an agent that screens job applicants, scores employees, or decides who gets credit moves you into a different category, and the controls here would not be enough.

**AI literacy (Article 4).** Providers and deployers must take measures to ensure a sufficient level of AI literacy of the people who operate and use AI systems, taking into account their knowledge, role and context. This has applied since 2 February 2025. It covers you as a deployer even if the system is low-risk. In practice: the people who approve actions and read reports should understand what the agents can and cannot do, what a hallucinated number looks like, and why untrusted text is dangerous. `docs/lessons-from-production.md` and `docs/evals.md` are written partly for that purpose.

**Transparency (Article 50), where applicable.** The Act contains duties about AI systems that interact directly with people, and about AI-generated or manipulated content (for example marking synthetic content, and disclosing AI-generated text published to inform the public on matters of public interest unless a human has editorial responsibility). Who is obliged, and what exactly is required, depends on your role and on how you use the output. In this repo the relevant surfaces are the `content-writer` agent (blog drafts that go through a human-approved pull request) and any message sent through `team.message` or `slack.post`. If you let agents talk to customers, you have to decide how to disclose that.

**Good practice borrowed from high-risk obligations.** Articles 9 to 15 describe what a high-risk provider has to build: risk management, record-keeping, transparency, human oversight, accuracy and robustness. You are not obliged to meet them for a low-risk internal tool. They are still a sensible checklist, and the table below shows where this repo has something comparable.

**Dates.** Application dates for several provisions, in particular the high-risk obligations, were amended by the 2026 "digital omnibus" package. This page does not state those dates. Read the current consolidated text of the Regulation and the amending act before you plan around any date.

**Checking quotes.** If you want to verify what an article actually says, or compare a version of the text, the author's companion project [`eu-ai-act-mcp`](https://github.com/akoemek-dev/eu-ai-act-mcp) lets an agent look up quotes from versioned text of the Act. Use it, or the official text on EUR-Lex, instead of trusting a summary like this one.

## Mapping: controls and related AI Act concepts

| Control in this repo | What it gives you | Related concept (inspired by, not a claim of conformity) |
|---|---|---|
| Hash-chained audit trail: `events` table in `.backoffice/ledger.db`, written by `Ledger.audit`, checked by `backoffice audit verify`; every tool call, denial, proposal, approval and execution is an event | Automatic, ordered records of what the system did, with tamper evidence | Record-keeping and logging (cf. Art. 12) |
| Run ledger: `runs` table with status, model, cost, turns, attempts, degraded sources, result; `backoffice runs`, `backoffice show <run_id>` | Per-run traceability and a basis for post-hoc review | Record-keeping (cf. Art. 12); post-market monitoring ideas |
| Outbox and tiers: T1 auto, T2 human approval, T3 refused (`outbox.py`, `backoffice.yaml` `actions`); approvals expire closed | A human decides every effect visible outside the team; money, legal and deletion are never automated | Human oversight (cf. Art. 14) |
| Approver identity: Telegram approval needs approver ID and chat ID; the approval message shows the real payload; decisions are stored with `decided_by` (Telegram records the user ID; the CLI records `cli:<OS user>`, so give each approver their own account on the host) | Accountability for each approval; no approval based on an agent's summary | Human oversight (cf. Art. 14) |
| Kill switch (`backoffice kill on`, `BACKOFFICE_KILL=1`), checked before every run and before the executor performs any action; budgets (daily, monthly, per job, per run) | A stop button and hard resource limits | Human oversight, ability to intervene or interrupt (cf. Art. 14) |
| Rule of Two (`policy.validate_agents`, `capabilities` in `backoffice.yaml`) and PreToolUse guard (`policy.Guard`): path, shell, domain and delegate allowlists | Identified risk (prompt injection leading to data leaks or unwanted actions) addressed by design; enforced outside the model | Risk management (cf. Art. 9); cybersecurity (cf. Art. 15) |
| Structured run report (`RUN_REPORT_SCHEMA`: status, summary, artifacts, proposed actions, `data_gaps`, `needs_human`); `source-discipline` skill; preflight with degraded mode | Reports say what they are based on and what is missing; failures are visible | Transparency and information for deployers (cf. Art. 13); accuracy (cf. Art. 15) |
| Evals (`evals/cases`, `backoffice eval`): deterministic checks, optional judge, pass^k | Repeatable evidence that behaviour holds after a prompt, skill, model or SDK change, including injection cases | Accuracy and robustness testing (cf. Art. 15); risk management testing (cf. Art. 9) |
| Idempotency keys, compare-and-set state changes, retries that never repeat a success | Fewer silent errors and duplicate effects | Robustness and resilience (cf. Art. 15) |
| Agent definitions, skills and jobs as reviewed files in git; `backoffice validate` | Documented intended purpose, tools and limits per agent; a change history | Technical documentation habits (cf. Art. 11 and Annex IV, as inspiration only) |
| Documentation (`docs/`) and the agent descriptions | Material for staff training on what the agents do | AI literacy (Art. 4) |
| Disclosure of AI involvement in outbound content | Not provided by code. You decide the wording and where it appears | Transparency (Art. 50), where applicable |

What the table does not show: nothing here amounts to a conformity assessment, a quality-management system, a registration, or a risk-management process in the legal sense. It is a set of engineering controls.

## GDPR basics for this system

If you connect a real CRM, personal data flows through the agents. A short list of what is relevant here. This is orientation, not advice.

- **Lawful basis and information duties.** Contact and deal data in your CRM already has a lawful basis and a privacy notice. Processing it with an AI agent is a new processing step; check that your notice and your record of processing activities cover it (Articles 6, 13, 14, 30).
- **Processors and transfers.** Whatever the agents read via tools goes to the model provider as part of the prompt. Review the provider's data processing terms, retention settings and transfer mechanism for the credential type you use (API key under commercial terms versus a subscription login are not necessarily the same). Telegram, if you use it for approvals and notifications, also processes whatever text you send it, including action payloads.
- **Data minimisation (Article 5(1)(c)).** Give agents the least data that does the job: expose tools that return the fields needed, not whole records. The demo tools cap output (for example `crm_search` returns at most 20 matches). `crm-steward` is told not to copy message bodies verbatim into proposals and not to store contact details in its memory file.
- **Audit redaction, and its limits.** `policy.redact` runs on tool inputs and outputs before they enter the audit trail. It does three things: masks values whose key looks sensitive (token, secret, password, api key, authorization, cookie), truncates long strings (400 characters for inputs, 200 for tool results), and caps lists at 20 items. It does not recognise personal data inside values. A `crm_search` query with a person's name, or the first 200 characters of a CRM record, will appear in the audit trail. Proposal payloads in the `actions` table are stored in full, and so are run results. Treat `.backoffice/ledger.db` as a store of personal data.
- **Retention and erasure.** There is no purge command. The audit trail is a hash chain, so deleting or editing old events makes `backoffice audit verify` fail, and a deleted prefix breaks it too. The practical approach is to rotate the whole ledger on a schedule you choose: verify it, archive the file (access-controlled), start a new one. Decide the retention period, write it down, and apply the same to `workspace/reports/`, `workspace/drafts/` and the memory files in `workspace/state/`, which may contain names from CRM data. Erasure requests that touch the ledger need a process you define; the code does not provide one.
- **Solely automated decisions (Article 22).** The outbox means no agent decision with legal or similarly significant effect on a person takes effect without a human decision. Keep it that way: do not add a T1 action that changes a customer's contract or access.
- **Security of processing (Article 32).** Secrets stay out of the repo and out of agent reach (secret globs in `policy.SECRET_GLOBS`, `.env` denied in `.claude/settings.json`), the ledger is outside any agent's write paths, and the shipped deployment files run as an unprivileged user. See `docs/operations.md`.
- **Telemetry.** OTLP export is off unless you set `telemetry.otlp_endpoint`. With `log_tool_details: true`, tool details are sent to your backend as well; treat that backend like the ledger.
- **DPIA.** Whether you need a data protection impact assessment depends on scale and on what data you connect. Ask your data protection officer or counsel before you connect sensitive categories of data.

## What you still have to do yourself

1. Decide who in your team is accountable for the system, and who may approve which kind of action (the `approvals` block in `company/company.yaml` is a place to write this down; the code does not enforce roles beyond the approver ID list).
2. Run an AI literacy session for the people who approve actions and read reports. Cover prompt injection and invented numbers in particular.
3. Decide how you disclose AI involvement in customer-facing text, and apply it in the content workflow and in any message action you enable.
4. Check your role and obligations under the AI Act against the current consolidated text. Re-check when you add a use case.
5. Update your privacy notice and record of processing activities; sign or review data processing terms with the model provider and any messaging provider.
6. Set a retention period for the ledger and for `workspace/`, and put the rotation in your runbook.
7. Give agents read-only credentials for every connected system, and keep write credentials in action handlers only.
8. Run `backoffice audit verify` and `backoffice doctor` regularly, and back up the ledger off the host.
9. Keep your evals current. Add a case whenever you see a failure in production.
10. Re-read the T2 and T3 lists in `backoffice.yaml` whenever you add an action kind, and write the reason for the tier in the commit message.
