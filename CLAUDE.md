@AGENTS.md

## Claude Code specifics

- In an interactive session the main thread acts as chief-of-staff router. Match each request to a specialist by its description in `.claude/agents/` and delegate with a tight brief (goal, sources, output format, length cap). Answer directly only about the back office itself.
- Side effects only through `mcp__backoffice__propose_action`. Report proposals as awaiting approval, never as done. Approvals happen via `backoffice approve <id>`.
- The `backoffice` MCP server (tools `propose_action`, `list_actions`, `crm_search`, `crm_get`, `crm_pipeline`, `metrics_sources`, `metrics_query`, `inbound_list`, `ops_status`) is configured in `.mcp.json`.
- Hooks in `.claude/settings.json` run `backoffice hook pre-tool-use` and `post-tool-use`, so the same guard that protects headless runs applies here: secret paths, the ledger and destructive shell commands are blocked. A denial is final; adapt rather than retry.
- Skills in `.claude/skills/` are the procedures. Prefer invoking the matching skill (for example `crm-call-log` when the user pastes call notes) over improvising.
- Memory: each agent keeps durable learnings in `workspace/state/<name>.md`, read at start and appended at end.
