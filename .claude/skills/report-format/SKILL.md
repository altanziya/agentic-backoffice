---
name: report-format
description: House style for every report Fieldline's agents write - title, as-of line, TL;DR, sections, sources, data gaps. Use whenever writing a briefing, digest, review, audit or any markdown report.
---
# Report format

Readers are founders with five minutes. The format puts the answer first and the evidence after.

## Layout

```markdown
# <Report name> - <period or date>

As of: <YYYY-MM-DD HH:MM> <timezone from backoffice.yaml> | Period: <YYYY-MM-DD to YYYY-MM-DD> | Author: <agent>

## TL;DR
- <max 5 bullets; each a finding or a decision needed, with the number>

## <Section>
<findings; tables for numbers>

## Recommendations
1. <one action, owner-sized, with reason> 

## Sources
- `metrics_query source=web days=28` (run 2026-10-05)
- `workspace/reports/seo/2026-09-28-seo-weekly.md`

## Data gaps
- <source, what is missing, effect on the report> (write "None" if none)
```

## Style

- Lead with what changed or what needs a decision. Context goes below.
- Numbers go in tables with columns: metric, current, previous, delta, source. Units in the header, not repeated per cell. Delta shows absolute and percent.
- Short sentences, active voice, plain words. No filler openers ("In today's fast-moving..."), no hype, no emojis.
- One idea per bullet. A bullet longer than two lines belongs in a section.
- Recommendations are concrete and limited (at most five). If there is nothing to do, say "No action needed" rather than inventing one.
- Hypotheses are labelled "Hypothesis:". Opinions are labelled as such.
- Respect length caps from the brief or job. A daily briefing fits one screen; a weekly review is at most two pages.

## File naming

`workspace/reports/<area>/{date}-<name>.md` with ISO dates, for example `workspace/reports/kpi/2026-10-05-kpi-weekly.md`. Write the file once complete; do not leave partial reports. Use the area directory your agent is allowed to write to.

## Check before finishing

- TL;DR matches the body (same numbers).
- Every table row has a source; every source listed is used.
- Data gaps section present, even if "None".
