# Build log

How this was actually built. Sources: `STATE.md`'s log, `DECISIONS.md`, `git log`.

## The shape of the work

Three roles, separated so decisions lived in one place and tokens stayed low:

- **Sonnet** did research and content: four agents in parallel on real San Diego permits,
  business licensing, trash and Get It Done, events and general inquiries. Output is
  `research/01`-`04` plus `research/00-synthesis.md`, which fixed the schemas, fee formulas,
  seed data and FAQ text; the KB markdown and seed JSON came from the same synthesis.
- **Fable** planned, decided and reviewed: `PLAN.md`, `DECISIONS.md` (append-only, with
  rejected alternatives), and a devil's-advocate review gate after each milestone.
- **Opus** implemented one milestone at a time against a written spec, with a standing rule:
  no new design decisions. Where a spec was silent, take the simplest reading, write it in
  `STATE.md` under "Decisions needed", and keep moving. There are 28 such entries.

## Commits

```
20:31 init repo with San Diego workflow research   21:35 feat(M1) infra, api, llm client, health
20:35 docs: plan, decisions, assumptions, state    21:36 docs: M1 review accepted
20:36 docs: seed and kb formats                    21:53 feat(M2) rag, tools, router, chat, evals
20:50 docs: eval policy, report do not gate        21:54 docs: M2 review; date-injection decision
22:06 feat(M4) web chat, staff queue, traces       22:13 feat(M3) workflows, intake, certificates
22:16 fix(data) realistic permit fees; M3/M4 review accepted
```

M3 and M4 ran in parallel against a written API contract, on disjoint directories.

## Milestones and what each review changed

**M1: infrastructure.** Compose (Postgres+pgvector, SeaweedFS, API, web), SQL migrations at
startup, models, seed loader, S3, the tiered LLM client with trace hooks, embeddings, `/health`.
24 tests. Review: accepted, no must-fix. Five "spec was silent" decisions stood, including
`BIGSERIAL` keys, hnsw over ivfflat, `{{EMBED_DIM}}` substitution.

**M2: retrieval, tools, routing, chat.** KB ingest, hybrid retrieval with RRF, 11 tools, the
classifier and tier rules, agent profiles, the orchestrator, the traces API, the eval runner.
68 tests, first eval dev 80/80/100/90. Review: accepted, one must-fix carried into M3, because
the eval had caught the model searching September 2023 for "events in September".

**M3: workflows** (state machine, worker, document and form intake, validators, fees,
certificate PDFs, applications API, sample PDFs, `scripts/smoke.sh` 11/11, 100 tests) and
**M4: web** (Next.js chat with uploads, inline form and trace drawer; staff queue; traces page;
build and lint clean). During M3, extraction turned out to fill Part 1 of the business tax form
and null Parts 2 and 3, three runs out of three, because qwen reads the JSON schema as a shape
and the prompt as instructions. The fix was spelling the field list out in prose.

The **M3+M4 review** was accepted with three must-fix items carried into M5: the seeded permit
fees were implausible (a $45,000 remodel quoted $1.80, because the seed modelled the rate as 4
cents per $1,000), the seeded applications sat in automatic statuses so the worker rewrote the
staff queue on every restart, and the LiteLLM gateway had never been run. All three are closed.

**M5: docs and deploy.** This file, the README, the architecture doc, the explainer, the demo
script, `deploy/aws/`, `scripts/reset_demo.sh`.

## The eval policy, and why it is a policy

Written down before any evals existed, because the temptation is obvious: 30 questions is a
small enough set to tune a prompt against, and the resulting number would mean nothing. So the
golden set reports, it does not gate. Nobody edits a prompt, a router rule or a KB file because
a golden item failed; root causes that generalise get fixed and logged in `DECISIONS.md`. Ten
of the thirty are held out and reported separately. Scoring is mechanical (intent, expected
tool, citations present, keyword overlap) with no LLM judge, because a judge built on a 7B
model would be less reliable than the thing it judges. Exactly one change came out of an eval:
injecting today's date into every system prompt, which moved dev keywords 90% to 95%.

## What went wrong

**Docker Desktop's credential helper.** `~/.docker/config.json` sets `credsStore: "desktop"`,
which blocks on the macOS keychain when there is no GUI session, so every `docker pull` and
`docker compose build` from a non-interactive agent shell hung with zero output. Diagnosing it
cost real time, including one Docker Desktop restart. The workaround is a copy of `~/.docker`
with the key removed, used through `DOCKER_CONFIG`. Nothing in the repo depends on it.

**SeaweedFS binds a hostname, not loopback.** Started with `-ip=seaweedfs`, so a healthcheck
probing `localhost:9333` inside its own container fails; the probe uses the service name.

**asyncpg and multi-statement SQL.** Prepared statements cannot hold multiple statements, so
each migration file goes to the raw driver connection instead.

## What took the longest

Research and planning, then getting a small local model to behave. The infrastructure was
straightforward; the time went into places where a 3B or 7B model does something a frontier
model would not: dropping tool calls, filling one section of a form, answering without citation
markers, not knowing the date. Each has a written response in the code, and none is a keyword
patch that would have hidden the behaviour from the evals.

## 2026-09-05 — phase 2

M1-M5 shipped a working assistant on entirely fictional data. Before treating that as done, the
author ran the live stack by hand: twelve probe questions against the running Bedrock deployment,
not the golden set. Real usage found what a fixed eval can't: organics collection alternating
weeks when the real policy is weekly, the model explaining "ISO week parity" to a resident, a
back-reference to a fee it never actually calculated, a referral miss on a row that existed in
the table, and the model inventing an RV-parking permit fee from its own training data because
nothing in the KB covered parking at all. `DECISIONS.md` "Phase 2" records the fixes chosen and
what was rejected (real data everywhere was rejected — no time before Tuesday for CSV ingestion
pipelines for things that don't need it).

Five milestones, specced in `PLAN.md` §12.1 and built on separate branches so the running :8080
demo stack was never disturbed mid-milestone:

- **M6 (data and guardrail fixes).** Organics now read as weekly everywhere the schedule is
  computed or described; the `organics_week` column and seed field stay for backward
  compatibility but nothing reads them. A new `get_holiday_schedule` tool answers holiday
  questions that come with no address. `get_referral` now matches on individual 4+-letter words
  instead of a single substring, so a resident's own phrasing finds the right agency. The shared
  system prompt gained two rules that turned out to matter more than any single tool: never state
  a number or result the model hasn't actually gotten from a tool call in this conversation, and
  never answer from general knowledge of San Diego or California, even hedged as "generally" —
  say so and give the referral or 619-236-5555 instead. That second rule is the reason the
  RV-parking question stopped being a guessing game before there was anywhere else for it to get
  a real answer from.
- **M7 (KB expansion).** `api/kb/parking.md`, `utilities.md` and `housing.md`, researched from
  live sandiego.gov pages, in the same frontmatter-plus-`### Q:` format as the existing KB files,
  retrieved the same unfiltered way as any other `general` question. `kb_chunks` went from 82 to
  120 chunks. Parking, water/sewer billing and short-term rental licensing are no longer things
  the model has to improvise or decline.
- **M8 (hybrid real data and web search) — the largest milestone.** One address resolver
  (`app/live/geocode.py`) now backs every address-taking tool: exact seed match, then the City's
  real ArcGIS geocoder, then a bare ZIP as a last resort, each result carrying a `match` field
  (`seed`/`geocoded`/`zip`) so the honesty story downstream knows which kind of answer it's
  giving. This was root-caused directly from a 2026-09-05 defect: a resident who typed a real,
  unseeded Carmel Valley address got "not found," and a bare ZIP had no path to an answer at all.
  New live lookups in `app/live/arcgis.py` hit the City's actual ArcGIS `MapServer` endpoints for
  council district, street sweeping, zoning and permits on file, each with a 4-second timeout, a
  10-minute in-process cache, and a clean fallback to seed data or a typed error — never a 500.
  `search_events` now merges real council-meeting agendas from the City's Granicus RSS feed
  alongside the seeded calendar. A new `search_city_website` tool (`app/live/search.py`) can
  search `site:sandiego.gov` through a pluggable provider (`SEARCH_PROVIDER=brave|none`) and
  returns fetched-page text as citable sources exactly like RAG hits; with no key configured
  (`none`, the shipped default — the author hadn't decided on a Brave key by end of day) it
  returns a typed "not configured" error rather than failing silently. Every tool result that
  reaches the model now carries `source: "live"` or `source: "seed"`, and the system prompt was
  given the exact sentence to say for each: "according to the City's live map data" or "based on
  demo data" — never blurred together. The nav badge changed from a flat "demo — fictional data"
  to "demo — fictional applications, live City map data," because after M8 that's no longer one
  claim, it's two different ones and both need to be true. Applications, tracking numbers and
  workflows stay entirely fictional; there is no public write API for permits or Get It Done to
  build against.
- **M9 (eval expansion).** The golden set grew from 30 questions to 54 (36 dev / 18 holdout) and
  gained a `category` on every item: `standard` (the original set), `adversarial` (prompt
  injection, unknown addresses and tracking numbers, out-of-scope questions, scored with literal
  `must_contain_any`/`must_not_contain` phrase checks instead of a judge), `multi_turn` (a
  follow-up like "and recycling?" has to resolve against an address given a turn earlier), and
  `multi_intent` (two requests in one message, scored on whether every named tool got called).
  Scoring stayed mechanical on purpose — a judge built on the same tier of model being judged
  would be less reliable than the thing it's judging. One golden item's phrase list was widened
  after the fact (item 33/34, a scorer near-miss on "wasn't able to find" that the reply had
  actually gotten right); `DECISIONS.md` "Phase 2" is explicit that widening an assertion after a
  run is allowed, tuning a prompt to a golden item is not — those are different acts even though
  both touch a number in a report.
- **M10 (act-then-ask), in progress.** The M9 baseline scored multi-intent tool use at 50%:
  several items answered one half of a two-part question and silently dropped the other, or
  stopped mid-turn to ask for an optional detail the tool didn't actually need yet. The spec
  requires auditing each failing item against the actual profile rules first — the service-request
  profile genuinely requires a photo for graffiti and illegal dumping, so an item that expected a
  tool call without one may be the wrong expectation, not the wrong behaviour — before touching
  any prompt. Not yet merged; STATE.md's log has the live numbers as they stand today.

Full 54-item eval on the rebuilt main container, 2026-09-05 13:15 (the number this file and the
demo script both point to): standard n=32 — intent 96.9%, tool 93.8%, citations 100%, keywords
100%, guardrail 100%. Adversarial n=10 — 80/100/100/90/90. Multi-turn n=6 — 100/83.3/100/83.3/100.
Multi-intent n=6 — 100/50/100/100/100, the open M10 problem stated in the numbers rather than
smoothed over. All 54 — 94.4/88.9/100/96.3/98.1, for $1.30. Results file:
`api/evals/results/2026-09-05T18-13-25Z.json`.

The whole phase-2 day — the twelve probes that started it, four milestones' worth of
verification runs, and the full eval above — cost about $5 of real Bedrock spend against a
$10 budget the author set that morning, tracked turn-by-turn against the `traces` table by
`scripts/spend.sh` and logged run-by-run in STATE.md's "Spend ledger."

- **M13b (red-team follow-ups + sweep, 2026-09-05).** Seven findings closed: status tools redacted
  (no applicant fields, no transition log); referral matching stems both sides with a 3-letter floor
  and a function-word stoplist — stemming alone still lost "dog" and left "dog licence" unmatched;
  `rank_referrals` does not re-stem already-stemmed terms ("licens" would grind to "licen"); fee
  estimators became cross-domain read-only tools; `search_city_website` hidden when no provider is
  configured; MarkdownLite renders pipe tables and http(s)-only links; upload filenames sanitised;
  2027 holidays added with year-aware helpers; `evals.run --ids`. Sweep: ten `__init__.py` headers,
  44 docstrings/type hints, two dead web exports removed, no console.log anywhere. `web/` has no unit
  runner, so the MarkdownLite check is a stubbed Playwright spec with zero model spend. 301 tests.
