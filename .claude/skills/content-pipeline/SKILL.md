---
name: content-pipeline
description: Draft the next blog post from the content plan, get a clean-context review, revise, and propose a site pull request. Use for "write the next post", "content pipeline", "draft blog post".
---
# Content pipeline

## Inputs

`company/content-plan.md`, `company/brand-voice.md`, `company/products.md`, `company/goals.md`, `metrics_query source=search` (optional), existing drafts in `workspace/drafts/`.

## Procedure

1. Read the plan; pick the first item not marked done and not already in `workspace/drafts/`. Note slug, working title, target keyword, audience, intent. If the plan is empty or all done, stop with status `ok` and say so.
2. Read voice and product files. List the product facts the post may state (features, prices, limits) before writing.
3. Optionally `metrics_query source=search days=28` for the keyword's current impressions and position; use numbers only if returned.
4. Draft `workspace/drafts/{slug}.md`: front matter (title, description of 150 characters or fewer, date, tags), then body. One promise, concrete trade-business examples, a clear next step for the reader. 800-1200 words unless the plan says otherwise.
5. Delegate to `reviewer`: path of the draft, voice file, product file, list of factual claims to verify, and the instruction to return verdict plus numbered issues.
6. Revise on blocker and major issues using Edit. Re-submit once. After two rounds, stop; list remaining issues in `needs_human` and do not propose the PR.
7. On approve, propose `site.pull_request`: branch `agent/post-{slug}`, title `feat(blog): add post <title>`, body with the reviewer verdict and source of each factual claim, `files` `{"content/blog/{slug}.md": <full text>}`. See `propose-action`.
8. Append the slug and status to your memory file.

## Output

`workspace/drafts/{slug}.md` and one `site.pull_request` action (T2, awaiting approval). Run report: `artifacts` the draft path, `proposed_actions` the PR id, `needs_human` for unresolved issues or facts needing confirmation.

## Quality checks

- Product claims match `company/products.md` exactly; external facts have source links or are removed.
- Voice check against `company/brand-voice.md` passed per reviewer.
- Description length and slug match the front matter and file name.
- You did not publish; the PR text says "proposed".

## Failure handling

Reviewer unavailable: do not propose the PR; report `partial` with the draft path. Missing plan or voice file: status `blocked`, name the file. Never invent customer quotes or statistics.
