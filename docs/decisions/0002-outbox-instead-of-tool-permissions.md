# 0002 - An outbox for side effects instead of in-session permission prompts

**Status:** accepted

**Context.** The Agent SDK can ask a callback (`can_use_tool`) before a tool runs, and a hook can
defer a call. For scheduled jobs this means holding a process open for hours waiting for a
human, or resuming sessions later. The callback is also skipped when an allow rule or a
permissive mode already decided, so it is a weak place to hang a safety guarantee.

**Decision.** Agents have no tool that performs an external effect. They call
`propose_action(kind, payload, justification)`. The action kind's tier decides: T1 executes
after the run, T2 waits for a human (CLI or Telegram), T3 is refused. A separate executor
performs approved actions exactly once.

**Consequences.** No session is alive while effects happen; approvals can take a day. Every
effect has an idempotency key, an approver and a result in the ledger. The human approves a
concrete payload, not a mid-run intention. The cost: agents cannot react to the result of an
effect within the same run - acceptable for back-office work, wrong for a live chat agent.
