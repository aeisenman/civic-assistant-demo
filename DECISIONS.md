# DECISIONS.md — why things are the way they are

Append-only. Newest at the bottom. Each entry: date, decision, why, alternatives rejected. Read this file first.

## 2026-09-02

- **Fake city = San Diego, workflows modeled on the real ones.** Research agents (Sonnet) pulled DSD permits, Treasurer business tax, ESD trash, Get It Done, events, and general inquiries into `research/`. Why: realistic forms and status vocab make the demo credible. Rejected: inventing a generic city (less convincing).
- **LLM client speaks the OpenAI protocol.** `openai` SDK with `base_url` + per-tier model names from env. Why: user wants to swap keys/providers without code changes; Ollama, OpenAI, and (via LiteLLM) Bedrock all speak it. Rejected: Anthropic SDK direct (no key on this machine; less swappable), Bedrock's own OpenAI-compatible endpoint (tested: only exposes Haiku and rejects chat completions for Anthropic models).
- **Dev provider = Ollama** (`qwen2.5:3b` small, `qwen2.5:7b` smart, `nomic-embed-text` embeddings). Tested: chat, JSON-schema output, and tool calling all work through `/v1`. Why: zero cost overnight, no key management. Cost: weaker answers than Sonnet; swap before the demo if needed.
- **Three logical model tiers, not three hard-coded models.** small (classify/extract), smart (answer), escalate (hard turns). Why: the core design question is "how do you route"; the answer is rules in `llm/router.py` plus a config table, visible in every trace.
- **RAG for policy text, tools for records.** Trash schedules, permit status, events, fees are SQL lookups via function calling; FAQ/policy markdown is retrieved via pgvector + full-text with RRF. Why: retrieval over tabular facts is the classic RAG failure; tools are exact and auditable.
- **Chat is the intake channel.** Residents upload a PDF or fill an inline form inside the chat; the assistant extracts, asks for gaps, files it, returns a tracking number. Why: one story shows Q&A and workflow together; matches how residents actually behave. Rejected: separate upload portal (two UIs to explain).
- **Workflow engine = state machine in Postgres + in-process worker.** Why: explainable in 30 seconds; no Celery/Temporal/Redis. Rejected: Temporal (great, but a demo-killer to explain), Vercel Workflow (not hosting there).
- **SeaweedFS for documents, Postgres+pgvector for everything else.** Why: requested; S3 API means AWS S3 is a one-line swap. MinIO would have been equivalent.
- **Plain SQL migrations applied at startup** instead of Alembic. Why: fewer concepts for a demo.
- **Staff dashboard kept small.** Product is resident-facing; the staff page exists only to show the workflow advancing and to press "approve". 
- **Ports moved off defaults** (3001/8080/5433/8333) because 3000/8000/5432 are occupied by other projects on the dev Mac.
- **Fable plans and reviews, Opus implements, Sonnet researches and writes content.** Why: user instruction; keeps decisions in one place and tokens down.
- **Evals report, they do not gate, and nobody tunes to them.** Local qwen is weak; a pass/fail threshold would invite overfitting prompts to 30 questions. Mechanical scoring only, 10-question held-out split, and the interesting number is the delta across providers. (User request.)

## 2026-09-02 (M1 implementation)

- **hnsw, not ivfflat, for `kb_chunks.embedding`.** The index is created by the startup
  migration against an empty table; ivfflat needs data to train its lists and would have to be
  rebuilt after ingest. Cost: slightly slower build, more memory — irrelevant at demo scale.
- **`BIGSERIAL` primary keys.** Tracking numbers are the human-facing identifier; internal ids
  only need to be short and readable in logs. Rejected: UUIDs (noisier, no benefit without
  distributed writes).
- **Vector width is substituted into the SQL at migration time** (`vector({{EMBED_DIM}})`)
  rather than fixed at 768, so switching to an OpenAI or Titan embedding model is an env change
  plus a fresh DB. Rejected: hard-coding 768 (locks the provider swap the whole plan is about).
- **`chat()`/`embed()` accept an injected `AsyncOpenAI`.** One argument makes the whole LLM
  layer testable through `httpx.MockTransport` with no network and no fixture server.
  Rejected: monkeypatching module globals in tests (silently rots when the client is refactored).
- **Health reports per component instead of failing.** A demo where one box is red is more
  useful than a 500 that says nothing about which dependency died.

## 2026-09-03 (M2 implementation)

- **RRF over hybrid retrieval, with the fusion in a pure function.** `rag/retrieve.py` runs a
  pgvector cosine top-8 and a `ts_rank_cd` top-8, then fuses with reciprocal rank fusion (k=60).
  Why: dense search finds paraphrases, full-text pins exact strings like "SB-1186", and RRF needs
  no score calibration between two scales that are not comparable. `rrf()` takes rank lists and
  returns ordered ids, so the ranking logic is unit-tested without a database. Rejected: weighted
  score blending (needs tuning per corpus), dense-only (misses fee codes and form numbers).
- **A topic filter that returns fewer than 2 hits is dropped and the search rerun.** Why: a wrong
  intent should degrade to a slightly off-topic source, not to no sources at all.
- **The topic filter is spliced into the SQL string, not bound.** `(:topic::text IS NULL OR ...)`
  is a syntax error once asyncpg renumbers the parameters inside `text()`. Building `AND d.topic =
  :topic` only when a topic exists is shorter than fighting the cast, and the value stays bound.
- **The only non-model routing shortcut is the tracking-number regex.** `\b(PRM|BTC|SR)-\d{4}-\d{6}\b`
  sets the intent from the prefix at confidence 1.0 before any model call, because the prefix
  literally *is* the domain. Everything else goes to the SMALL model. Why: PLAN.md §14 — keyword
  heuristics would paper over what the classifier actually does, and the evals exist to measure it.
- **Tool errors are values, not exceptions.** `dispatch()` returns `{"error": ..., "summary": ...}`
  for an unknown tool, invalid arguments, or a failure inside the tool. Why: a 3B model that drops
  a required field should get a readable message and another turn; the resident should never see a
  500. The same reasoning wraps the whole turn in `agents/chat.py`.
- **Every tool result carries a `summary` string.** Why: a weak model quotes a sentence far more
  reliably than it re-renders a nested JSON object, and the summary is also what the trace shows.
- **Citations fall back to the top 2 hits, flagged `implicit: true`.** Why: qwen often answers
  from the sources without writing `[1]`. Showing the passages it was given, labelled as inferred,
  is more honest than showing none. Rejected: forcing citations with a retry (costs a call and
  teaches the model nothing).
- **`create_service_request` writes through `workflows/store.create_application`.** Why: M3 swaps
  that one function for the workflow engine without touching the tool or the chat loop.
- **`GET /api/forms/{type}` returns a static dict in M2.** Why: the web app needs the contract now;
  M3 replaces `FORM_SCHEMAS` with schemas derived from the pydantic models so extraction,
  validation and rendering share one definition. The field names already come from synthesis §1.
- **The assistant is told today's date at request time.** M2 eval showed the model searching September 2023 for "events in September". Fix: a dynamic `Today is <weekday>, <date>` line appended to the system prompt in the orchestrator (after the static preamble, so prompt-caching prefixes stay stable on providers that cache). This is a root-cause fix that generalizes, allowed under the eval policy in PLAN.md §14. Not fixed: the 3B classifier's confusions between `general` and `service_request`; that is the provider's weakness and the number we show honestly.
- **M3 and M4 run in parallel.** Web builds against a written API contract; the two agents own disjoint directories and rebase before pushing.

## M3 — workflow engine, intake, certificates (Opus)
- **One status spine for all three application types.** `draft → submitted → validating →
  needs_info|routed → in_review → approved|rejected → issued → closed`. Why: the research gives
  three different vocabularies (DSD plan-check, Treasurer, Get It Done) but the same shape; one
  table is explainable in a sentence and the staff queue needs one set of buttons. Rejected: a
  transition table per type — three times the code for cosmetic differences.
- **The engine is the only writer of `applications.status`.** `advance()` validates the
  transition, writes an `application_events` row and runs the entry hook, so the audit timeline
  is a byproduct rather than a thing anyone can forget. The API returns 409 on an illegal jump.
- **Side effects live in `ON_ENTER`, keyed by the status being entered.** `validating` runs the
  validator and immediately routes; `issued` renders the certificate. Why: "what happens when an
  application becomes X" is one lookup, and the worker never has to know about either.
- **The worker is one asyncio task in the API process, polling every 3s.** Why: PLAN.md forbids
  Celery/Redis, and a 3-second poll is invisible in a demo. `WORKER_ENABLED=false` turns it off
  so the staff page can step an application by hand.
- **Document intake validates synchronously, then hands back to the worker.** The chat reply has
  to say "I still need X" in the same turn, so `intake_turn` runs `submitted → validating`
  itself; everything after that is the worker's. Rejected: making the resident poll.
- **Workflow replies are templated, not generated.** A tracking number, a fee and a missing-field
  list are facts the engine already knows; letting a 7B model paraphrase them adds latency and a
  chance of a wrong number, with no upside. Only the *extraction* is a model call.
- **Seed applications were rewritten to the `workflows/schemas.py` field names.** PLAN.md §13
  makes the pydantic models the single definition of a form; the M1 seed used the research §1
  names, so the validator would have called every fixture incomplete. Rejected: aliasing old
  names in the validator — two vocabularies is exactly what the single-definition rule forbids.
- **The extraction prompt repeats the field list in prose.** qwen2.5:7b-32k treats the JSON
  schema as a shape to fill and the prompt as the instructions: without the checklist it filled
  Part 1 of the business tax form and nulled Parts 2–3 (3/3 runs). Generalizes to any small
  model; no golden eval item exercises document intake, so this is not eval tuning.
- **Permit fee seed numbers corrected by Fable.** The synthesized `per_1000_valuation_cents` values were literally a few cents, so a $45k remodel quoted $1.80. Set Building-with-Plans to $250 + $12.50/$1k, Tenant Improvement $200 + $10/$1k, Grading $150 + $8/$1k, ADU flat $3,500. Still labeled estimates; the point is plausible magnitude, not accuracy.
- **Seeded applications sit only in manual states** (needs_info, in_review, approved, issued, rejected, closed) so the worker does not rewrite the staff queue on every restart. Fresh submissions from the chat are the ones that move automatically.

## M5 — docs, deploy, cleanup (Opus)
- **Seeded applications now sit only in the six manual statuses.** PRM-2026-000101 became
  `rejected`, BTC-2026-000202 and SR-2026-000302 became `in_review`. The worker auto-advances
  `submitted`, `validating` and `routed`, so any fixture in one of those was rewritten on every
  restart and the staff queue never looked the same twice. The eight fixtures now cover
  needs_info, in_review, approved, issued, rejected and closed, and the worker leaves them alone.
- **The LiteLLM gateway lives behind a compose profile, not a comment.** `docker compose up -d`
  ignores `profiles: ["aws"]`, so the default path is unchanged, and
  `docker compose --profile aws up -d` brings the gateway up. A commented-out service cannot be
  tested; a profiled one can, and was.
- **The gateway was exercised against real Bedrock once.** All five aliases (`small`, `smart`,
  `escalate`, `extract`, `embed`) answered from us-west-2; Titan returned 1024 dimensions. That
  turns "the provider is an env swap" from a claim into a tested statement. `.env` stays on
  Ollama; the container was stopped afterwards.
- **`extract` is its own LiteLLM alias** pointing at the same Haiku as `small`, rather than
  reusing the `small` name. The tier can then be repointed at a long-context model without an
  application change, which is the whole point of tiers being roles.
- **The EC2 instance role is scoped to inference, not `AmazonBedrockFullAccess`.** One inline
  policy allowing `bedrock:InvokeModel*` and `bedrock:Converse*`. The managed policy also grants
  model management and provisioned throughput, which a demo box has no reason to hold.
- **`down.sh` terminates the instance and deletes the security group but keeps the IAM role.**
  The role costs nothing and re-creating it costs a propagation wait on every `up.sh`. The script
  prints the four commands to remove it by hand.
- **`reset_demo.sh` does not rebuild images by default.** A reset is normally about wiping data,
  and a rebuild is the slow part. Because the api Dockerfile copies `seed_data/` and `kb/` into
  the image, editing either needs `--build`; the script header says so, and this was found the
  hard way while verifying the seed-status change.

## 2026-09-03

- **Bedrock is the live provider; Nova Lite does extraction.** Tested five cheap Bedrock models on the real sample PDF: Nova Micro, Nova Lite, Nova 2 Lite, Llama 4 Scout and Haiku 4.5 all extracted 13/13 fields in ≤1.6s. Chose Amazon Nova Lite for the extract tier: 300k context and roughly $0.06/$0.24 per million tokens, the cheapest usable long window on the account. Small tier stays Haiku 4.5 because intent classification drives routing accuracy and Haiku is still cheap per call. Smart = Sonnet 4.6, escalate = Opus 4.6 (Sonnet 5 / Opus 5 need an AWS sales enablement). Ollama profile kept for offline dev.
- **Frontend gets Playwright end-to-end tests and a design pass.** User asked for proof that buttons work and a modern, professional look; screenshots are reviewed by Fable.

## Bedrock go-live (Opus, 2026-09-03)

- **`chat_json` degrades from `json_schema` to `json_object` per model, and remembers.** Bedrock
  validates the JSON Schema before it runs the model, and its Anthropic models reject
  `minimum`/`maximum` on a `number` — which is exactly what pydantic emits for the classifier's
  `confidence: float = Field(ge=0, le=1)`. Every routed turn 400'd. On a 400 whose message names
  the response format, `chat_json` now retries once with `{"type": "json_object"}` and the schema
  pasted into the system prompt, and adds the model to a module-level set so later calls skip the
  wasted 400. Nova Lite accepts `json_schema` natively and is never downgraded, so document
  extraction keeps the stronger constraint. Rejected: deleting the `ge`/`le` bounds from
  `Classification` (a real invariant, and it would silently accept `confidence: 7`); rejected:
  sanitising every schema before sending (guessing which keywords a provider dislikes is a
  maintenance treadmill — reacting to the provider's own error is honest and self-correcting).
- **The fallback strips a markdown fence.** `json_object` is an instruction, not a grammar, on
  Bedrock's Anthropic models: they answer with valid JSON inside a ```json block. `_unfence()`
  removes it before validation. Without it the fallback failed both attempts and the fix would
  have looked like it did not work.
- **Amazon Nova Lite does document extraction; the other three tiers are Claude.** Extraction is
  long-context, high-volume and low-judgement, and Nova Lite is $0.06/$0.24 per 1M against
  Haiku's $1.00/$5.00 with a 300k window. It filled 12 of the sample business tax form's fields on
  the live run. The small tier stays Haiku 4.5 because intent classification is what drives
  routing accuracy, and that is the number the evals measure.
- **`.env.bedrock` sets `COMPOSE_PROFILES=aws`.** The provider swap is now genuinely one `cp`:
  no `--profile` flag to remember, no second command. The Ollama profile is unchanged because it
  simply does not set the variable.
- **`api` depends on `litellm` with `required: false`.** The API embeds the entire knowledge base
  during startup, so it cannot come up before the gateway; but the Ollama profile has no gateway.
  `required: false` is the one compose construct that means "wait for it if it is here". Rejected:
  a startup retry loop in `main.py` — that is application code paying for a compose ordering
  problem, and it would hide a genuinely dead gateway behind a slow boot.
- **The trace records the tier alias (`small`, `extract`, ...), not the Bedrock model id.** That is
  what `LLM_PRICES_JSON` is keyed by, so `estimate_cost` works without a second lookup table, and
  the underlying ids live one file away in `deploy/aws/litellm.yaml`. Rejected: threading a
  `provider_model` through `LLMResult`, the trace row and the price table — three files and a
  config type change to show something the config already says.

## Web design pass + Playwright e2e (Opus)
- **One navy, one amber, and slate for everything else.** `app/globals.css` defines the whole
  system as Tailwind v4 `@theme` tokens: `--color-primary` `#0f2f4f` (nav, primary buttons,
  resident bubbles), `--color-accent` `#d97706` used only for the seal, focus rings and the active
  nav underline, slate neutrals, white cards on a slate-50 page. Why: a projected demo needs one
  obvious hierarchy, and two hues plus a neutral scale is the smallest system that gives it.
  Rejected: adding a UI library — it would be the largest dependency in the repo and the author
  has to be able to explain every file.
- **Four type steps, named, not ad-hoc.** `text-title` 24 / `text-section` 16 / `text-body` 15 /
  `text-meta` 13, defined once as `--text-*` tokens. Why: the previous pages mixed `text-xl`,
  `text-sm` and `text-xs` per component, which is how a prototype looks like a prototype.
- **The chat column is a fixed-height flex column with its own scroll**, not a page that scrolls
  under a `sticky` composer. Why: the sticky composer overlapped the conversation whenever the
  page was taller than the viewport (visible in the first screenshot run). A chat pane that owns
  its scroll is also what every resident already recognises.
- **Status pills map one hue per meaning**, not one per status: amber = waiting on the resident
  (`needs_info`), blue = a human has it (`in_review`), green = done (`approved`/`issued`), red =
  refused, gray = inert, indigo = still in the automated pipeline. Why: a staff member scans the
  queue by colour before reading a word.
- **`MarkdownLite` grew bold, inline code and lists.** The model writes `**Regular schedule:**` and
  `- ` bullets on almost every answer and the old renderer printed the asterisks. Still no
  markdown library and still no `dangerouslySetInnerHTML`: a small regex over bold/code spans plus
  block-level list detection covers what the model actually emits. The `/traces` page deliberately
  shows the raw reply — that is a debugging view.
- **The staff detail is a slide-in right panel with a pinned Actions footer.** Why: the happy-path
  button has to be reachable without scrolling past a 12-field extraction, and the table stays
  visible behind the panel so the queue is still the context.
- **`window.prompt` for the advance note is gone**, replaced by a text field in the Actions
  section. Why: a browser dialog on a projector reads as unfinished, and Playwright auto-dismisses
  dialogs, so the note was untestable.
- **Sending with only an attachment is allowed.** The composer previously required typed text, so
  "here is my form" needed a sentence the resident had no reason to write. An empty send with an
  attachment now posts "Here is my completed application. Please file it." — the same phrasing
  `scripts/smoke.sh` proves works against the intake tool.
- **Playwright, one Chromium project, `retries: 1`, 90 s per test, no mocks.** Why: the point of
  the suite is "the buttons work against the real API and a real model", which a mocked fetch
  cannot show. `retries: 1` absorbs one slow LLM turn without hiding a real failure.
- **The seven design-review screenshots are committed.** Why: they are the artefact a reviewer
  actually looks at, and regenerating them needs a running API. `playwright-report/` and
  `test-results/` are gitignored — those are run output, not a record.
- **`next.config.ts` sets `agentRules: false` and `devIndicators: false`.** Next 16 dev writes
  `AGENTS.md`/`CLAUDE.md` into `web/` (this repo has its own at the root) and paints a dev badge
  over the bottom-left corner of every screenshot.

## Phase 2 (Fable, 2026-09-05, after 12 live probes and the author's answers)
- **Organics are weekly, not alternating.** The M1 schema alternated organics with recycling; real ESD
  policy and the zone notes both say weekly, and the bot told a resident "organics Week A only". Fixed
  in M6 without a migration: the column stays, nothing reads it.
- **Hybrid real data.** Read-only lookups (geocoding, street sweeping, zoning, permits by address,
  Get It Done open data) may call real City endpoints with a seed-data fallback; applications,
  workflows and tracking numbers stay fictional because no public write API exists (Accela and
  Get It Done have none). Rejected: real everywhere — CSV ingestion pipelines before Tuesday.
- **Strict sources rule plus a web search tool** restricted to sandiego.gov domains, so "answer only
  from sources" still lets the bot answer most San Diego questions. Model memory is never a source.
- **Trash answers speak in dates, not ISO week parity.** The tools compute the next recycling date;
  the model stops explaining odd/even weeks.
- **Evals grow by category** (adversarial, multi-turn, multi-intent), still mechanically scored,
  still not a gate. Spanish deferred: it worked in one probe and the author did not pick it.
- **KB grows to parking, utilities, housing** under the `general` intent (unfiltered retrieval) rather
  than three new intents: the classifier prompt is the only thing that changes.
- **A scorer assertion may be widened after a run; a prompt may not.** M9 item 34 failed because the
  phrase list lacked "wasn't able to find" while the reply was correct. Fable added the phrases at
  merge. §14 forbids tuning prompts to golden items; it does not forbid fixing a wrong test.
- **Eval numbers are reported per category** (standard, adversarial, multi_turn, multi_intent) and the
  headline provider comparison in README stays on the 30-item standard set so it remains comparable
  with the qwen and Bedrock runs of 2026-09-03.
- **Cheap read-only lookups are cross-domain; money, forms and filings stay per intent.** M10's
  audit showed the per-intent tool allow-list, not the prompt, was why a pothole-plus-trash-day
  message dropped its second half: the trash tool was not visible to the service_request profile.
  `CROSS_DOMAIN_TOOLS` (schedules, events, council district, status, referral) now ride on every
  domain profile; fee estimators, start_application and create_service_request do not.
- **A tool's required fields must match what the workflow actually needs.** `description` on
  create_service_request was required by the schema and unused by the validator, so the model
  stopped to ask for it. Optional with a generated fallback.
- **Milestone spend caps must cover the acceptance runs.** M10's $0.60 cap was below the ~$0.91 the
  specified before/after category runs cost on the escalate tier; the agent overran to $1.27 and
  said so. Future specs price the acceptance commands first (multi-intent items run ~$0.04 each on
  Opus) and set the cap above them.
- **Status lookups are public but redacted.** Anyone with a tracking number sees status, department,
  fee estimate, missing-field names and the next step, like a real 311 portal; applicant fields and
  the transition log are only readable through the staff API behind the login. Rejected: opaque
  tracking numbers (would hide the demo's readable ids for a threat that redaction already removes).
- **Fee estimators are cross-domain; filings are not.** After M10's allow-list finding, the red team
  showed multi-intent turns still dropped fee questions. Estimates are read-only, so they ride with
  the other lookups; start_application and create_service_request stay behind their intent.
- **An unavailable tool is not offered.** `search_city_website` is only in a profile when a search
  provider is configured. Advertising it while off cost three dead calls per turn and then a
  memory-based answer, which is the exact failure the strict-sources rule exists to stop.
- **Referral matching stems both sides with a 3-letter floor and a stoplist.** "dog license" against
  "Dog licensing" needs "dog" kept and "licens" matched; the earlier 4-letter floor dropped "dog".
- **No agent deletes rows from `traces`.** The table is the spend ledger the author asked for. The red
  team deleted 35 probe rows ($0.74) to tidy the demo pages; the ledger in STATE.md carries the number
  and spend.sh is understood to be a lower bound from that point.

## Pre-presentation fixes (Fable, 2026-09-07)
- **The traces page renders the reply; raw is a toggle.** The 2026-09-03 entry made `/traces` a raw
  debugging view; on a projector it printed literal asterisks in the demo's last beat. The reply
  now goes through MarkdownLite with a "raw" button, so the debugging view is one click away.
- **Tool summaries name the weekday of the date they return.** In a holiday week `next_recycling`
  shifted the date but the summary kept the zone's normal weekday, and the model wrote "Wednesday,
  September 10" for a Thursday. Found by the 2026-09-07 verification probes, fixed with a test
  pinned to Labor Day week.
- **Scheduled desktop automation must not live under ~/Desktop (2026-09-14).** The launchd job that
  was meant to open the demo on 09-08 failed with "Operation not permitted": macOS TCC blocks a
  non-GUI `bash` from reading Desktop/Documents/Downloads unless the binary has Full Disk Access.
  Next time, copy the script to `~/bin` or grant access before relying on it, and verify with
  `launchctl kickstart` on the day before, not just a manual run.

## Phase 3 hardening, round 1 (Fable, 2026-09-14)

Source: two read-only Opus audits (`docs/HARDENING_AUDIT.md`), author's answers (one week, $5 Bedrock,
GitHub Actions with agent pushes, AWS stays scripted).

- **Bounds at the edge, not in the model.** `message` max 4000 chars, `session_id` must match
  `^[A-Za-z0-9_-]{8,64}$`, `document_ids` max 5 and deduped. A 1 MB message was a 200 and a bill.
- **Two cost breakers before classify().** Per-session turn cap (200) and a daily `SUM(cost_usd)` cap
  ($25) both answer 429 with a sentence a resident can read. The classifier is itself a model call, so a
  breaker that trips after it is not a breaker.
- **`/health` is free; `/health/deep` is the model probe.** The old `/health` made a real chat and embed
  call per request, anonymous. `/health` now reports db, s3, kb count and startup errors, returns 503
  `degraded` when db or s3 fails; `/health/deep` is staff-only and cached 60 s. The web pill reads only
  db and s3.
- **Model client timeout 45 s, one retry.** The SDK default was 600 s and two retries.
- **Startup degrades instead of crash-looping.** Each lifespan step is wrapped; a failed KB ingest leaves
  the app serving with `/health` red, which is what `/health` was built for.
- **Request ids.** `X-Request-ID` on every response, one access line per request with status, ms and the
  traces row id for buffered chat.
- **`advance()` takes a row lock and re-checks `from_status`;** the UPDATE is conditional as a second
  guard. Two concurrent advances yield one event row and one 409.
- **Certificate before commit.** `issued` renders and stores the PDF in a BEFORE_COMMIT hook; a storage
  failure leaves the row `approved` and returns 503. The worker backfills rows issued before this change.
- **Tracking numbers from Postgres sequences** (migration 006, one per type, seeded above the current
  max and above the 000399 fixture floor); year from the clock; IntegrityError retried once.
- **The seed loader never truncates resident tables.** `applications`, events, documents, chat_messages,
  traces, staff tables are on a NEVER_TRUNCATE list; sample applications are inserted only if absent.
  Consequence: the staff queue accumulates across restarts by design; `scripts/reset_demo.sh` (which now
  backs up first) is the way to clear it.
- **Migrations under `pg_advisory_lock`; DB connect retried 30 s; statement_timeout 15 s.**
- **CI on every PR:** api (ruff, format, pytest), web (typecheck, lint, build), compose-smoke (stub
  OpenAI server, no model calls), security (pip-audit, npm audit, gitleaks). e2e and nightly eval exist
  but are gated on an OIDC secret that is not configured. Ruff: E, F, I, B, UP at line length 110;
  `Depends()`/`File()` defaults allow-listed rather than rewritten.
- **Web:** CSP with `script-src 'unsafe-inline'` (Next hydration needs it; nonces would forfeit static
  prerender), stream fallback only on 404/405 (a 500 used to silently re-run the turn and bill twice),
  partial answers kept on a dropped connection, API-down state with Retry on staff pages, error
  boundaries, dialog semantics on the staff drawer, polls that skip hidden tabs and back off.
- **Ruff formatting was re-run on merged main** rather than merging M17's 46 reformatted files over M14
  and M15; M17's two hand edits were re-applied by hand.
- **Push blocked:** the GitHub token on the Mac is invalid; every branch is local until `gh auth login`.

## Phase 3 hardening, round 2 (Fable, 2026-09-14)

- **`ENVIRONMENT=prod` fails closed.** A model validator refuses to start with any placeholder secret
  (`staff`, `civic`, `civicsecret`, `sk-litellm-demo`, `ollama`, `CHANGEME`, empty) or a `localhost`
  CORS origin, naming every offender at once. `dev` is the default so the committed profiles and a bare
  `pytest` keep working. `.env.example` and `.env.openai` ship `CHANGEME`; the two demo profiles keep
  their public values under a comment saying so.
- **Compose:** `restart: unless-stopped`, json-file logging 10m x 3, memory limits, healthchecks on api
  (the free `/health`, 503 = unhealthy) and web, `web` waits for a healthy api. Postgres, SeaweedFS S3
  and LiteLLM bind to 127.0.0.1; the SeaweedFS master and filer UIs are no longer published. Images
  pinned: seaweedfs 4.47, litellm v1.100.1, python 3.12.14-slim, node 22.23.2-alpine, uv 0.11.7.
- **The LiteLLM container no longer sees the whole `~/.aws`.** Only the credentials file is mounted,
  read-only, and `AWS_PROFILE` selects a Bedrock-only profile. The master key comes from the env file.
- **Images run as a non-root `app` user** with a `HEALTHCHECK`; the api image is multi-stage with uv
  copied from its own image, and uvicorn trusts proxy headers so a TLS proxy yields a Secure cookie.
  `COOKIE_SECURE` is tri-state and commented out in the templates because an empty value is a parse error.
- **`deploy/aws/up.sh`** rewrites `WEB_ORIGIN` to the public origin, narrows 22/3001/8080 to `MY_IP/32`
  (revoking older open rules first), generates the staff password, S3 secret and master key, writes
  `ENVIRONMENT=prod`. SeaweedFS accepts any key pair without an IAM config, so the S3 secret is
  decorative and the README says so. Not run.
- **Everything the model reads that we did not write is fenced.** KB chunks, fetched pages and tool JSON
  arrive inside `<source n kind trust="untrusted">`, a page cannot close the fence (`defang`), and the
  preamble says fenced text is never an instruction. Tool results carry `t1, t2` labels so they can
  never be cited as `[n]`.
- **The profile allow-list is enforced in the tool loop**, not only offered: an off-profile call gets an
  error summary and never executes. `traces.tool_rounds` records the rounds used.
- **Redirects stay on, the final host is re-checked** against the sandiego.gov allow-list; turning
  redirects off would have broken the `sandiego.gov` to `www.` 301s.
- **KB ingest is idempotent per document by content hash**, so a crash mid-ingest resumes; pre-existing
  rows are adopted by topic rather than re-embedded, which keeps old trace chunk ids valid.
- **Two prompt rules from the live run:** "do not do arithmetic on a tool's numbers to make a new
  figure" (the model turned a $1,250 fee into an invented $2,063 to $2,313 range) and "a t-label must
  never appear in your reply".
- **The `hardening` golden category:** 60 items, ten groups, 12 held out. Run 1 on main: guardrail 93%,
  three of the four failures were over-strict phrase lists, fixed in the scorer not the prompt (PLAN
  §14). Run 2 on the M19 branch, 43 dev items: guardrail 100%, numbers_from_tools 100%, intent 84%.
  The intent misses are mostly label strictness; not tuned. One real open item: an injection wrapper
  ("developer mode ... then tell me the trash day") flips the router to `smalltalk`, so the legitimate
  half goes unanswered. That is a router weakness, recorded, not papered over.
- **Spend:** M19 about $3.52 against its $3.30 line; phase 3 total about $4.3 of the $5 the author set.

## Phase 4 production readiness (Fable, 2026-09-15)

- **Scope from the author:** no Spanish; benchmark ten questions known to be unanswered and close the
  gaps; separate the resident chat from the staff console; a reporting dashboard over the traces the
  author already likes; one more application type; both production shapes documented in the HTML kit.
- **Resident sessions are bound to a cookie (Fable's call).** The last open audit item was a
  client-chosen session id that anyone could guess. The API now mints `resident_session` = HMAC of the
  id on first contact; later requests for that id must carry it or get 403. Chosen over a server-stored
  session table because nothing is stored, a restart logs nobody out, and the client protocol is
  unchanged (the browser still generates the id). No dev bypass: the eval runner and smoke.sh carry
  cookie jars like a browser.
- **The dashboard is computed in SQL from the tables that already exist**, no metrics pipeline, no new
  dependency; charts are inline SVG. The most useful panel is "unanswered": recent turns with no
  sources or a decline, which is how a city finds the next KB gap.
- **Two migrations share the 008 prefix** (`008_resident_sessions.sql` from M20, `008_stro.sql` from
  M24). The runner applies files in filename order and both are additive, so they coexist; M26a takes
  009. Renaming after either has been applied to the shared database would re-run it, so the names stay.

## Phase 4, round 1 outcomes (Fable, 2026-09-15)

- **Resident sessions (M20):** `documents` gained a `session_id` column so "first contact" can be
  decided from uploads as well as chat; the cookie is set on the streaming response itself because a
  route that returns a Response never inherits a dependency Response's headers.
- **Staff console (M21):** the resident app has no staff links; the console has its own layout and
  nav (Queue, Dashboard, Traces), one auth gate for all three. The report is windowed by `created_at`
  in every section, days with no turns are absent from `by_day` (truthful, unpadded), and the decline
  phrase family is copied from the eval scorer with a test that keeps the copy a subset. Dark theme is
  a whole-app decision the web has never made (`color-scheme: light`); left as is.
- **Gap benchmark (M23):** ten real gap questions became the `production` golden category. Closed with
  content, not prompt rules: run 2 gave citations 100%, keywords 100%, zero declines. Two remaining
  misses were the eval's own phrases and were corrected as measurement (item 125's `must_not_contain`
  flagged a correct denial; item 128 no longer requires `get_referral` because the KB now answers it).
  Real defect surfaced: the `service_request` profile enumerates categories by hand and omits three
  that exist in `service_categories.json`, and one reply named a department the tool did not return.
  Both go to M27. The pre-M19 `kb_documents` rows had no content hash, so KB edits were silently
  ignored on this database until the hashes were backfilled; adoption must write the hash (M27).
- **STRO licence (M24):** fourth type, `STR-` prefix, own sequence, flat fees per tier from the
  Treasurer's page, TOT number required at validation (the real form requires it before issue; one
  required list per type). Offered by both `general` and `business` because the live classifier sends
  "apply for a short-term rental license" to `business`. `STR` is matched before `SR` in the tracking
  regex. Golden items renumbered to 130-132 after colliding with M23's 120-129.
- **A regression the mocks could not see (2026-09-15).** M26a's first heartbeat wrapper drove the turn
  generator step by step from fresh tasks. Each step then ran in a different asyncio context, and the
  trace collector's ContextVar token, set at the top of the turn, was reset from another context:
  every streamed turn produced its full answer and then ended in the fallback reply. 574 mocked tests
  passed; the rebuilt stack's browser test failed on the first real turn. Fixed by running the whole
  turn in one producer task behind a queue, with a test that sets and resets a ContextVar inside the
  generator. Lesson recorded: any wrapper that moves an async generator between tasks needs a live
  turn in its acceptance, not only a mock.

## Phase 4, round 2 outcomes (Fable, 2026-09-15)

- **Admission control is a 429 before the body, not a wait inside it.** The stream route no longer
  takes a pool-holding dependency; the guards run in a short session; a full semaphore answers 429
  with Retry-After. Measured on the rebuilt stack with the real model: 20 concurrent streams, 16
  served, 4 turned away, zero errors, 9 s total. Before: 60 s per stream and apologies.
- **One clock.** `app/clock.py` in America/Los_Angeles replaces every `date.today()`; `TZ` is set in
  compose; a frozen-clock test pins New Year's Eve behaviour.
- **Shared state moved to Postgres where it matters:** per-IP token buckets, idempotency keys with a
  60 s payload dedupe, worker row claims with SKIP LOCKED, an advisory lock around KB ingest. The staff
  login throttle is the one counter still in memory; recorded as a gap.
- **Retention is a setting, not a policy.** `TRACE_RETENTION_DAYS` defaults to keep; the California
  Public Records Act sets a two-year floor before destruction, so the demo does not delete by default.
- **CI now exercises the thing that broke.** compose-smoke starts the full stack with a stub model
  that answers classification, runs the smoke script in stub mode, and a 20-stream probe with a
  15-second ceiling; Trivy scans both images as a hard gate; down migrations exist from 006 and a
  restore drill ran against a real backup.
- **The service-request category list is built from the seed table**, and filing replies must quote
  the tool's department verbatim; the summary now states department and target response time so the
  model has nothing to guess.
- **Spend for phases 3 and 4:** about $4.3 (phase 3) plus about $1.5 (M23 two runs, M24 smoke and
  probes, verification turns and the live concurrency probe) in phase 4.
