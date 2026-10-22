# STATE.md — single source of truth for where the build is

Updated by whoever finishes a step. Keep it short. Newest status at top.

## Current
- 2026-09-20 (Fable): **Demo prepared again.** pytest 584, ruff clean, web build clean, smoke 13/13
  before the reset; `reset_demo.sh` (backup taken, readiness check fixed for the M14 /health shape);
  after: warm-up 2.9 s, staff login 200, queue 10 seeded rows across four types, dashboard live, six
  demo questions correct including the new library-card answer, 14 non-mutating Playwright specs
  green. Brave tidied over CDP (21 tabs closed), staff signed in, six tabs open: chat, queue,
  dashboard, traces, demo kit, systems map; Finder on the sample documents. Note: `/tmp/dockercfg`
  had lost its config.json (tmp cleanup), so compose fell back to the bare CLI; regenerate it with the
  snippet in `scripts/demo_up.sh` if `docker compose` prints "unknown shorthand flag".
- 2026-09-16 (Fable): **Pushed to GitHub; all four PR workflows green on main** (api, web, security
  with Trivy image scans and gitleaks, compose-smoke with the full stack, stub-mode smoke and the
  20-stream probe: 1.8 s, zero 5xx). Three CI-only fixes on the way: `web/public/.gitkeep` (the image
  COPY needed the directory), `trivy-action@v0.36.0`, `pull-requests: read` for gitleaks and a push
  trigger for security; images now `apt-get upgrade` / `apk upgrade` at build and the web runner drops
  npm, so the scans are clean; the stub-mode smoke sends the resident cookie jar. The probe's
  `continue-on-error` is removed, so it gates. Dependabot opened six PRs, five of them majors (Node
  26, Python 3.14, TypeScript 7, ESLint 10); `dependabot.yml` now ignores semver-major, which
  Dependabot will close on its next run; the minor-and-patch group PR #3 is worth merging after CI.
  **Author's clicks:** branch protection with required checks `api`, `web`, `security`,
  `compose-smoke` (names in `scripts/ci/README.md`); `AWS_ROLE_ARN` only if e2e and the nightly
  eval should run.
- 2026-09-15 19:00 (Fable, handoff): **Phase 4 production readiness complete on main; stack rebuilt
  and verified.** M20-M27 merged (sessions bound to an HMAC cookie; resident app and staff console
  split with a reporting dashboard and `GET /api/reports/summary`; ten real gap questions closed with
  KB content, kb_chunks 133; STRO licence as the fourth type; stream deadlock fixed with 429 admission
  control, heartbeats, Pacific clock, per-IP limits, idempotency keys, worker SKIP LOCKED, retention
  setting; CI runs the full stack with a stub model, a 20-stream probe and Trivy; down migrations and
  a restore drill; categories from the seed table). Main: pytest 584 + load test, ruff and format
  clean, web typecheck/lint/build clean, compose config clean, 12 migration files. Rebuilt stack:
  TZ America/Los_Angeles, smoke 13/13, Playwright 23/23 after the fix below, 20 concurrent real-model
  streams in 9 s with 16 served and 4 turned away (429), zero errors. **Regression caught on the
  rebuilt stack and fixed the same hour:** the first heartbeat wrapper reset the trace ContextVar
  from another task, so every streamed turn ended in the fallback; 574 mocked tests missed it, the
  browser test caught it; the load test now asserts complete turns. Research: `research/08`, `09`,
  `10`; hostile review in `docs/HARDENING_AUDIT.md`. Demo kit v2 (five tabs, both production shapes,
  criteria scorecard, review statuses) at https://claude.ai/code/artifact/228a95e3-b536-4e7a-a375-08d8d75da6c2,
  `docs/DEMO_KIT.html`, and `~/Downloads/Municipality Agent Demo/` (kit, script, production plan,
  four sample PDFs, diagrams, reference folder with audits and research). Phase 4 spend about $1.5.
  **Open by choice:** login throttle in-process; router flips to smalltalk on a developer-mode
  wrapper; English only; retention defaults to keep; TLS documented, not built. **Next:**
  `gh auth login -h github.com`, `git push origin main`, open a PR so the six workflows run (Trivy is a
  hard gate and may need a base-image bump), pick the required checks named in `scripts/ci/README.md`,
  configure `AWS_ROLE_ARN` if e2e and the nightly eval should run.
- 2026-09-14 20:00 (Fable, handoff): **Phase 3 hardening complete on main, stack rebuilt and verified.**
  M14-M19 merged. Main: ruff and format clean, pytest 422, web typecheck/lint/build clean, 7 migrations.
  Rebuilt from final main with the new images: all five containers healthy, non-root (uid 10001),
  `restart: unless-stopped`, memory limits, loopback-bound Postgres/S3/LiteLLM. Verified on the rebuilt
  stack: `/health` free and green, `/health/deep` 401 anonymous and green as staff (Bedrock reachable
  through the credentials-file mount), an injection wrapper answered the legitimate half and refused
  the rest, an $80k permit question quoted only the tool's $1,250 and cited the KB for the plan-check
  percentage, a 5,000-char message and a `../etc` session id are 422s, `scripts/smoke.sh` 11/11,
  Playwright 18/18 (run before M16/M19 on the round-1 build; markdown/smoke/api-down specs are
  model-free and worth re-running once). Hardening eval: guardrail 100%, numbers_from_tools 100%,
  intent 84% (label strictness, not tuned). Phase 3 spend about $4.3 of $5.
  **Open, by choice:** router flips to `smalltalk` on a "developer mode" wrapper (hardening id 60);
  intent labels on six hardening items are stricter than the router's defensible choice; 15 of 43
  hardening replies exceed 6 s (Sonnet plus tool rounds); litellm `:4000` loopback was Fable's
  one-word addition. **Next:** `gh auth login -h github.com`, `git push origin main`, open a PR from a
  branch to see the four workflows run, then click the branch-protection settings in
  `scripts/ci/README.md`; configure `AWS_ROLE_ARN` (OIDC) if the e2e and nightly eval jobs should run.
  The six `worktree-agent-*` branches are merged and can be deleted after the push.
- 2026-09-14 18:10 (Fable): **Phase 3 round 1 merged and verified.** M14, M15, M17, M18 on main
  (M17's repo-wide ruff format re-run on merged main instead of merging 46 reformatted files). Main:
  ruff clean, format clean, pytest 380, web typecheck/lint/build clean. Stack rebuilt from main:
  migration 006 applied, sequences live, `X-Request-ID` on every response, CSP and nosniff headers
  served, `scripts/smoke.sh` 11/11, Playwright 18/18 (3 new api-down, 1 hostile markdown). Round 2
  dispatched: M16 (config/secrets/compose/docker/deploy) and M19 (source fences, hardening golden
  category, live runs, ~$3.30). **Push still blocked**: `gh auth login -h github.com` needed; then
  push main and the six `worktree-agent-*` branches (or just main) and open a PR to trigger the
  workflows. Decisions in DECISIONS.md "Phase 3 hardening, round 1".
- 2026-09-14 15:30 (Fable): **Phase 3 hardening started.** Two read-only audits (`docs/HARDENING_AUDIT.md`)
  found ~60 gaps; six serious: unbounded message/document_ids, 600 s model timeout, `/health` bills a
  model call per probe, client-chosen session id reads any session's history, seed TRUNCATE wipes
  resident rows on every restart, EC2 script leaves CORS broken and ports open. Specs in PLAN.md §12.2
  (M14-M19), probe set in `docs/HARDENING_PROBES.md`. Author's answers: one week, $5 Bedrock, GitHub
  Actions with agents pushing branches, AWS stays scripted. Round 1 dispatched in worktrees: M14 (API
  bounds/timeouts/cost/health/observability), M15 (workflow + data integrity), M17 (CI/CD + ruff), M18
  (web hardening). Round 2 after merge: M16 (config/secrets/compose/docker/deploy), M19 (injection
  fences + hardening golden category, the only milestone that spends Bedrock).
- 2026-09-14 11:30 (Fable): **Demo prepared for today.** Playwright e2e 14/14 on the live container
  (:3001, real Bedrock), then `scripts/reset_demo.sh` wiped and reseeded (health green, kb_chunks 120,
  8 seeded applications, 1 warm-up trace), then smoke/traces/responsive specs 5/5 on the reset stack,
  warm-up turn 3.7 s, staff login 200. Demo kit copied to `~/Downloads/Municipality Agent Demo/`
  (3 sample PDFs, systems map html+png, walkthrough html, DEMO_SCRIPT.md, README.md). A new Brave window
  holds login, chat, staff, traces, systems map, walkthrough; Finder is on the sample documents.
  Browser tab cleanup by AppleScript was blocked: macOS raised "Terminal wants access to control
  Google Chrome / Brave" prompts that nobody could answer from a shell, so other windows are still open
  and the author closes them by hand. Brave shows a pending "Update" button; do not restart it before
  the demo.
- 2026-09-14 evening (Fable): **Demo-week systems map built; stack re-verified; spend script fixed.**
  One-page systems diagram for screen share at
  https://claude.ai/code/artifact/d4fe819f-0654-446f-9ef0-074b310c443e (source `docs/SYSTEMS_MAP.html`,
  screenshot `docs/verification/12-systems-map.png`). Two Playwright QA passes: no clipped text, no
  overlapping labels, arrows land on lane edges, dark theme clean. Opus verifier re-ran everything on the
  live stack: pytest 302, lint/build clean, smoke 11/11, 6 demo questions correct (one escalated to Opus
  on a multi-intent turn as designed), streaming OK (first token ~3.3 s today), auth 401/200 correct,
  0 tracebacks in 24 h of api logs. 12 Bedrock turns, $0.21. **Defect fixed:** `scripts/spend.sh`
  filtered Cost Explorer on the service "Amazon Bedrock", which carries only platform cents; model usage
  bills under per-model services. It now groups by service and totals every Bedrock line. Real September
  spend for this project's models (Haiku 4.5 + Sonnet 4.6 + Opus 4.6) is about $9.74, ~15% above the
  app-side estimate of $8.30; the whole account shows $11.49 because Sonnet 4.5 / Opus 4.5 lines belong
  to another project. Do not quote "about $5" in demo beat 11. Before a cold-start demo: run
  `bash scripts/demo_up.sh` by hand from Terminal, then sign in at http://localhost:3001/login (staff/staff)
  in the browser; the script only checks login over curl.
- 2026-09-14 (Fable, handoff): **Post-presentation. Nothing in progress, no blockers.** Checks run
  today: pytest 302 passed, `npm run lint` clean, `npm run build` clean, `/health` green (kb 120),
  `scripts/smoke.sh` 11/11 PASS, api log 0 errors. Spend all-time $8.09 by app estimate (+$0.74
  deleted rows = ~$8.83). **The launchd demo job did NOT run on 2026-09-08**: macOS refused
  `bash` access to a script under ~/Desktop ("Operation not permitted", TCC); the job is removed.
  `bash scripts/demo_up.sh` by hand works and was tested twice on 09-07. No traces were recorded on
  09-08, so the presentation either ran elsewhere or used the pages without new turns. Next: the
  author decides whether to keep the stack running, add a Brave key, or archive (see
  ASSUMPTIONS.md questions 5-7).
- 2026-09-07 18:45 (Fable): **Demo bring-up automated.** `bash scripts/demo_up.sh` starts Docker
  Desktop if needed, `docker compose up -d` (no build), waits for health and kb_chunks 120, warms
  Bedrock with one smalltalk turn, checks staff login, and opens chat, staff, traces, the walkthrough
  artifact and `api/forms/`. Tested twice today. A launchd job
  (`~/Library/LaunchAgents/com.municipality.demo-up.plist`, copy in `scripts/`) runs it once at
  **2026-09-08 17:30**; log in `data/demo_up.log`. Remove with `launchctl unload` after the demo.
- 2026-09-07 11:00 (Fable): **Pre-presentation verification done and four defects fixed.**
  Opus verifier ran smoke 11/11, 18 edge-case probes (16 correct, 3 partial, 0 wrong), streaming
  (first token 1.77 s), the staff workflow through the API, and 11 container screenshots; report at
  `docs/verification/2026-09-07-e2e.md`, $0.62. Fixed and rebuilt into the containers: wrong
  weekday on a holiday-shifted recycling date (the only factual error), traces table hiding
  Tokens/Latency/Cost when expanded, raw markdown in the traces detail (now rendered, raw behind a
  toggle), snake_case keys in the staff detail. 302 tests. Walkthrough page for the author:
  https://claude.ai/code/artifact/bc49c3c8-c01c-4de3-9d04-3405c441070e (also
  `docs/verification/walkthrough.html`). Presentation 2026-09-08; run `docs/DEMO_SCRIPT.md`.
- 2026-09-05 17:15 (Fable): **Phase 2 complete. M6-M13 merged; containers rebuilt from f0c22e9.**
  Health green (kb_chunks 120), pytest 301, web lint/build clean, Playwright 14/14 on the live stack,
  0 tracebacks. Golden set 59 items (40 dev / 19 holdout); last standard-category run 96.9% intent /
  100% tool / 100% cite / 100% kw / 100% guardrail; multi_intent and multi_turn tool 100% after M10;
  red-team items 56-58 pass after M13b. Spend for the day about $6.4 by app estimate plus $0.74 of
  deleted red-team rows; phase-2 total about $8.07 of the $10 cap. Staff login staff/staff.
  Next for the author: read docs/DESIGN.md and rehearse docs/DEMO_SCRIPT.md on the Mac mini; decide
  on a Brave key (`SEARCH_PROVIDER=brave`, `SEARCH_API_KEY`) for the web-search tool; optional:
  opaque tracking numbers, city-name-without-ZIP geocode guard, dangling-citation cleanup (red-team
  16/17/22/23 still open by choice). Nothing is blocked.

## Spend ledger (Bedrock, app-side estimate from `bash scripts/spend.sh`; budget $10 for phase 2)
| When | Who | What | Turns | Est. $ | Running total |
|---|---|---|---|---|---|
| 2026-09-02..03 | all | M2-M5 evals, smoke, manual | 108 | 0.99 | 0.99 |
| 2026-09-05 10:20 | Fable | 12 live probes | 12 | 0.28 | 1.27 |
| 2026-09-05 11:10 | M6+M7 agents | 4 + 3 verification probes | ~7 | ~0.15 | ~1.42 |
| 2026-09-05 10:40 | M9 agent | 52-item baseline eval | 64 | 1.02 | 2.44 |
| 2026-09-05 12:30 | M8 agent | 8 probes + 32-item eval + retries | 46 | 1.03 | 3.46 |
| 2026-09-05 13:15 | Fable | 54-item eval on rebuilt main container | 66 | 1.30 | 4.85 |
| 2026-09-05 13:20 | spend.sh | running total incl. M10 in progress | 310 | — | 5.23 |
| 2026-09-05 13:40 | docs agent | 6 demo-script probes | 6 | 0.14 | — |
| 2026-09-05 14:00 | M10 agent | 5 category eval runs + 2 probes | 50 | 1.27 | 6.20 (spend.sh after M10) |
| 2026-09-05 14:10 | Fable | standard-category eval on final container | 32 | 0.74 | **6.94** |
| 2026-09-05 15:30 | M12 agent | 3 TTFT probes + smoke + 2 e2e | ~15 | 0.12 | ~7.1 (+ M11/red-team, in progress) |
| 2026-09-05 15:35 | red-team agent | 35 probe turns deleted from `traces` (session_id rt-%) to tidy the demo pages, cost recorded client-side before deletion | 35 | 0.74 | — |
| 2026-09-07 10:00 | verifier + Fable | smoke, 18 probes, streaming, 4 screenshot turns, 2 checks | ~30 | 0.66 | ~8.75 |
| 2026-09-05 17:10 | M13b agent + Fable | golden 56-58 (3 turns) + full Playwright 14/14 (5 turns) | 8 | 0.21 | **~8.07 final** (spend.sh 7.33 + 0.74 deleted) |
| 2026-09-05 16:30 | red-team agent | 36 chat turns (35 deleted, see below, + 1) | 36 | 0.77 | ~7.9 |
| 2026-09-05 16:10 | M11 agent + Fable | M11 verification (3 turns) + 1 streaming check on the rebuilt stack | 4 | 0.09 | ~7.86 (spend.sh + 0.74) |
| 2026-09-05 15:40 | note | spend.sh therefore understates by $0.74 from here on; honest app-side total after the red team = spend.sh + 0.74 (about **7.77** at 15:40). No agent may delete traces rows again. | | | |

## Milestone status
| M | Status | Notes |
|---|---|---|
| research | done | research/01-04 + 00-synthesis |
| M1 infra/api skeleton | done | compose 4 services, migrations, models, seed loader, S3, LLM client, /health all green, 24 tests |
| M2 RAG/tools/router/chat | done | ingest at startup, hybrid RRF retrieval, 11 tools, classifier + tier rules, `/api/chat` `/api/traces` `/api/forms`, eval runner; 68 tests |
| M3 workflows/intake | done | engine + asyncio worker, doc/form intake, validators, reportlab certificates, `/api/applications` `/api/documents`, 3 sample PDFs, smoke.sh 11/11 PASS; 100 tests |
| M4 web | done | Next.js 16 app: `/` chat (citations, trace panel, upload, inline form), `/staff` queue (polled 5s), `/traces`; `npm run build` + eslint clean; container answers 200 on :3001. Design pass + 13 Playwright e2e + 7 screenshots added 2026-09-03 |
| M5 docs/deploy | done | README (150 lines), 4 docs, deploy/aws up/down + README, reset_demo.sh, litellm exercised against real Bedrock |

## Environment notes (bit us once, will bite again)
- **`docker` hangs in a non-interactive shell.** `~/.docker/config.json` sets
  `credsStore: "desktop"`; the helper blocks on the macOS keychain when there is no GUI
  session, so `docker pull` / `docker compose build` hang with zero output. Workaround used
  for verification: `cp -R ~/.docker /tmp/dockercfg`, delete the `credsStore` key, then
  `DOCKER_CONFIG=/tmp/dockercfg docker compose ...`. Interactive use on the Mac is fine.
- SeaweedFS is started with `-ip=seaweedfs`, so it does **not** listen on loopback inside its
  own container; the healthcheck has to probe `http://seaweedfs:9333/cluster/status`.
- Docker Desktop was restarted during M1 debugging; an unrelated Postgres container
  was restarted afterwards and is back up.

## Decisions needed (spec was silent; simplest reading taken — say the word to change)
Web design pass (spec was silent, simplest reading taken):
34. The chat no longer opens with a greeting *message*; the greeting is the empty state, so
    "New conversation" leaves an empty list. Tests assert on the empty state, not a first bubble.
35. Staff Advance buttons are labelled with a verb ("Approve", "Reject", "Issue certificate") and
    carry `data-advance-to` with the raw status; the raw status is still what is sent.
36. `e2e/screenshots/*.png` are committed; `playwright-report/` and `test-results/` are not.

1. Primary keys are `BIGSERIAL`, not UUIDs (readable ids in the staff UI and in demos).
2. `kb_chunks.embedding` uses an **hnsw** index, not ivfflat: the table is empty when the
   migration runs and ivfflat needs rows to train its lists.
3. `001_init.sql` writes `vector({{EMBED_DIM}})`; `migrations.py` substitutes the env value.
   Changing `EMBED_DIM` therefore needs a fresh DB (`rm -rf data/volumes/pg`).
4. Event `date` is a real `DATE`; `start_time`/`end_time` stay `TEXT` ("09:00").
5. `chat()` takes an optional `client=` argument purely so tests can inject a mock transport.
6. `.env` is a copy of `.env.ollama` (gitignored) so `docker compose up` works on a fresh clone
   only after `cp .env.ollama .env` — the README (M5) must say this.

M2 (spec was silent, simplest reading taken):
7. Migration `002_traces_m2.sql` adds `reason`, `error`, `calls`, `document_ids` to `traces`;
   001 had no columns for the router's reason, the per-call breakdown, or a failed turn.
8. Chunk overlap is *whole trailing paragraphs* up to 150 chars, not a raw 150-char slice, so a
   window never begins mid-sentence.
9. `dispatch()` also converts an *exception inside a tool* into `{"error": ...}`, not just bad
   arguments — the tool loop needs a dict either way and a resident should never see a 500.
10. Generated tracking numbers are "one past the highest existing", with a floor per type. Only
    `service_request` has a floor (000400, per spec); permits/BTC continue from the seeded rows.
11. `estimate_permit_fee`'s argument is literally named `permit_type_code_or_name` (M2 spec) even
    though PLAN.md §8 abbreviates it to `permit_type`.
12. `general` and `smalltalk` map to no KB topic; `service_request` maps to KB topic
    `service_requests` (the intent name and the topic name differ by one letter).
13. `retrieve()` takes the session as its first argument (the spec's signature omitted it).

M4 (spec was silent, simplest reading taken):
14. `NEXT_PUBLIC_API_URL` is a Docker **build arg**, not just a runtime env var: Next inlines
    `NEXT_PUBLIC_*` at build time, so a runtime-only variable would never reach the browser.
    Compose passes it both ways; changing it needs `--build`.
15. The API emits `{"action": ...}` in `actions[]`; the M4 spec called the key `type`. The UI
    reads `a.action ?? a.type` so either shape renders.
16. Quick-action form fallback: if a turn returns no `render_form` action but the reply mentions
    a form/application/permit/certificate/request, the hinted form is rendered anyway. The local
    7b model often answers "here is how to apply" without calling `start_application`.
17. The attachment chip shows the length of `text_preview`, which the API caps at 300 chars, so
    it renders "300+ chars extracted" at the cap rather than claiming an exact count.
18. The session id lives in a ref, not React state: it is never rendered, and reading
    `localStorage` during the static prerender would only produce a hydration mismatch.
19. Staff detail re-reads `GET /api/applications/{id}` after an advance, because
    `POST /advance` returns the row without `events` or `allowed_transitions`.
20. Fonts are the system stack, not `next/font/google`: the Docker build has no reason to need
    the network, and the brief asked for a system font.
M5 (spec was silent, simplest reading taken):
29. `scripts/reset_demo.sh` uses a plain string for the optional `--build` flag, not a bash
    array: macOS ships bash 3.2, which errors on an empty array expansion under `set -u`.
30. `reset_demo.sh` does **not** rebuild by default. The api Dockerfile `COPY`s `seed_data/`
    and `kb/` into the image, so editing seed data needs `bash scripts/reset_demo.sh --build`.
    This bit once during M5 verification: the first reset re-seeded the old statuses.
31. `deploy/aws/down.sh` leaves the IAM role and instance profile in place. They cost nothing
    and re-creating them costs a 10s propagation wait on every `up.sh`; the script prints the
    four commands to remove them by hand.
32. `.env.bedrock` gives `extract` its own LiteLLM alias pointing at the same Haiku as `small`,
    so the extraction tier can be repointed without touching the app.
33. Seeded PRM-2026-000101 became `rejected` (was `submitted`), BTC-2026-000202 and
    SR-2026-000302 became `in_review` (were `routed`/`validating`). The eight fixtures now
    cover all six manual statuses and the worker leaves every one of them alone.

M3 (spec was silent, simplest reading taken):
21. `store_document` still returns a `Document`; `bool(doc.text)` *is* the "scanned PDF" flag the
    spec asked for, so there is no second return value to keep in sync.
22. Intake actions carry BOTH `"type": "application_created"` (the M3 spec) and
    `"action": "application_created"` (the M2 shape `rendering.actions_from` already emits), so
    the web app can switch on either.
23. `AUTO["validating"]` is None, so the worker calls `engine.run_auto`, which re-runs the
    `validating` hook for a row stuck there. That is both the normal path and crash recovery.
24. `seed_data/sample_applications.json` was rewritten to use the `workflows/schemas.py` field
    names (`applicant_name`, `valuation_usd`, `address`, `employees`, `ownership_type`, ...).
    The M1 file used the research §1 names, so the M3 validator would have marked every seeded
    row incomplete. PLAN.md §13 makes the pydantic models the single definition, so the seed
    follows them.
25. The worker advances seeded rows whose status is automatic: on every startup
    PRM-2026-000101 goes submitted -> routed, SR-2026-000302 validating -> routed, and
    BTC-2026-000202 routed -> in_review. That is the worker doing its job, not a bug.
26. Generated tracking numbers now floor at 000400 for **all three** types (M2 decision 10 only
    floored service requests), so PRM/BTC numbers never collide with the fixtures either.
27. `create_service_request` (chat tool) now calls `engine.submit`, so it no longer sets the
    department itself — the validator does, ~3s later. The tool still reports the department it
    looked up, so the resident sees it immediately.
28. The extraction prompt lists the field names and descriptions explicitly, not just the JSON
    schema. Without the checklist qwen2.5:7b-32k filled Part 1 of the business tax form and
    nulled Parts 2-3 (verified 3/3 runs before and after). This is a root-cause prompt fix, not
    eval tuning — no golden item touched it.


Bedrock switch (spec was silent, simplest reading taken):
34. `chat_json`'s json_object fallback is **sticky per model name**, not per call. Bedrock's
    Anthropic models reject `minimum`/`maximum` on a number in a `json_schema` response_format
    (the classifier's `confidence` field), so without a memo every single turn would pay a
    wasted 400 first. The model name is added to a module-level set on the first rejection.
    Nova Lite accepts `json_schema` and is never downgraded.
35. The fallback also had to strip a ```json fence: `{"type":"json_object"}` is an instruction
    rather than a grammar on Bedrock's Anthropic models, and they fence their JSON. `_unfence()`
    in `client.py` handles it; without it the fallback validated 0/2 attempts.
36. `provider_model` was **not** added to the trace. `LLM_PRICES_JSON` is typed
    `dict[str, dict[str, float]]` in config.py, so carrying the Bedrock id in it would have meant
    a config type change plus a new `LLMResult` field plus a trace column — not the one-line
    change the spec allowed. The underlying ids are one file away in `deploy/aws/litellm.yaml`.
37. `reset_demo.sh` takes optional trailing service names (`--build api litellm`). When given it
    `docker compose rm -sf`s only those plus db/seaweedfs (which own the volumes) instead of a
    project-wide `down`, so a reset can leave someone else's `web` container running.
38. `/health` still reports only the four chat tiers in `models`; `EMBED_MODEL` is not in that
    map. Unchanged from M1 — adding it would change the contract the web app reads.

## Known defect (found in M2, FIXED in M3)
- **The assistant did not know today's date.** Fixed: `rendering.today_line()` appends
  `Today is <Weekday>, <YYYY-MM-DD> (America/Los_Angeles).` to the system prompt on every
  request, after the static preamble and the sources block. Re-running the evals moved dev
  keywords 90.0% -> 95.0%; nothing else was touched.

## Review findings
- M5 (Fable, 2026-09-03): accepted. LiteLLM→Bedrock verified once locally for all four tiers plus embeddings.
- M3+M4 (Fable, 2026-09-03): accepted. pytest 100, smoke 11/11, web builds and serves. Must-fix carried into M5: permit fee seed magnitudes (done by Fable), seeded application statuses limited to manual states (done in M5), LiteLLM gateway exercised locally once (done in M5, results below).
- M2 (Fable, 2026-09-02): accepted. Eval dev 80/80/100/90, holdout 90/90/100/100 (intent/tool/citations/keywords). Must-fix carried into M3: inject today's date into the system prompt. Decisions 7-13 stand.
- M1 (Fable, 2026-09-02): accepted as-is. Decisions 1-6 stand. No must-fix items.

## Log
- 2026-09-03 09:30 design-review defects fixed (Opus). Three defects Fable found in the
  screenshots, all fixed and verified: (1) the staff detail listed fields in the stored JSON's
  arbitrary key order (APN first, applicant name seventh) — the panel now fetches
  `GET /api/forms/{type}` (cached per type at module scope) and renders fields in pydantic schema
  order with the schema's labels; keys not in the schema fall to the end, A-Z; null still renders
  as an em dash. (2) The pinned Actions bar overlapped the Timeline — the panel is now a flex
  column (header `shrink-0`, body `flex-1 overflow-y-auto`, actions `shrink-0` with a top border);
  verified with a 6-event timeline scrolled to the bottom: last entry bottom 677px, actions top
  693px, no overlap. (3) The trace showed `Model: smart`, the LiteLLM alias, not the model that
  answered — new `LLM_PROVIDER_MODELS_JSON` setting (alias -> label, default `{}`) in
  `api/app/config.py`, exposed as `provider_models` in `GET /health`, set in `.env.bedrock` and
  copied to `.env`; a new `web/lib/health.ts` caches one `/health` per page load and the trace
  panel, the traces table and the health-pill tooltip now read `smart · claude-sonnet-4-6`
  (plain alias when there is no label, so the Ollama profile is unaffected).
  Checks: `npm run lint` clean, `npm run build` clean, `npx playwright test` **13 passed**,
  `uv run pytest -q` **100 passed**, `/health` green with `provider_models` present, api and web
  containers rebuilt (`localhost:3001` serves the fictional-data badge, `/staff` 200).
  Screenshots regenerated — `05-staff-detail.png` and `02-chat-conversation.png` show the fixes.
- 2026-09-03 09:10 web design pass + e2e done (Opus). Design: new token system in
  `app/globals.css` (navy `#0f2f4f` primary, amber `#d97706` accent, slate neutrals, four named
  type steps), navy nav with an accent-underlined active link + health pill + "demo — fictional
  data" badge, CSS-only city seal as the assistant avatar and nav mark, chat empty state with the
  quick actions, inline trace panel with a monospace key/value grid, sticky-header zebra tables on
  `/staff` and `/traces`, slide-in staff detail panel (Fields / Warnings / Timeline / Actions with
  a pinned action bar), responsive to 390px. Tests: `web/e2e/` — smoke, chat, quick-actions,
  upload, staff, traces, responsive, screenshots. **`npx playwright test` 13 passed, 0 failed**
  (1.1m, against the Bedrock API on :8080 and a dev server on :3002). `npm run lint` clean,
  `npm run build` clean. Seven screenshots in `web/e2e/screenshots/` (git-tracked).
  UI bugs found and fixed while testing: (1) the sticky composer overlapped the conversation on a
  tall page — the chat column now owns its own scroll; (2) `**bold**` and `- ` bullets rendered as
  literal markdown in every answer — `MarkdownLite` now handles bold, inline code and both list
  kinds; (3) the staff detail printed the string `null` for every unextracted field — now an em
  dash; (4) the composer refused to send an attachment without typed text; (5) `window.prompt` for
  the advance note replaced with a real field; (6) `next dev` was writing `AGENTS.md`/`CLAUDE.md`
  into `web/` and painting a dev badge into every screenshot. Also: `web/Dockerfile` now sets
  `PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1` so `npm ci` in the image does not pull a Chromium.
  Not done: the web container was not rebuilt (compose is another agent's).
- 2026-09-03 16:10 Bedrock live (Opus). `.env` is now `.env.bedrock`; the whole stack runs on
  real Bedrock us-west-2 through LiteLLM. Changed: `deploy/aws/litellm.yaml` (extract ->
  `bedrock/us.amazon.nova-lite-v1:0`, explicit `aws_region_name: us-west-2` on all five,
  `drop_params: true`), `.env.bedrock` (`COMPOSE_PROFILES=aws`, Nova Lite prices,
  EMBED_DIM 1024), `docker-compose.yml` (litellm healthcheck on /health/liveliness;
  api `depends_on` litellm `condition: service_healthy, required: false`),
  `scripts/reset_demo.sh` (optional service scoping + profile notes),
  `api/app/llm/client.py` (json_object fallback + `_unfence`), README, PLAN §4,
  deploy/aws/README.md.
  **One real failure, found and fixed:** every non-tracking-number turn 400'd with
  `output_config.format.schema: For 'number' type, properties maximum, minimum are not
  supported` — Bedrock's Anthropic models validate the JSON Schema and `Classification.confidence`
  is `Field(ge=0, le=1)`. First eval run scored dev intent 0.0% / tool 45.0% because of it.
  Fixed with the fallback the task authorised: on a 400 about the response format, retry once
  with `{"type":"json_object"}` and the schema in the system prompt, remember the model, and
  strip the code fence the model wraps its JSON in. Nova Lite (`extract`) never needs it —
  `json_schema` works there natively, which is how the 12-field extraction below ran.
  Verification, all commands real:
    - `/health` db/s3/llm/embed=ok, kb_chunks=82, models {small,smart,escalate,extract}.
    - Five LiteLLM aliases answered directly; Titan returned 1024 dims.
    - Upload `sample_business_tax_application.pdf` -> chat -> BTC-2026-000400, trace `calls`
      shows tier `extract` (1477/195 tokens, 1397ms, $0.000135), **12 non-null fields**, fee $43.88.
    - `bash scripts/smoke.sh` 11/11 PASS, 0 failures.
    - `cd api && uv run pytest -q` 100 passed.
    - Eval (30 items, nothing tuned): dev n=20 intent 95.0% tool 90.0% citations 100.0%
      keywords 100.0% mean 6101ms cost $0.3486; holdout n=10 intent 90.0% tool 100.0%
      citations 100.0% keywords 100.0% mean 6265ms cost $0.1505; total $0.4991.
      Side by side with the qwen2.5:7b run of 2026-09-03 05:50 in README "Evals".
    - Total observed spend for the whole session, summing `cost_usd` over
      `GET /api/traces?limit=100` (81 traces: the failed first eval, the good eval, smoke and
      the manual checks): **$0.6852**.
  Left running: db, seaweedfs, litellm, api (and the `web` container another agent owns).
  Not verified by me: `web/`, untouched on purpose.
  Nova Lite's $0.06/$0.24 per 1M was confirmed against `aws pricing get-products
  --service-code AmazonBedrock` (USW2-NovaLite-input-tokens / -output-tokens, published
  2026-09-01). The Anthropic and Titan models are not in that API's `model` attribute list,
  so those four prices are list prices as of 2026-09 and say so in `.env.bedrock`.
- 2026-09-05 16:10 M12 + M11 merged, api and web containers rebuilt from 5eb0ed2, `.env` re-synced (STAFF_*, WEB_ORIGIN): health green, kb 120, `/api/traces` 401 -> login -> 200, `/api/chat/stream` streams tokens, all four web routes 200, 0 tracebacks. Full Playwright run deferred to the final verification to save spend.
- 2026-09-05 14:10 M10 merged, api rebuilt, standard category re-run (Fable): intent 96.9% (item 2 labelled service_request, defensible), tool 100%, citations 100%, keywords 100%, guardrail 100%, $0.74. Item 24 passes with its new content check. Results `api/evals/results/2026-09-05T18-25-08Z.json`.
- 2026-09-05 13:15 api + web containers rebuilt from main f890c9e (Fable), `.env` re-synced from `.env.bedrock` (LIVE_DATA_ENABLED, SEARCH_PROVIDER), KB re-ingested: health green, kb_chunks 120, web 200, 0 errors. Full eval (54 items): standard n=32 intent 96.9% tool 93.8% cite 100% kw 100% guardrail 100%; adversarial 80/100/100/90/90; multi_turn 100/83.3/100/83.3/100; multi_intent 100/50/100/100/100; all 94.4/88.9/100/96.3/98.1, $1.30. Standard is up from the pre-M6 baseline (93.3/93.3/96.7/96.7); multi_intent unchanged, M10 owns it. Results file `api/evals/results/2026-09-05T18-13-25Z.json`.
- 2026-09-05 11:40 M9 merged (Fable). golden.json conflict resolved in favour of M6's wording with M9's `category` key; item 34's `must_contain_any` widened (scorer near-miss on "wasn't able to find", an assertion bug, not tuning); docs/EXPLAINER.md count updated to 52. Rebuild of the api container deferred until M8 lands: M8 reseeds the shared db with a new `zips` column and a main-branch container start would truncate it mid-verification.
- 2026-09-05 11:15 M6 + M7 merged to main (Fable). Not yet rebuilt into the running api container: waiting for M9's baseline eval to finish against :8080 first, then `docker compose up -d --build api` and `ingest --force` (trash_zones notes and trash.md text in the live DB are still pre-M6 until then).
- 2026-09-02 20:30 research done, repo created, plan written (Fable)
- 2026-09-02 21:40 M1 done (Opus): compose (db/seaweedfs/api/web) up; `/health` returns
  db=ok s3=ok llm=ok embed=ok, models map correct; `uv run pytest -q` 24 passed;
  api logs clean (migration applied, bucket created, all 8 seed files loaded);
  `bash scripts/setup_ollama.sh` created qwen2.5:7b-32k. Web placeholder answers 200 on :3001.
- 2026-09-03 04:55 M2 done (Opus): `docker compose up -d --build` green, `/health` kb_chunks=82;
  `uv run pytest -q` 68 passed; api logs clean (no tracebacks). Four verification curls all
  answered with the right tool and citations. Eval (30 items, qwen2.5:7b via Ollama):
  dev n=20 intent 80.0% tool 80.0% citations 100.0% keywords 90.0% mean 7487ms;
  holdout n=10 intent 90.0% tool 90.0% citations 100.0% keywords 100.0% mean 5851ms; cost $0.
  Nothing was tuned to those numbers.
- 2026-09-03 05:15 M4 done (Opus): `web/` scaffolded with create-next-app (Next 16, TS, Tailwind 4,
  no extra deps). `npm run build` clean; `npx eslint .` clean (0 problems); `npx tsc --noEmit` clean.
  `docker compose up -d --build web` green; curl 200 for `/`, `/staff`, `/traces` on :3001; the
  served chunk contains `http://localhost:8080`, so the build arg is inlined correctly. Exercised
  M3's live endpoints through `web/lib/api.ts` itself (node type-stripping): health ok, form permit
  12 fields, chat trash question -> tier=escalate, tool `get_trash_schedule`, 2 citations; upload
  -> doc 1; create -> SR-2026-000400 (worker took it to in_review); advance approved -> issued ->
  certificate 2155 bytes application/pdf; invalid transition returned 409. Note: that verification
  left one real row (SR-2026-000400) and one document in the demo DB.
- 2026-09-03 05:50 M5 done (Opus). Written: README.md (150), docs/ARCHITECTURE.md (250),
  docs/EXPLAINER.md (194), docs/DEMO_SCRIPT.md (120), docs/BUILD_LOG.md (90),
  deploy/aws/up.sh (191), down.sh (48), deploy/aws/README.md (67), scripts/reset_demo.sh (74).
  Edited: sample_applications.json (statuses), .env.bedrock, deploy/aws/litellm.yaml,
  docker-compose.yml (`litellm` under compose profile `aws`).
  **LiteLLM exercised once against real Bedrock** (us-west-2, an IAM user,
  `docker compose --profile aws up -d litellm`, ~/.aws mounted read-only). All five aliases
  answered; verbatim results:
    - chat `small`: `{"model":"small","choices":[{"finish_reason":"stop","message":
      {"content":"ok","role":"assistant"}}],"usage":{"completion_tokens":4,
      "prompt_tokens":14,"total_tokens":18}}`
    - chat `smart`, `escalate`, `extract`: same shape, `content:"ok"`, 14/4 tokens each.
    - embeddings `embed`: 1024 dims, `usage {prompt_tokens: 4, total_tokens: 4}`.
    - No model was rejected. Container stopped and removed afterwards; `.env` still Ollama.
  Verification: `bash scripts/reset_demo.sh --build` -> health db/s3/llm/embed=ok kb_chunks=82,
  eight seeded applications stable in manual statuses across restarts;
  `uv run pytest -q` 100 passed; `bash scripts/smoke.sh` 11/11 PASS 0 failures;
  `cd web && npm run build` clean. Eval (30 items, qwen2.5:7b via Ollama, nothing tuned):
  dev n=20 intent 80.0% tool 80.0% citations 100.0% keywords 100.0% mean 6830ms;
  holdout n=10 intent 90.0% tool 90.0% citations 100.0% keywords 100.0% mean 6040ms; cost $0.
- 2026-09-03 05:15 M3 done (Opus): `docker compose up -d --build api` green; `/health` all ok,
  kb_chunks=82. `uv run pytest -q` 100 passed. `bash scripts/smoke.sh` 11/11 PASS, 0 failures
  (upload -> chat -> PRM-2026-000400 in_review -> approved -> issued -> certificate %PDF;
  incomplete PDF -> needs_info -> follow-up message -> in_review; business tax PDF -> fee $43.88).
  Eval re-run after the date fix (qwen2.5:7b, 30 items): dev n=20 intent 80.0% tool 80.0%
  citations 100.0% keywords 95.0% mean 6913ms; holdout n=10 intent 90.0% tool 90.0%
  citations 100.0% keywords 100.0% mean 6227ms; cost $0. Only the date line changed; nothing
  was tuned. `docker compose logs api` clean (0 tracebacks, 0 ERROR lines).
