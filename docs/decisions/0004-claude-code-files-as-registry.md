# 0004 - Claude Code files are the agent registry

**Status:** accepted

**Context.** Keeping agent prompts in one place for interactive use and in another for the
scheduler leads to drift (the predecessor system had prompts, a JSON registry and a crontab
that disagreed).

**Decision.** `.claude/agents/<name>.md` is the single definition: Claude Code reads its
frontmatter natively; runtime-only settings (write paths, web domains, shell allowlist,
delegates) sit in a `backoffice:` block that Claude Code ignores. Skills live in
`.claude/skills/`. The runner loads the same files with `setting_sources=["project"]` and passes
delegates as SDK `AgentDefinition`s.

**Consequences.** Opening the repo in Claude Code gives you the same agents the scheduler runs.
The registry is validated (`backoffice validate`) for name/file match, unknown delegates,
missing skills and Rule-of-Two violations.
