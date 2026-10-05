# 0003 - Parallel readers, one writer

**Status:** accepted

**Context.** Multi-agent setups pay off when work is parallel and read-heavy (Anthropic's
research system); they fail when several agents make overlapping decisions or edits without
shared context (Cognition's "don't build multi-agents", later refined to "writes stay
single-threaded"). Token cost grows with every agent.

**Decision.** Fan-out is read-only: the chief-of-staff dispatches specialists in parallel with a
tight brief and a length cap, they return findings, and the orchestrator alone writes the
result. A fresh-context reviewer checks drafts before they are proposed. Delegation depth is one.

**Consequences.** One set of numbers per report, one place where contradictions are resolved,
bounded cost. Weekly review is the only job that fans out; most jobs are a single agent.
