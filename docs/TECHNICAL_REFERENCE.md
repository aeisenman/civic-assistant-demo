# Municipality Agent, technical reference

What the system is, what happens on every request, and why each piece is shaped the way it is.
Written 2026-09-21 for a technical review. `ARCHITECTURE.md` is the file-level source; this is the
reading order. Every number below was measured on the stack as built (commit `d1ed895`).

## 1. What it is

A resident-facing assistant for a fictional City of San Diego. Residents ask about trash pickup,
permits, business tax, City events, and service requests, and can file four kinds of application
from the chat: building permit, business tax certificate, Get It Done service request, short-term
rental (STRO) licence. Staff sign in to a console with a queue, a reporting dashboard, and a trace
of every model turn.

Three rules shape everything:

1. **Facts come from tools, policy comes from retrieval.** Trash zones, fees, statuses and events
   are rows; they are answered by typed function calls against Postgres. FAQ and policy text is
   markdown; it is answered by hybrid retrieval over pgvector. The split is enforced by the tool
   allow-list per intent.
2. **Nothing the model says comes from its own memory.** Every fact traces to a tool result or a
   cited chunk. Everything the model reads that the team did not write is fenced as untrusted data.
3. **Every turn leaves a trace.** Intent, tier, model, tool calls with source, retrieved chunks,
   tokens, latency, cost. The dashboard and the evals are computed from that table.

## 2. The system at a glance

Five containers under one compose file, one `.env` file selecting the model provider.

| Service | Image | Port | Role |
|---|---|---|---|
| `web` | Next.js 16, React 19, Tailwind 4 | 3001 | Resident chat at `/`; staff console under `/staff` |
| `api` | FastAPI, Python 3.12, SQLAlchemy 2 async | 8080 | Routing, retrieval, tools, workflow engine, traces, reports |
| `db` | Postgres 16 + pgvector | 127.0.0.1:5433 | Records, vectors, full text, rate limits, sessions |
| `seaweedfs` | SeaweedFS, S3 API | 127.0.0.1:8333 | Uploaded documents and issued certificates |
| `litellm` | LiteLLM gateway | 127.0.0.1:4000 | OpenAI-protocol front for Amazon Bedrock; only under the `aws` profile |

Every service has `restart: unless-stopped`, log rotation (10 MB x 3), a memory limit, and a
healthcheck. The images run as a non-root user and are pinned to exact versions. Only 8080 and 3001
are reachable from outside the host.

**Model tiers** are roles, not model names. The API never names a model; it names a tier and the
gateway maps it.

| Tier | Bedrock (demo) | Used for |
|---|---|---|
| `small` | Claude Haiku 4.5 | Intent classification, document type detection, JSON-only tasks |
| `smart` | Claude Sonnet 4.6 | Resident answers with tools and retrieval |
| `escalate` | Claude Opus 4.6 | Low confidence, high complexity, multi-intent turns |
| `extract` | Amazon Nova Lite | Form field extraction from uploaded documents (300k context) |
| `embed` | Titan Embed v2 | Knowledge base chunks and queries, 1024 dimensions |

Copying `.env.ollama` instead runs the same code on local qwen2.5 models and nomic-embed-text.

## 3. One chat turn, end to end

The resident types a message. The browser posts it to `POST /api/chat/stream` with a session id it
minted itself and, after the first turn, the cookie the API handed back.

1. **Edge checks, before any model call.** The body is bounded (message at most 4,000 characters,
   session id matches `^[A-Za-z0-9_-]{8,64}$`, at most five document ids). The per-IP token bucket
   is charged. The session cookie is verified or, on first contact, minted. The per-session turn cap
   and the daily cost breaker are read. A stream slot is taken without waiting; none free means a
   429 with `Retry-After`, sent before any headers.
2. **Intake check.** A file drop, or a reply while this session has an application waiting for
   information, is a workflow turn and short-circuits here. Its reply is templated, never generated.
3. **History.** The last ten messages for the session.
4. **Classify.** The small tier returns JSON: intent, confidence, complexity, secondary intents. A
   tracking-number pattern in the message sets the intent directly with no model call.
5. **Select the tier.** `escalate` when confidence is under 0.6, complexity is high, or a second
   intent is present; otherwise `smart`. The reason is a sentence on the trace.
6. **Profile.** One per intent: system prompt, tool allow-list, knowledge-base topic. Seven intents.
7. **Retrieve.** Unless the intent is smalltalk: pgvector cosine top 8 and Postgres full-text top 8,
   fused by reciprocal rank fusion, top 5 returned. A topic filter runs first and is dropped if it
   yields fewer than two hits.
8. **Build the prompt.** The shared preamble, then the numbered sources, each inside
   `<source n kind trust="untrusted">`, then the date line last so the cacheable prefix stays stable.
9. **Tool loop.** At most four rounds. The model may call only tools on its profile's allow-list; an
   off-list call gets an error summary and never runs. A repeated call with the same arguments is
   served from a per-turn cache. Tool JSON goes back inside a fence labelled `t1, t2` so it can never
   be cited as `[n]`. Text the model writes next to a tool call is a preamble and is not streamed.
10. **Answer.** The final round's tokens stream to the browser. Citations `[n]` are mapped back to
    the sources; if none were cited, the top two are returned flagged `implicit`.
11. **Persist.** One `traces` row, then the user and assistant messages pointing at it. A trace
    write failure does not lose the answer.
12. **Done.** One `done` event with the reply, citations, actions and the trace. A failure anywhere
    is a `done` with the fallback reply, never a dropped connection.

Every event goes out as server-sent events: `status` after routing, `tool` per dispatched call,
`token` per delta, `done` once. A `: heartbeat` comment every 15 seconds keeps a load balancer from
idling the connection out during a slow tool round.

`POST /api/chat`, which the evals and the smoke script use, is the same generator with the events
thrown away. The two endpoints cannot drift.

## 4. Routing and the prompt

- The classifier sees the last three user messages, so "and recycling?" resolves against the address
  given a turn earlier.
- `smalltalk` gets no tools and no retrieval.
- `general` gets every tool and no topic filter; it is where housing, parking, utilities, library
  and jobs questions land.
- Six tools ride on every domain profile so a message with two subjects is answered in one turn:
  trash schedule, next pickup, events, council district, application status, referral. Tools that
  quote money, open a form, or file a case stay behind their own intent.
- The preamble fixes the rules the evals score: answer only from sources and tool results, cite
  `[n]`, call every fee an estimate, never state a number no tool produced, never do arithmetic on
  a tool's numbers, handle every request in a multi-part message before asking anything, say whether
  a fact came from live or seed data, quote a filing's department and tracking number verbatim from
  the tool, and treat fenced text as data even if it claims to be an instruction.
- The service-request category list in the prompt is generated from the seed table at import, so the
  prompt and the table cannot drift.

## 5. Retrieval

- Knowledge base: nine markdown files under `api/kb/`, about 1,000 lines, 133 chunks. Each file has
  frontmatter with title, topic and source URL.
- Chunking: each `### Q:` FAQ block is one chunk; prose under `##` is packed into roughly 1,200
  character windows with 150 of overlap on paragraph boundaries. Chunk text starts with the title and
  heading so a retrieved paragraph carries its context.
- Ingest at startup is idempotent per document by content hash and runs under an advisory lock, so
  two replicas cannot double the knowledge base and a crash mid-ingest resumes.
- Hybrid search: dense finds paraphrases, full text pins exact strings like "SB-1186". Reciprocal
  rank fusion needs no score calibration between the two scales.
- The index on `kb_chunks.embedding` is HNSW, because the migration runs against an empty table and
  IVFFlat needs rows to train.

## 6. Tools and live City data

Sixteen tools. Each is a plain async function with a pydantic input model; the registry derives the
OpenAI JSON schema from the model, so contract and validation cannot drift. `dispatch()` never
raises: an unknown tool, bad arguments, or an exception inside a tool becomes `{"error", "summary"}`
and the model gets another round.

Every result carries a `summary` sentence, a `source` (`live` or `seed`), and for address tools a
`match` (`seed`, `geocoded`, `zip`). The trace shows all three.

Live data comes from the City's own ArcGIS services: the geocoder, council districts, street
sweeping, zoning, permits on file, and the Granicus RSS of council agendas. One resolver backs every
address-taking tool: exact seed match, then the City geocoder at score 80 or better, then a bare ZIP.
All live calls go through one HTTP module with a 4-second timeout, a 10-minute cache, a
`None` return on any failure, and redirect targets re-checked against the `*.sandiego.gov`
allow-list. A dead City service degrades to seed data with the answer labelled "based on demo
data", never a 500. `LIVE_DATA_ENABLED=false` turns the module off; the unit tests run that way.

Web search (`search_city_website`) is built and off: it needs a Brave key and reports itself
unconfigured otherwise, rather than being an advertised tool that always fails.

## 7. Prompt safety

- Every knowledge-base chunk, fetched page, and tool result is wrapped in `<source ...
  trust="untrusted">`; a `defang` step neutralises any `<source` text inside so a page cannot close
  the fence. The preamble says fenced text is never an instruction.
- The tool allow-list is enforced in the loop, not only offered to the model.
- Status lookups return a redacted view: tracking number, type, status, department, fee estimate,
  names of missing fields. Applicant fields never reach the model, so walking sequential tracking
  numbers yields nothing personal.
- Markdown from the model is rendered by a small allow-list renderer: `http`/`https` links only,
  no raw HTML, no data-URI images. A Playwright test feeds it `<script>`, `onerror`, and
  `javascript:` links and asserts inert text.
- The hardening eval category (60 items: injection, out of scope, ambiguity, numbers, dates,
  multi-turn, noise, language, live-data failure, cost loops) scores guardrail 100% and "no number
  absent from tool results" 100%. One open item: a "developer mode" wrapper flips the router to
  smalltalk, so the legitimate half of that question goes unanswered. Recorded, not hidden.

## 8. Streaming and concurrency

- The stream route holds no pool connection. The two guards run in a short session that is closed
  before the response is built; the generator opens its own. A FastAPI yield dependency is not
  released until a streaming body drains, and taking one deadlocked the API at exactly
  `pool_size + max_overflow = 20` concurrent streams. That was measured, fixed, and is now gated.
- Admission control is a 429 before the body. At most 16 turns stream at once.
- Every model call has a 45-second read timeout and one retry. The SDK default was 600 seconds with
  two retries.
- Certificate rendering and every boto3 call run in a thread, with 3-second connect and 10-second
  read timeouts, so a slow object store cannot stall the event loop.
- Measured on the live stack with the real model: 20 concurrent streams finish in 9 seconds, 16
  served, 4 turned away with 429, zero errors. Against the stub model in CI: 20 streams in 1.8
  seconds. The pytest load test runs 40 concurrent streams against a scratch database and asserts
  zero 500s, complete turns, and p95 under 2 seconds.

## 9. Intake and the workflow engine

Two intake paths create the same `applications` row.

- **Document.** Upload goes to SeaweedFS; pypdf extracts text in a thread; under 50 characters is a
  scan and is stored with empty text and refused honestly (no OCR). The small tier detects the type,
  the extract tier fills the type's pydantic schema, the validator lists what is missing, the row is
  submitted.
- **Form.** A quick action renders `GET /api/forms/{type}` inline; the submit posts to
  `POST /api/applications`, validated by the same model. An `Idempotency-Key` per submit makes a
  double click or a retry return the original row.
- **Needs info.** Missing fields are asked for in chat; the next message is extracted against only
  those fields, merged, and resubmitted. The state machine re-validates; the model does not decide
  completeness.

Workflow replies are templated: a tracking number, a fee and a missing-field list are facts the
engine already knows, and a model paraphrasing them risks a wrong number.

One status spine for all four types:

```
submitted -> validating -> needs_info | routed -> in_review -> approved | rejected -> issued -> closed
```

- Automatic (an in-process worker every 3 seconds): `submitted -> validating`, `validating ->
  needs_info | routed` (the validating hook decides), `routed -> in_review`.
- Manual (staff buttons): `in_review -> approved | rejected`, `approved -> issued`, `-> closed`.
- `advance()` is the only writer of status. It takes `SELECT ... FOR UPDATE`, re-checks the current
  status, runs the pre-commit hook, and updates with a `WHERE status = from_status` guard, so two
  concurrent advances produce exactly one event row and one 409.
- `issued` renders the certificate PDF and stores it before the status commits; a storage failure
  leaves the row `approved` and returns 503. The worker backfills rows issued before that rule.
- Tracking numbers come from one Postgres sequence per type; the year comes from the Pacific clock.
- The worker claims rows with `FOR UPDATE SKIP LOCKED`, so a second worker never processes the same
  application.

## 10. Data model

Postgres holds everything. Plain SQL migrations applied in filename order under an advisory lock,
tracked in `schema_migrations`, with `.down.sql` files from 006 onward and a `--rollback` flag.

| Group | Tables |
|---|---|
| Resident records | `applications`, `application_events`, `documents`, `chat_messages`, `traces` |
| Reference (seeded, reloaded on start) | `trash_zones`, `addresses`, `events`, `permit_types`, `service_categories`, `referrals`, `council_districts` |
| Knowledge base | `kb_documents` (with content hash), `kb_chunks` (text, `embedding vector(1024)` HNSW, `tsv`) |
| Operations | `staff_users`, `staff_sessions`, `rate_limits`, `schema_migrations` |

The seed loader reloads reference tables only; resident tables are on a `NEVER_TRUNCATE` list and
sample applications are inserted only if absent. SeaweedFS keys are `documents/<id>/<filename>` and
`certificates/<tracking_number>.pdf`. Pointing `S3_ENDPOINT` at AWS is the whole change for real S3.

`scripts/backup.sh` writes a `pg_dump` plus a tar of the object store; `scripts/reset_demo.sh` calls
it before wiping; `scripts/restore.sh` restores the newest backup into a scratch database and prints
row counts side by side. The drill has been run.

## 11. Sessions, staff auth, limits

- **Resident sessions.** The browser mints a session id. On first contact the API sets
  `resident_session` = HMAC-SHA256(session id, `SESSION_SECRET`), HttpOnly, SameSite=Lax, 30 days.
  Every later request on that id must carry a cookie that verifies for exactly that id or gets a 403.
  Nothing is stored server-side; a restart logs nobody out; rotating the secret starts everyone a new
  conversation. No bypass header exists: the eval runner and the smoke script carry cookie jars.
- **Staff auth.** scrypt password hash, 32 random bytes as the session token with only its SHA-256
  stored, HttpOnly cookie for 12 hours, one generic 401 after a one-second pause, 429 after five
  failures in a minute. Staff routes (`/api/applications*`, `/api/traces`, `/api/reports`,
  `/health/deep`) require it; `advance` writes the signed-in username as the actor.
- **Per-IP rate limit.** A token bucket in Postgres (one `INSERT ... ON CONFLICT ... RETURNING`),
  burst 20, refill 30 a minute, on every route a stranger can reach. Postgres rather than memory so
  two API replicas share one limit.
- **Cost.** Every call is priced from `LLM_PRICES_JSON` onto the trace. A per-session turn cap
  (200) and a daily cap ($25, Pacific day) are checked before the classifier, with a warning at 80%.
- **Retention.** `TRACE_RETENTION_DAYS` defaults to keep everything; above zero the worker sweeps
  traces and messages daily. The California Public Records Act sets a two-year floor before
  destruction, which is why the default keeps.
- **Production mode.** `ENVIRONMENT=prod` refuses to start on any placeholder secret, a `localhost`
  origin, or a non-TLS origin, naming every offender at once.

## 12. Observability and the dashboard

- Every response carries `X-Request-ID`; one access line per request logs status, duration and, for
  buffered chat, the trace row id. No resident message text is logged.
- `/health` is free and anonymous: process, database, object store, chunk count, startup errors.
  It answers 503 when the database or object store is down. `/health/deep` makes the model probe,
  staff-only, cached 60 seconds.
- Startup steps are wrapped: a failed knowledge-base ingest leaves the app serving with `/health`
  red instead of crash-looping.
- `GET /api/reports/summary?days=` computes the dashboard from the tables in SQL: turns, sessions,
  cost, p50 and p95 latency, error and fallback turns, turns and cost by day, intents, tiers, tools
  with error rate and live share, citation rate, applications by type and status, median hours to
  review, and the ten most recent unanswered turns. The unanswered panel is how a city finds its
  next knowledge-base gap.

## 13. Testing and CI

| Layer | What | Count |
|---|---|---|
| Unit | pytest with a mocked model client, no network | 584 |
| Load | 40 concurrent streams against a stub model and a scratch database | 1, `-m load` |
| Browser | Playwright against the running stack | 23 |
| Smoke | Upload, file, advance, issue, certificate, needs-info, business tax, STRO | 13 steps |
| Evals | Golden questions scored mechanically: intent, tool choice, citation, keywords, guardrail, no invented numbers | 132 in 6 categories |

The evals report and never gate; every generalising fix is logged in `DECISIONS.md` rather than
tuned to an item.

GitHub Actions on every push and pull request: `api` (ruff, format, pytest), `web` (typecheck,
lint, build), `security` (pip-audit, npm audit, gitleaks, Trivy on both images as a hard gate),
`compose-smoke` (the full stack with a stub model that classifies, the smoke script in stub mode,
and a 20-stream probe that gates). `e2e` and a nightly eval exist behind an AWS OIDC secret.

## 14. Configuration and the provider swap

One typed settings object read from `.env`. The three committed profiles differ only in model names
and base URLs: `.env.ollama` (local), `.env.openai`, `.env.bedrock` (LiteLLM gateway, the demo). The
API speaks the OpenAI protocol through one client module that times, prices and traces every call.
Changing the embedding width needs a fresh database; the vector width is asserted at startup so a
mismatch fails loudly at boot rather than at the first insert.

## 15. Production shapes

Both change environment values and where the containers run, nothing in the code.

- **A. One VM, compose, Caddy for TLS, nightly backup to S3, an instance role, SSM parameters,
  CloudWatch.** About $90 a month plus model usage. Recommended for a pilot.
- **B. ECS Fargate (api x2, web x2, worker x1, litellm), ALB with ACM and WAF, RDS Postgres with
  pgvector Multi-AZ, S3, Secrets Manager, CloudWatch.** About $310 a month plus model usage. The
  shape a citywide launch needs; two API tasks are safe because rate limits and worker claims are
  in Postgres.

Model usage is about $0.03 a turn on the current tiers. The full tables are in `PRODUCTION_PLAN.md`.

## 16. Known limits, by decision

Payments, resident accounts, real write integrations (Accela and Get It Done have no public write
API), OCR, Spanish, TLS in the compose demo, a per-claim faithfulness score, an independent
accessibility audit, a Public Records Act redaction procedure, the staff login throttle being
in-process, and the developer-mode router flip. Each has a reason and a production answer in the
demo kit's "Gaps left on purpose" tab.

## 17. Questions an engineer will ask

- **What breaks with two API replicas?** Rate limits, idempotency, worker claims, migrations and
  ingest are all in Postgres. The staff login throttle is the one in-memory counter left.
- **Where does the model get its facts?** Only from fenced sources and tool results. A "no number
  absent from tool results" scorer runs on every eval.
- **How do you know the streaming path works?** A load test in pytest, a probe in CI, and a live
  measurement on Bedrock. A regression in the heartbeat wrapper passed 574 mocked tests and was
  caught by the browser test on the rebuilt stack the same hour; it is written up in `DECISIONS.md`.
- **What happens when Bedrock hangs?** 45-second timeout, one retry, fallback reply with a trace
  naming the error, connection never dropped. LiteLLM falls back from Opus to Sonnet for the
  escalate tier if throttled.
- **What happens when the City's ArcGIS is down?** Seed data, labelled as such, in under 4 seconds.
- **How does a new application type get added?** One pydantic schema, one validator, one fee
  function, seed rows, a sample PDF. The STRO licence was added that way; the form, extraction,
  state machine and certificate path did not change.
- **How does a new system of record get added?** One adapter module behind an existing tool
  contract. The live City layers are the proof: the same council-district tool answered from a seed
  row in phase 1 and from ArcGIS in phase 2.
