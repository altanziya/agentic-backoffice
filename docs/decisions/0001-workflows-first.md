# 0001 - Workflows first, agents inside them

**Status:** accepted

**Context.** Most back-office work recurs on a known schedule with a known shape: a KPI report
on Monday, inbound triage every morning. Letting a long-lived "autonomous" agent decide what
to do next makes cost, timing and failure modes unpredictable.

**Decision.** Plain Python owns *when*, *which agent*, *with which tools* and *within which
limits*. One job is one bounded agent session with a budget, a turn limit and a narrow tool
surface. The model's freedom is inside the job: how to analyse, what to write, what to propose.

**Consequences.** Runs are comparable over time and individually re-runnable; evals can target
a job. Open-ended "go figure out what the company needs" is not a feature - the chief-of-staff
can suggest, a human schedules. Rule of thumb borrowed from Microsoft's Agent Framework docs:
if you can write it as a function, do not make it an agent (e.g. disk and endpoint checks live
in `backoffice doctor`, not in an LLM prompt).
