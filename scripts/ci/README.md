# CI — what runs, when, and what it costs

Seven files: six workflows in `.github/workflows/` plus `.github/dependabot.yml`.
Four of them gate every pull request; two are opt-in because they spend real
money on Bedrock (and now fail loudly rather than skipping green while the
credential they need is missing); one is a config file GitHub reads directly.

Helpers live here, not inline in the YAML, so they can be run by hand:

| File | What it is |
|---|---|
| `stub_openai.py` | A stdlib-only fake OpenAI server: `/v1/models`, `/v1/chat/completions` (buffered and SSE), `/v1/embeddings` (deterministic vectors, `--embed-dim`, default 768). Lets `compose-smoke` boot the API with no model and no spend. |
| `concurrency_probe.py` | Opens N chat streams at once and asserts every one ends in a `done` event, with no 5xx and none of them slower than `--max-seconds`. Needs `httpx`. |
| `health_ok.py` | Reads a `/health` body on stdin; exit 0 when `db` and `s3` are ok. |
| `eval_summary.py` | Newest `api/evals/results/*.json` → a markdown table for the run summary. |
| `../../.env.ci` | The CI env profile. Committed on purpose: every value is a throwaway that only exists inside a runner. |

---

## On every pull request (and every push to `main`)

### `api` — `.github/workflows/api.yml`

Paths `api/**`. `astral-sh/setup-uv` (cached on `api/uv.lock`) → `uv sync
--frozen` → `uv run ruff check .` → `uv run ruff format --check .` → `uv run
pytest -q`, with `LIVE_DATA_ENABLED=false`.

No service containers. `api/tests/conftest.py` forces live data off before
`app.config` is imported and the suite mocks httpx and the LLM client, so the
302 tests need no Postgres, no S3 and no model. ~2–3 min.

Ruff's rules and line length live in `api/pyproject.toml`. Two deliberate
suppressions are recorded there and at the one site: `B008` is disabled for
FastAPI's `Depends()`/`File()` markers (rewriting them would break routing), and
`UP042` is suppressed on `Tier` in `app/llm/client.py` (`enum.StrEnum` changes
what `str(Tier.SMALL)` returns).

### `web` — `.github/workflows/web.yml`

Paths `web/**`. `npm ci` → `npm run typecheck` → `npm run lint` → `npm run
build` with `NEXT_PUBLIC_API_URL=http://localhost:8080`. ~3–4 min.

`typecheck` is `next typegen && tsc --noEmit`, not bare `tsc --noEmit`: Next 16
generates `LayoutProps` and the route types into `.next/types/`, so on a clean
checkout `tsc` alone fails on `app/layout.tsx` before anything real is checked.

### `compose-smoke` — `.github/workflows/compose-smoke.yml`

No path filter — it is the check that catches a Dockerfile or compose change.
**Two matrix legs, `EMBED_DIM` 768 and 1024**, because that number is baked into
the vector column by migration 002 and prod (Titan v2) runs 1024 while the local
Ollama profile runs 768. Before M26b only 768 was ever exercised.

1. buildx builds the api and web images with `type=gha` cache (a scope per leg,
   because the two legs run at the same time and two concurrent `mode=max`
   exports into one scope race), tagged `civic-api` / `civic-web` with
   `COMPOSE_PROJECT_NAME=civic`, so the `up` below reuses them.
2. `sed .env.ci > .env` with the leg's `EMBED_DIM` — `docker-compose.yml`
   declares `env_file: .env` for the api service, so the CI profile has to land
   at that path as well as being passed to `--env-file`.
3. Starts `stub_openai.py --embed-dim <leg>` on the runner host, curls all three
   endpoints, and fails the step if the vector it gets back is the wrong length.
4. `docker compose --env-file .env up -d db seaweedfs api web` — the **whole
   default profile**, web included. `COMPOSE_PROFILES` is unset, so LiteLLM
   (profile `aws`) stays out.
5. Polls `/health` for up to 3 minutes, requiring `db=ok` and `s3=ok`. `llm` and
   `embed` are printed but not required — `/health` makes no model call.
6. Waits for the `web` container to report `healthy`. Compose gates `web` on
   `api: service_healthy`, so this also proves the API healthcheck passes from
   inside the network, not only from the host.
7. `SMOKE_MODEL=stub bash scripts/smoke.sh` — see below.
8. `concurrency_probe.py -n 20`, currently `continue-on-error`.
9. On failure, api and web logs plus the stub's log; always `down -v`.

This is the only check that proves migrations run, the seed loader fills
Postgres, the S3 bucket is reachable, the web image serves and an application
can be filed and issued. `INGEST_KB_ON_STARTUP=false` skips 120 embedding calls
whose vectors would be stub noise. ~10–14 min per leg.

**Why the stub answers JSON.** `app/llm/router.classify` asks for a
`Classification` through a `json_schema` response format. The stub used to reply
with the same prose it gives everything, so the classifier raised, every turn
took the error path, and the only thing CI could assert was the fallback
apology — which is also why the 2026-09-15 load test could not exercise tools or
retrieval. It now fills any schema it is handed (`json_schema`, a `json_object`
fallback with the schema pasted into the prompt, or a forced `tool_choice`),
preferring `smalltalk` and `low`, so a turn takes the cheapest real path
instead. A request that merely *offers* tools still gets prose: that is the
agent's answer turn, and JSON there would break the reply.

**What `SMOKE_MODEL=stub` runs.** `scripts/smoke.sh` defaults to `real` and is
unchanged for a human running it against the Bedrock stack. `stub` drops the
four checks that assert what a model said — the fee quoted in a chat reply, and
the needs_info extraction loop — and files the permit through the inline-form
endpoint instead of through chat. What is left still covers the whole workflow
spine: `/health`, `GET /api/forms/permit`, a PDF upload, `POST
/api/applications`, the worker routing it to `in_review`, staff sign-in, two
advances, and a certificate that really is a PDF. Both modes print the list of
checks they performed at the end, so the log says what the run proved rather
than only how many lines it printed.

**The concurrency probe is expected to fail today.** 20 is exactly
`pool_size + max_overflow`, and the SSE route holds a pool connection in a
`yield` dependency for the life of the stream and then asks for a second one, so
at 20 every stream waits out the 30 s pool timeout and ends in the fallback
apology (hostile review 2026-09-15, finding 1; measured again on this branch at
60.2 s wall, 20/20 streams over the ceiling, versus 0.3 s at concurrency 10).
Note that those streams *do* end in a `done` event — the timeout is caught and
templated — which is why the probe also enforces `--max-seconds`. The step is
`continue-on-error: true` with a comment naming **M26a**, which drops the
dependency; when M26a merges, delete that line and the probe gates again.

### `security` — `.github/workflows/security.yml`

Also on a weekly cron (Mondays 06:17 UTC), so a CVE published after a merge is
still reported. Four independent jobs:

- **pip-audit**: `uv export --frozen --no-dev --no-hashes | uvx pip-audit
  --no-deps --disable-pip -r /dev/stdin`. `--no-deps --disable-pip` means "audit
  exactly these versions" — uv already resolved the whole transitive set, and
  without them pip-audit builds a throwaway venv and re-resolves from PyPI.
- **npm audit**: `npm audit --audit-level=high` in `web/`, **reported, not
  fatal**. It was clean when this landed (0 advisories of any severity), so the
  `|| true` exists only so a fresh advisory against next/react cannot block an
  unrelated PR overnight. Findings land in the job summary and as a `::warning`.
  Drop the `|| true` once someone owns triage.
- **trivy**: builds `civic-api` and `civic-web` (a matrix, its own buildx cache
  scopes) and scans each **image** at `HIGH,CRITICAL` with `exit-code: 1` and
  `ignore-unfixed: true`. pip-audit and npm audit read dependency *manifests*;
  this is the only job that can see a CVE in the `python:3.12.14-slim` or
  `node:22.23.2-alpine` base layer underneath them, which is exactly what used
  to ship unnoticed. `ignore-unfixed` because a CVE with no patched version in
  the distro cannot be cleared by a rebuild, and a red check nobody can turn
  green gets ignored; run `trivy image --ignore-unfixed=false civic-api:scan`
  locally to see the full list before bumping a pinned base tag. Unlike npm
  audit this is a hard gate — the fix is a one-line Dockerfile change.
- **gitleaks**: `gitleaks/gitleaks-action@v3` over the full history
  (`fetch-depth: 0`), which runs `gitleaks detect --redact` — a finding names
  the file and rule without printing the secret into the log. No licence key is
  needed for a repo owned by a personal account. This is the free path: GitHub's
  own secret scanning and push protection are free only on public repos, and a
  private repo would need GHAS.

~2–3 min.

---

## Opt-in, and **not yet runnable**

Both need an `AWS_ROLE_ARN` repository secret: the ARN of an IAM role whose
trust policy accepts GitHub's OIDC provider for this repo, allowed to call
Bedrock. **That role does not exist yet.** Until it does, each workflow's
`guard` job **fails** with

```
::error::AWS_ROLE_ARN secret not configured; see scripts/ci/README.md
```

It used to skip green instead, which is indistinguishable from a passing run:
`eval-nightly` had been "running" every night for a week without once executing,
and nobody noticed (hostile review finding 14). A workflow that cannot do its
job should look broken. Neither is on the required-checks list, so neither
blocks a merge, and `e2e` only starts on a dispatch or an `e2e` label — a red X
is what the person who asked for it should see. Creating the secret is the only
change needed; neither file has a placeholder to edit.

Inside `eval-nightly`, `continue-on-error` is now on the **scoring step only**.
PLAN.md §14 says report the number and never tune the prompts to it, so a bad
score must not fail the run — but a stack that would not start, a `/health` that
never went green, or a missing results file are infrastructure failures and are
reported as such.

(Why a `guard` job at all: the `secrets` context cannot be read from a job-level
`if:`, so the check has to be a job that publishes a boolean output.)

### `e2e` — `.github/workflows/e2e.yml`

`workflow_dispatch`, or put the **`e2e`** label on a pull request. Assumes the
role via OIDC (`permissions: id-token: write`), brings the Bedrock profile up
with `docker compose up -d --build`, waits for `/health`, installs Chromium and
runs `npm run test:e2e`, then uploads the Playwright HTML report. Gated because
`web/playwright.config.ts` drives the **real** model: ~12–18 min, ~$0.50.

### `eval-nightly` — `.github/workflows/eval-nightly.yml`

Cron 09:00 UTC plus dispatch. Runs `python -m evals.run` against a live stack,
writes the scores into the run summary and uploads `api/evals/results/*.json`.
Every step is `continue-on-error: true` and this is **never** a required check —
PLAN.md §14 says report the number and never tune the prompts to it. ~15–20 min,
~$0.50.

---

## `.github/dependabot.yml`

Weekly (Mondays 06:00 UTC): `pip` on `/api`, `npm` on `/web`, `github-actions`
on `/`, `docker` on `/api` and `/web`. Minor and patch updates are grouped into
one PR per ecosystem.

Two things to know. Dependabot's `pip` ecosystem reads `api/pyproject.toml` but
does **not** refresh `api/uv.lock`, so a Python bump needs `cd api && uv lock`
pushed onto the branch before `api.yml`'s `uv sync --frozen` will pass. And the
`docker` ecosystem reads Dockerfiles, not `docker-compose.yml`, so the pinned
compose images (pgvector, seaweedfs, litellm) are still a manual bump.

Action pins are major tags (`actions/checkout@v7`, `docker/build-push-action@v7`
and so on) except `astral-sh/setup-uv@v10.1.0`: upstream stopped publishing
floating major tags after `v7`, so `@v10` does not resolve. Dependabot bumps it.

---

## Branch protection — the author has to click this

Nothing in the repo can set this; it is Settings → Branches → Add rule.

- **Branch name pattern:** `main`
- **Require a pull request before merging** — 1 approval (or 0 for a solo repo,
  but keep the PR so the checks run).
- **Require status checks to pass before merging**, and **Require branches to be
  up to date before merging**. Required checks — search for these four by name
  after they have run once:
  - `api / ruff + pytest`
  - `web / typecheck + lint + build`
  - `compose-smoke / build + up + smoke (embed 768)` and
    `compose-smoke / build + up + smoke (embed 1024)` — one per matrix leg
  - `security / python dependencies`, `security / node dependencies`,
    `security / image scan (civic-api)`, `security / image scan (civic-web)`,
    `security / secret scan`
- **Do not** add `e2e` or `eval-nightly` — they cost money and skip without the
  secret, which would block every merge.
- Optional: **Require conversation resolution**, and **Do not allow bypassing
  the above settings** (turn that one off while iterating solo, since it applies
  to admins too).

One caveat worth knowing before you tick the boxes: `api` and `web` have `paths`
filters, so a PR touching only `docs/` never starts them, and a required check
that never starts leaves the PR "Expected — waiting for status". Either keep
those two off the required list and rely on `compose-smoke` plus `security`
(which have no path filter), or replace the filters with a
[skip-job pattern](https://docs.github.com/actions/using-workflows/workflow-syntax-for-github-actions#jobsjob_idif)
that always reports a green check. The four-check list above assumes the author
mostly opens PRs that touch `api/` or `web/`.

## Running a job by hand

```bash
cd api && uv sync --frozen && uv run ruff check . && uv run ruff format --check . && uv run pytest -q
cd web && npm ci && npm run typecheck && npm run lint && npm run build
cd api && uv export --frozen --no-dev --no-hashes | uvx pip-audit --no-deps --disable-pip -r /dev/stdin
cd web && npm audit --audit-level=high

# The stub, on its own (--embed-dim must match EMBED_DIM):
python3 scripts/ci/stub_openai.py --port 4010 --embed-dim 1024
curl -s localhost:4010/v1/models
curl -s localhost:4010/v1/chat/completions -H 'content-type: application/json' \
  -d '{"model":"stub-small","messages":[{"role":"user","content":"ping"}]}'

# The stub-mode smoke and the concurrency probe against a running stack:
SMOKE_MODEL=stub bash scripts/smoke.sh http://localhost:8080
cd api && uv run --with httpx python ../scripts/ci/concurrency_probe.py -n 20
```

The whole compose-smoke job without Actions, against a local uvicorn (PLAN §12.1
recipe) rather than containers:

```bash
python3 scripts/ci/stub_openai.py --port 4011 --embed-dim 1024 &
cd api && SEED_ON_STARTUP=false INGEST_KB_ON_STARTUP=false WORKER_ENABLED=false \
  EMBED_DIM=1024 LLM_PRICES_JSON='{}' \
  DATABASE_URL=postgresql+asyncpg://civic:civic@localhost:5433/civic \
  S3_ENDPOINT=http://localhost:8333 \
  LLM_BASE_URL=http://127.0.0.1:4011/v1 EMBED_BASE_URL=http://127.0.0.1:4011/v1 \
  LLM_MODEL_SMALL=stub-small LLM_MODEL_SMART=stub-smart EMBED_MODEL=stub-embed \
  uv run uvicorn app.main:app --port 8088
```

(`WORKER_ENABLED=false` because the container on :8080 already runs the workflow
worker against the same database; leave it on if you are not sharing one.)
