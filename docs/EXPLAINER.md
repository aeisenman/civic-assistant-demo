# File-by-file explainer

Every source file, what it does, why it exists, and the one name to be able to talk
about. Then twenty questions a reviewer might ask, with where the answer lives.

## `api/app/`: the service

| Path | What and why | Name to know |
|---|---|---|
| `main.py` | FastAPI app factory and the startup sequence. Order matters: migrations, S3 bucket, seed, KB ingest, then the worker task. Exists so nothing else has to know the boot order. | `lifespan` |
| `config.py` | Every runtime knob as one typed pydantic-settings object read from `.env`. Exists so no module reads `os.environ` and no model name is hard-coded. | `Settings.model_for_tier` |
| `db/engine.py` | The single async SQLAlchemy engine plus the per-request session dependency. `pool_pre_ping` because the DB container can restart under the API. | `get_session` |
| `db/migrations.py` | Applies `migrations/*.sql` once each, tracked in `schema_migrations`, substituting `{{EMBED_DIM}}`. Plain SQL instead of Alembic: fewer concepts for a demo. | `run_migrations` |
| `db/models.py` | SQLAlchemy 2 mapped classes, one per table. The SQL files are the source of truth; these exist so queries are typed. | `Trace` |
| `db/migrations/001_init.sql` | The whole schema: records, KB tables, traces, chat messages, the hnsw index on `kb_chunks.embedding`. | `vector({{EMBED_DIM}})` |
| `db/migrations/002_traces_m2.sql` | Adds `reason`, `error`, `calls`, `document_ids` to `traces`, which 001 had no columns for. | `calls` |
| `db/migrations/003_m3.sql` | Adds `warnings` to `applications` and re-asserts the session/document columns with `ADD COLUMN IF NOT EXISTS`, so it is safe on an older database. | `warnings` |
| `db/migrations/004_m8_live.sql` | Adds `trash_zones.zips`, the ZIP -> collection-zone fallback M8 needs so a geocoded or ZIP-only address still gets a day. | `zips` |
| `db/migrations/005_staff_auth.sql` | `staff_users` and `staff_sessions` for the M11 login. The session table's primary key is the sha256 of the cookie, so a database dump holds nothing replayable. | `staff_sessions` |
| `db/migrations/008_resident_sessions.sql` | Adds `documents.session_id` so an upload counts as first contact for the M20 cookie, plus the index the EXISTS uses. NULL on every older row: those simply claim no session. | `session_id` |
| `db/migrations/008_stro.sql` | One more tracking-number sequence, `tracking_stro_seq`, for M24's fourth application type. Additive and `IF NOT EXISTS`; `applications.type` is plain TEXT, so nothing else about the schema changes. | `tracking_stro_seq` |
| `db/migrations/009_runtime.sql` | M26a: the `rate_limits` bucket table, `applications.idempotency_key` under a unique partial index, and a unique index on `kb_documents.filename` so two replicas cannot ingest the same file twice. Additive and `IF NOT EXISTS` throughout, because it is applied to a database that already holds the demo's data. | `rate_limits` |
| `clock.py` | `today()` and `now()` in `America/Los_Angeles`. Exists because the container is UTC, so a bare `date.today()` was already tomorrow from 4 pm Pacific — the prompt said Monday while the trash tool answered for Tuesday, and a permit filed on New Year's Eve would have read `PRM-2027-…`. One helper means one place to freeze in a test. | `today()` |
| `rate_limit.py` | A per-IP token bucket kept in Postgres, applied to the four routes a stranger can reach. Refill and spend are one `INSERT … ON CONFLICT DO UPDATE … RETURNING`, so it is one round trip and atomic; in Postgres rather than in the process so `--scale api=2` is still one limit. Keys on `request.client.host`, which uvicorn's `--proxy-headers` has already resolved, rather than trusting the header directly. | `take_token`, `rate_limit` |
| `auth.py` | Staff passwords (`hashlib.scrypt`, salt inside the hash string), session rows, the in-memory failed-login counter, and the `require_staff` dependency the staff routers hang off. Stdlib only: bcrypt or argon2 would be a wheel to pin and explain. | `require_staff` |
| `resident_session.py` | Binds a resident `session_id` to the first browser that used it: `resident_session` is an HMAC of the id under `SESSION_SECRET`, minted on first contact (no `chat_messages` and no `documents` row) and required on every request after. An HMAC rather than a stored token, so nothing is written server-side and a restart logs nobody out. | `require_or_mint` |
| `llm/client.py` | The only module that talks to a model, so every call is tiered, timed, priced and traced in one place. Speaks the OpenAI protocol, which is what makes the provider an env swap. `chat_stream()` is the same call with `stream=True`: text deltas out as they arrive, tool-call deltas accumulated by index, the same `LLMResult` last so the trace cannot tell the two paths apart. | `chat()`, `chat_stream()` and `TraceCollector` |
| `llm/router.py` | Intent classification on the small tier plus the tier-selection rules. The routing story lives here, in code, not in prompts. | `select_tier` |
| `rag/ingest.py` | Turns `api/kb/*.md` into `kb_documents` + `kb_chunks` with embeddings and a `tsvector`. Runs at startup when the table is empty. | `split_markdown` |
| `rag/retrieve.py` | Hybrid retrieval: pgvector cosine plus Postgres full-text, fused with reciprocal rank fusion. | `rrf()` |
| `live/http.py` | The one httpx front door for live City calls: 4-second timeout, a 10-minute in-process cache keyed by URL, `None` on any failure. `LIVE_DATA_ENABLED=false` short-circuits it, which is how tests stay off the network. | `fetch()` |
| `live/geocode.py` | **The** address resolver: seed row, then the City's ArcGIS geocoder, then a bare ZIP. Exists because every tool used to do its own exact match, so a real address that was not one of the 40 seeded rows was reported as not existing. | `resolve_address` |
| `live/arcgis.py` | The four live City map tools (district, street sweeping, zoning, permits) plus the Granicus council-agenda RSS. The only module that knows webmaps.sandiego.gov URLs. | `get_council_district` |
| `live/search.py` | `search_city_website`: last-resort search restricted to `*.sandiego.gov`, which fetches the top two pages and returns their text as citable sources. Tags are stripped with stdlib `html.parser`, so no new dependency. | `is_city_url` |
| `tools/registry.py` | The tool catalogue: name to pydantic model and async function, with the JSON schema derived from the model so contract and validation cannot drift. | `dispatch()` |
| `tools/trash.py` | `get_trash_schedule`, `get_next_pickup` and `get_holiday_schedule`. Address to zone to collection day, via `resolve_address`; a ZIP-level match is labelled and carries the City's real collection-map link. | `_confidence` |
| `tools/trash_calendar.py` | Pure date math for week parity and holiday shifts. No I/O, so it is directly unit-tested. | `next_pickup` |
| `tools/civic.py` | `search_events` (seed rows merged with live council agendas) and `get_referral`, which is how the assistant says "not us, here is who". Council district moved to `live/arcgis.py` in M8. | `search_events` |
| `tools/fees.py` | Permit and business tax estimates. Both rules are pure functions so the validator and the tool share one implementation. | `business_tax_breakdown` |
| `tools/applications.py` | Status lookups, `start_application` (returns a form schema), and `create_service_request`, which files through the engine so a chat-filed case gets the same state machine as a PDF. | `create_service_request` |
| `agents/profiles.py` | One profile per intent: system prompt, allowed tools, KB topic. The allow-list is the cheap half of routing. | `PROFILES` |
| `agents/chat.py` | The orchestrator: classify, retrieve, tool loop, cite, persist — written once as `stream_chat`, an async generator of `status` / `tool` / `token` / `done` events. `handle_chat` just drains it, so the streaming and buffered endpoints cannot answer differently. Wrapped so a broken turn is still a traced turn with a 200. | `stream_chat`, `handle_chat` |
| `agents/intake_turn.py` | The two chat turns that are workflow rather than Q&A: a file drop, and a reply that fills missing fields. Returns `None` for anything else. | `handle_intake_turn` |
| `agents/rendering.py` | Pure formatting between model and response: the Sources block, `[n]` to citations, tool results to UI actions, the templated workflow replies, and today's date. | `citations_for` |
| `workflows/schemas.py` | One pydantic model per application type: the single definition driving extraction, validation and form rendering. | `form_schema` |
| `workflows/engine.py` | The state machine. The only writer of `applications.status`; every transition writes an audit row and runs the entry hook. | `advance()` |
| `workflows/worker.py` | One asyncio task polling every 3 s for applications sitting on an automatic status. No broker, no second container. | `tick()` |
| `workflows/store.py` | Creates the `applications` row and its opening event, and draws tracking numbers from one Postgres sequence per type. | `next_tracking_number` |
| `workflows/validators.py` | Completeness, address and fee checks that decide `needs_info` versus `routed`, and set the department. | `validate()` |
| `workflows/intake.py` | Upload to SeaweedFS, text via pypdf, type detection, field extraction, and gap-filling from a chat message. | `extract_fields` |
| `workflows/certificates.py` | Renders the one-page PDF at `issued` and stores it. `render_certificate` is pure bytes, so it is tested without S3. | `render_certificate` |
| `storage/s3.py` | boto3 against SeaweedFS with path-style addressing. Pointing `S3_ENDPOINT` at AWS is the whole swap. | `key_for` |
| `seed/loader.py` | Truncate-and-insert `seed_data/*.json` into the reference tables at startup. Editing a JSON file and restarting is the whole update workflow. | `seed_all` |
| `api/health.py` | `/health`, checking db, s3, llm and embed independently so one dead dependency shows as one red box rather than a 500. | `health()` |
| `api/chat.py` | `POST /api/chat` and `POST /api/chat/stream`. Thin: validate, open a session, hand off to the orchestrator. The streaming route takes **no** session dependency — a yield-dependency is not released until the body has drained, which pinned one pool connection per stream and deadlocked at 20 — so the guards run in a short-lived session and the generator opens its own. It also takes its stream slot in the handler, answering 429 before any body, and emits a `: heartbeat` comment every 15 s while waiting on the model. | `post_chat_stream`, `_with_heartbeat` |
| `api/documents.py` | `POST /api/documents` multipart upload; returns `has_text` so the UI can say "no text found". | `upload_document` |
| `api/applications.py` | The staff surface: list, detail with timeline and allowed transitions, create from a form, advance, certificate. Everything but `POST /api/applications` (the resident's own inline form) is behind `require_staff`, and `advance` records the signed-in username as the actor. | `advance_application` |
| `api/forms.py` | `GET /api/forms/{type}`, rendered once at import from the pydantic models. | `FORM_SCHEMAS` |
| `api/traces.py` | `GET /api/traces` and `/api/traces/{id}`, newest first. Staff-only: a trace holds every resident message and reply. | `list_traces` |
| `api/reports.py` | `GET /api/reports/summary?days=1..90`, the staff dashboard's only call. Staff-only. Every figure is one SQL aggregate over `traces`, `chat_messages`, `applications` and `application_events` against a single cutoff, including a lateral `jsonb_array_elements` over `tool_calls` for the per-tool counts and `percentile_cont` for the latency percentiles — so a 30-day report never pages rows into Python. | `summary` |
| `api/auth.py` | `POST /api/auth/login` / `logout` and `GET /api/auth/me`. Sets the HttpOnly `staff_session` cookie, answers a bad password with one generic 401 after a one-second pause, and 429s after five failures in a minute. | `login` |

## `api/evals/`, `api/forms/`, `api/tests/`

| Path | What and why | Name to know |
|---|---|---|
| `evals/golden.json` | 59 questions with expected intent, expected tool(s), an expected answer, a `category` (`standard`, `adversarial`, `multi_turn`, `multi_intent`) and a `dev`/`holdout` split, 40 and 19. | `category` |
| `evals/run.py` | Runs the golden set against a live API and reports mechanically. No LLM judge, no pass/fail gate. | `score_item` |
| `forms/generate_samples.py` | Draws the four sample PDFs with reportlab so extraction has to read a real form layout rather than a tidy key/value list. | `Form.field` |
| `forms/sample_permit_application.pdf` | The happy-path upload: complete, extracts cleanly, reaches `in_review`. | n/a |
| `forms/sample_permit_incomplete.pdf` | Deliberately missing permit type and valuation, so the demo reaches `needs_info`. | n/a |
| `forms/sample_business_tax_application.pdf` | A three-part business tax form, which is what exposed the extraction-checklist problem. | n/a |
| `forms/sample_stro_application.pdf` | A complete Tier 3 short-term rental (STRO) licence application: the fourth type's happy path, and what `scripts/smoke.sh` step 12 files. | n/a |
| `tests/conftest.py` | Sets `LIVE_DATA_ENABLED=false` before `app.config` builds its settings singleton, and resets the live HTTP cache and transport around every test. | `live_on` |
| `tests/test_application_status_privacy.py` | Flattens the status tools' result and asserts no applicant name, address, APN or contact value appears anywhere; the red team walked tracking numbers and read residents' details. | `_flatten` |
| `tests/test_fee_bounds.py` | Negative valuations and employee counts above 10,000 are refused inside the tool, and the argument schemas carry no `minimum`/`maximum` (Bedrock rejects them). | `MAX_EMPLOYEES` |
| `tests/test_upload_filename.py` | `safe_filename`: path traversal, control characters and 300-character names become a plain basename with its extension. | `safe_filename` |
| `web/e2e/dashboard.spec.ts` | Signs in, opens `/staff/dashboard` and asserts all eight KPI tiles carry a figure, then intercepts the report call to prove the 30-day button asks for `days=30` and the page re-renders with the answer. Calls no model, so it costs nothing. | `page.route` |
| `web/e2e/markdown.spec.ts` | Stubs `/api/chat/stream` with a 404 and `/api/chat` with a canned reply, so it renders a fixed markdown string with no model spend and asserts the table, one safe anchor, and that `javascript:` and `data:` links stay literal. | `route.fulfill` |
| `tests/test_config.py` | Tier-to-model mapping and the embed-endpoint fallback. | `_settings` |
| `tests/test_llm_client.py` | Drives `chat`/`chat_json`/`embed` through `httpx.MockTransport`: tool-call parsing, schema retry, cost maths. | mock transport |
| `tests/test_chat_stream.py` | The same trick with a `text/event-stream` body: deltas assemble, usage from the final chunk reaches the trace, split tool-call arguments rejoin, a preamble next to a tool call is not yielded, and a `stream_options` rejection downgrades once. | `chat_stream` |
| `tests/test_chat_stream_turn.py` | A whole turn with the model and the database faked: the event order, and that the `done` body equals what `handle_chat` returns for the same mocked model. | `stream_chat` |
| `tests/test_router.py` | The tracking-number override and every branch of `select_tier`. | `select_tier` |
| `tests/test_rrf.py` | Reciprocal rank fusion on hand-written rank lists, no database. | `rrf` |
| `tests/test_registry.py` | Schema generation and that `dispatch` returns errors instead of raising. | `dispatch` |
| `tests/test_trash_calendar.py` | Week parity, next weekday, holiday shift. | `week_letter` |
| `tests/test_business_tax.py` | Both fee tiers and the per-employee line items. | `business_tax_breakdown` |
| `tests/test_engine.py` | Legal and illegal transitions, and that events are written. | `InvalidTransition` |
| `tests/test_validators.py` | Missing required fields, address warnings, late business start. | `missing_required` |
| `tests/test_schemas.py` | Form schema shape, widget choice, the narrowed missing-fields model. | `missing_fields_model` |
| `tests/test_certificates.py` | That the renderer produces a real PDF with the tracking number in it. | `render_certificate` |
| `tests/test_stro.py` | Everything M24 added that can be asserted offline: the STRO schema and its required list, the tier/residence consistency rules, the flat per-tier fee, the `STR-` prefix and its sequence, the form schema, the narrowed gap-fill model, and the licence PDF with its tier in words. | `_validate_stro` |
| `tests/test_s3.py` | Key sanitising, without touching SeaweedFS. | `key_for` |
| `tests/test_live_geocode.py` | The resolver's fallback order (seed, geocoder, ZIP) against a mocked transport and a fake session. | `FakeSession` |
| `tests/test_live_arcgis.py` | The four live tools against canned ArcGIS payloads: address-range filter, seed fallback, RSS parse, a 500 that is an answer not a crash. | `_handler` |
| `tests/test_live_search.py` | The `*.sandiego.gov` filter (including the `sandiego.gov.evil.example` lookalike), the tag stripper, and the "not configured" path. | `is_city_url` |
| `tests/test_api_reports.py` | The reports endpoint with no Postgres: a fake session answers the eleven aggregates in order and keeps the compiled SQL, so the shape, the 1..90 bound, the staff guard, the empty window and the jsonb/percentile SQL are all asserted for free. | `FakeSession` |
| `tests/test_trash_zip_level.py` | The M8 defect end to end: a real unseeded address and a bare ZIP both get a collection day, labelled `zip-level`. | `_confidence` |
| `tests/test_ci_stub.py` | Starts `scripts/ci/stub_openai.py` as a real subprocess on a free port and drives all three endpoints over HTTP, including a `Classification` that has to validate against the real pydantic model. | `stub_url` |
| `tests/test_migrations.py` | The vector-width refusal (the message has to name `scripts/reset_demo.sh`) and `--rollback`: the down SQL and the `schema_migrations` delete in one transaction, and `.down.sql` files excluded from the forward glob. | `FakeEngine` |
| `tests/test_cors.py` | The explicit method and header lists: GET/POST/DELETE pass a preflight, PUT and PATCH are refused, an unknown origin gets nothing. | `_preflight` |

## `scripts/`

| Path | What and why | Name to know |
|---|---|---|
| `setup_ollama.sh` | Pulls the three models and builds `qwen2.5:7b-32k`, because Ollama defaults to a 4k context that truncates permit PDFs. Idempotent. | `LONG_CTX_MODEL` |
| `smoke.sh` | Eleven end-to-end checks: upload, file, route, approve, issue, download, the `needs_info` loop, the business tax path. Signs a staff member in first and keeps the cookie in a jar, because the back-office half needs a session since M11. | `wait_for_status` |
| `reset_demo.sh` | Stops the stack, deletes both volumes, restarts, waits for `/health` green with `kb_chunks > 0`. Run before a demo. | the health poll |
| `backup.sh` | `pg_dump -Fc` inside the db container plus a tar of the SeaweedFS volume, into `data/backups/<ts>-<label>/`. `reset_demo.sh` calls it before it deletes anything. | `DEST` |
| `restore.sh` | The drill that makes the backup real: restores the newest `dump.pgc` into a scratch database `civic_restore`, prints row counts from both databases side by side, drops the scratch again unless `--keep`. Never writes to `civic`. A backup nobody has restored is a hypothesis. | `count` |
| `ci/stub_openai.py` | A stdlib-only fake OpenAI server so CI can boot the whole stack for $0. Fills any JSON Schema it is handed (preferring `smalltalk`) so a turn routes instead of taking the error path, and `--embed-dim` matches whatever `EMBED_DIM` the job runs at. | `schema_from` |
| `ci/concurrency_probe.py` | Opens 20 chat streams at once and insists every one ends in a `done` event, with no 5xx and none slower than the ceiling. 20 is `pool_size + max_overflow`, which is where the SSE route deadlocks today. | `one_stream` |

## `web/`

| Path | What and why | Name to know |
|---|---|---|
| `lib/api.ts` | Typed fetch helpers and response types for every endpoint. One place turns a FastAPI `{detail}` into an `Error`. `withSessionRetry` is the other one: a 403 from a resident route means the session id is another browser's, so it rotates the id and resends exactly once. | `request<T>`, `withSessionRetry` |
| `lib/stream.ts` | `POST /api/chat/stream` read with `fetch` + `ReadableStream` and split on blank lines — not `EventSource`, which can only GET. Falls back to the buffered `POST /api/chat` on any non-200, so a stale API still answers. | `streamChat` |
| `lib/session.ts` | The resident's session id: a uuid in `localStorage`, created lazily. Residents have no account, so this is all that ties a conversation together. `resetSession()` is the recovery path when the API says the id belongs to another browser. | `getSessionId` |
| `lib/health.ts` | One `GET /health` per page load, cached as a module-scope promise so the health pill, the trace panel and `/traces` mounting together make one request. `modelLabel()` turns the tier alias into "smart · claude-sonnet-4-6" using `provider_models`. | `loadHealth` |
| `lib/auth.ts` | One hook, `useStaffSession`, that asks `GET /api/auth/me` who is signed in and sends a 401 to `/login?next=`. Called once, in the staff console layout, so the redirect rule lives in one file. | `useStaffSession` |
| `lib/reports.ts` | The dashboard's one fetch and the types for what comes back, plus the three formatters the page shares. Separate from `lib/api.ts` because the dashboard is its only consumer and the response is a dozen nested shapes. | `getReportSummary` |
| `app/login/page.tsx` | The staff sign-in form: username, password, error state, and a `?next=` return path that is rejected unless it is a same-site path. | `safeNext` |
| `app/globals.css` | The whole design system as Tailwind v4 `@theme` tokens: one navy, one amber used sparingly, the slate scale, and four named type steps. Imported once by `app/layout.tsx`. Light-only on purpose — this is projected in a room. | `@theme` |
| `app/layout.tsx` | Root layout: system font stack, and `SiteChrome` to pick the route's frame. No `next/font/google`, so the Docker build needs no network. | `RootLayout` |
| `app/page.tsx` | The chat page: quick actions, composer with attachment, replies that stream in under a status line ("routing…", "smart · claude-sonnet-4-6", "calling get_trash_schedule…"), citations, the inline form, the trace drawer. The `done` event is authoritative and replaces whatever streamed in. | `send()` |
| `app/staff/layout.tsx` | The staff console's frame: `StaffNav` plus the single sign-in gate for every page under `/staff`, so there is one `GET /api/auth/me` per console page load and one place that decides what signed-out and API-down look like. | `StaffLayout` |
| `app/staff/page.tsx` | The queue: filterable table polled every 5 s, detail panel with fields, warnings, timeline and Advance buttons. | `advance()` |
| `app/staff/dashboard/page.tsx` | The reporting page: eight KPI tiles, turns and cost per day as inline SVG bars with the exact numbers in each bar's `<title>`, intent and tier bars, tool and application tables, and the unanswered list. A 1/7/30-day selector re-asks the API. No charting library. | `DayChart` |
| `app/staff/traces/page.tsx` | The last 100 turns, one row each, expanding to tool JSON and RAG ids. | `TracesPage` |
| `app/traces/page.tsx` | The pre-M21 traces URL, kept as a client redirect to `/staff/traces` so old bookmarks and demo scripts still land. | `TracesRedirect` |
| `components/SiteChrome.tsx` | Decides which frame a route gets: the resident nav and the "City staff sign-in" footer, or nothing at all under `/staff`, where the console layout supplies its own. A client component because the root layout is a server component and cannot read the pathname. | `SiteChrome` |
| `components/ResidentNav.tsx` | The resident bar: seal, title, honesty badge, health pill. Deliberately no links — a resident clicking "Traces" and landing on a login form was the thing M21 removed. | `ResidentNav` |
| `components/StaffNav.tsx` | The console bar: Queue, Dashboard, Traces, who is signed in, Sign out, health pill. Takes the session as a prop from the layout that owns it. | `LINKS` |
| `components/CitySeal.tsx` | The city mark and the assistant avatar, drawn in CSS — a navy disc, an amber ring and a star — so the demo ships no image asset. | `CitySeal` |
| `components/HealthPill.tsx` | Polls `/health` once on mount; green only when db, s3, llm and embed are all ok. | `HealthPill` |
| `components/MarkdownLite.tsx` | Paragraphs and line breaks, nothing else. A markdown library would be a dependency and an XSS surface for two features. | `MarkdownLite` |
| `components/Citations.tsx` | Numbered chips under a reply; clicking one expands the quoted chunk. An asterisk marks an implicit citation. | `Citations` |
| `components/TracePanel.tsx` | The trace drawer: routing, tool calls, a per-model-call table with totals, RAG chunk ids. | `TraceBody` |
| `components/InlineForm.tsx` | Renders `GET /api/forms/{type}` in the conversation and posts it. Strips empty values so the validator sees "missing", not "blank". | `toPayload` |
| `components/TrackingCard.tsx` | The "we filed it" card with the tracking number and a link into the queue. | `TrackingCard` |
| `components/StatusPill.tsx` | One colour per workflow status so the queue is scannable. | `COLORS` |

## Questions a reviewer might ask, and where the answer lives

**1. How do you decide which model to use?**
`app/llm/router.py`. A small model classifies the message into an intent with a
confidence and a complexity rating. `select_tier()` escalates on confidence below 0.6,
high complexity, or more than one intent; otherwise it uses the smart tier. Extraction
always uses the extract tier. Every decision, including the reason, lands on the trace.

**2. Why not RAG for the trash schedule?**
Because a trash schedule is a row, not a passage. Embedding a table and hoping cosine
similarity returns the right address is the classic RAG failure. `get_trash_schedule` is
a SQL lookup that is exact, auditable and cheap. RAG is for policy prose, where the
answer is a paragraph someone wrote. See `DECISIONS.md`, "RAG for policy text, tools for
records".

**3. How would you scale the worker?**
Today it is one asyncio task polling every 3 s in the API process, which is a deliberate
choice: no broker to explain (`DECISIONS.md`). To scale, first add `SELECT ... FOR UPDATE
SKIP LOCKED` to the batch query so multiple API replicas can poll the same table without
double-processing. Beyond that, move the hooks behind a real queue. The engine itself
does not change, because `advance()` already owns the transaction.

**4. How do you keep the model from inventing a permit status?**
Three layers. The profile prompt says never invent a status, date, tracking number or
fee. The status only ever arrives as a tool result, and `get_application_status` returns
a written `summary` the model can quote instead of re-deriving. And the workflow replies
(tracking number, fee, missing fields) are templated in `agents/rendering.py`, not
generated at all.

**5. What happens with a scanned PDF?**
`workflows/intake.py` extracts under 50 characters, stores the row with `text=""`, and
`POST /api/documents` returns `has_text: false`. The chat replies with
`unreadable_document_reply`: it says the demo does not do OCR and offers to take the
details in conversation. No application is created. OCR is listed as a production gap in
the README.

**6. How would you swap to Bedrock?**
`cp .env.bedrock .env && docker compose --profile aws up -d --build`. That starts a
LiteLLM gateway which speaks the OpenAI protocol and maps the tier aliases (`small`,
`smart`, `escalate`, `extract`, `embed`) to Bedrock model ids in `deploy/aws/litellm.yaml`.
No application code changes. The one catch is `EMBED_DIM`: Titan returns 1024 dimensions,
the vector column is sized at migration time, so it needs a fresh DB.

**7. How do you know it works?**
Three levels. 301 unit tests with no network and no database. `scripts/smoke.sh`, eleven
end-to-end checks through the real stack, plus 13 Playwright specs against the browser. And
`evals/run.py` over 59 golden questions, 40 dev and 19 held out, scored mechanically on intent,
tool choice, citation presence, keyword overlap and literal guardrail phrases.

**8. Why no LLM judge in the evals?**
The dev provider is a 7B local model. A judge built on it would be less reliable than the
thing it is judging. Mechanical scoring is dumber but honest, and it never quietly moves.
`PLAN.md` §14.

**9. Did you tune anything to the eval numbers?**
No, and that is a written rule. Nobody edits a prompt, a router rule or a KB file because
a golden item failed. One change came out of an eval: the model did not know today's date
and searched September 2023 for "events in September". The fix was injecting the date into
every system prompt, which generalises, and it is logged in `DECISIONS.md`.

**10. Why a state machine rather than letting the agent drive the workflow?**
An application's status is a compliance artefact. A model deciding it would be
unauditable and occasionally wrong. `workflows/engine.py` owns every transition, writes an
event row for each one, and rejects illegal jumps with a 409. The model's only job in the
workflow is extraction.

**11. How do citations work, and what if the model does not cite?**
Retrieved passages go into the system prompt as a numbered Sources block, and
`citations_for()` maps `[n]` markers in the reply back to the hits. If the model wrote no
markers, the top two hits are returned flagged `implicit: true` and the UI marks them with
an asterisk and the label "used, not explicitly cited". Showing what it was given is more
honest than showing nothing.

**12. Why hybrid retrieval instead of just vectors?**
Dense search finds paraphrases; full-text finds exact strings like "SB-1186" or a form
number, which an embedding blurs. RRF fuses them without needing a calibration between two
score scales that are not comparable. `rag/retrieve.py`, and `DECISIONS.md` for why
weighted blending was rejected.

**13. What is the trace, exactly, and why does it matter?**
One row per turn holding intent, confidence, tier, model, the router's reason, RAG chunk
ids, every tool call with arguments and result, per-model-call tokens, latency and cost.
It matters because "the assistant said something wrong" is otherwise unanswerable. It is
also the honest place to show that a 7B model picked the wrong tool.

**14. What is the weakest part of this?**
The local model. The classifier confuses `general` and `service_request`, and the 7B
answerer sometimes explains how to apply without calling `start_application` (which is why
the UI has a form-hint fallback, decision 16 in `STATE.md`). Both are provider weaknesses,
both are visible in the traces, and neither is papered over with keyword rules.

**15. What would you do with two more weeks?**
OCR for scanned uploads. PII redaction before anything is written to `traces`. A larger eval
set sampled from real traffic rather than 59 questions written by hand. Getting the classifier
off the critical path so the first token arrives sooner. And a second reviewer step in the
workflow, since approve is currently one click. Streaming and staff auth were both on this
list until M11 and M12; `docs/DESIGN.md` has the current version of it.

**16. Why `hashlib.scrypt` for the staff password?**
`app/auth.py`. It is a memory-hard KDF that ships with CPython, so there is no wheel to pin,
no build step in the Docker image, and nothing extra for me to have to explain. bcrypt and
argon2 are both fine choices and both are a new dependency in a repo whose rule is that the
author can explain every file. The work factors (n=2^14, r=8, p=1) and the salt travel inside
the hash string, so re-tuning them does not need a migration. The seed loader re-hashes
`STAFF_PASSWORD` at every startup, which is why changing it in `.env` changes the login.

**17. Why server-sent events rather than WebSockets?**
`app/api/chat.py` and `web/lib/stream.ts`. The traffic is one-directional — the server emits
`status`, `tool`, `token` and one `done` — and SSE is one `StreamingResponse` over the HTTP
stack that already exists, with no second protocol, no upgrade handshake and no connection
state to manage. A WebSocket would buy bidirectional messaging I have no use for. I do not use
`EventSource`, though, because it can only GET: the page reads the stream with `fetch` plus
`ReadableStream`, which POSTs and still sends the cookie. If the endpoint answers anything but
200 the page falls back to `POST /api/chat`.

**18. Why answer trash day at ZIP level instead of refusing?**
`app/live/geocode.py`, and the "Live data" table in the README. The City publishes no
per-address collection day anywhere public, so there is no real source to be right from. The
choice was between refusing every address outside the 40 seeded rows and answering from the
ZIP with the uncertainty stated. Refusing is honest but useless; answering silently would be
dishonest. So a geocoded or ZIP-only match returns `confidence: "zip-level"` with the caveat
and a link to the City's real collection map, and the `match` field shows in the trace. The
rule generalises: degrade with the uncertainty attached, do not pretend either way.

**19. Why are some tools cross-domain and others locked to one intent?**
`app/agents/profiles.py`, `CROSS_DOMAIN_TOOLS`. The allow-list exists to give a weak model
fewer ways to go wrong, but M10's audit showed it was also why "there's a pothole at X, and
what day is the trash picked up there?" dropped its second half — the trash tool was not on
the `service_request` profile. The split that survived is by consequence, not by domain: cheap
read-only lookups (schedules, events, council district, status, referral) ride on every
profile, while anything that quotes money, opens a form or files a case stays behind its own
intent. A wrong schedule lookup wastes a call; a wrong `create_service_request` files a case
in a resident's name.

**20. You widened an eval assertion after a run. Isn't that tuning?**
No, and the distinction is written down in `DECISIONS.md` under Phase 2. Item 34's reply was
correct and the scorer's phrase list simply did not contain "wasn't able to find", so the
scorer was measuring the wrong thing. Fixing a broken measurement is not the same act as
changing the system so a specific question passes. The rule I hold to is the second one:
`PLAN.md` §14 forbids editing a prompt, a router rule or a KB file because a golden item
failed. Root causes that generalise get fixed and logged — the date injection is the one
example in this repo — and everything else is reported at whatever number it scores.
