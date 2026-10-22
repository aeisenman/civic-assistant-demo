# Production plan: from demo fixture to City systems of record

What changes when this assistant runs against a real municipality's data, and what does not.
Written 2026-09-14 for the demo. Companion to `ARCHITECTURE.md` (what is built) and `DESIGN.md` (why).

## 1. What is real today and what is a fixture

| Layer | Today | Status |
|---|---|---|
| Council districts, street sweeping, zoning, permits on file | City ArcGIS layers, live, any real address | Real |
| Address resolution | City geocoder, with seed match first and bare ZIP last | Real, with fallback |
| Policy and FAQ text | 9 markdown files, about 900 lines, embedded at startup | Curated from City pages |
| Trash zones, addresses, events, fees, referrals | Seed JSON, 40 addresses, 12 zones, 25 events | Fixture |
| Applications and tracking numbers | Created by the workflow engine, stored in Postgres | Fixture (no public write API exists) |
| Routing, tools, retrieval, workflow engine, traces, evals, auth, provider swap | Code | Real |

The rule that makes the fixture safe: nothing the model says comes from the fixture directly. Every fact
arrives through a typed tool result or a cited chunk, and every tool result carries `source` (`live` or
`seed`) and `match` (`seed`, `geocoded`, `zip`). The trace shows both.

## 2. The seam: tools are the semantic layer

`app/tools/registry.py` maps a name to a pydantic input model and an async function. Each tool is one
business concept with a typed contract, a plain-language `summary`, and provenance tags. That is a
semantic layer in miniature. Production keeps the contract and replaces the implementation:

```
today:       get_permit_status(tracking) -> SELECT from applications (seed)
production:  get_permit_status(tracking) -> Accela adapter -> same result shape, source="accela", as_of=...
```

Prompts, router, profiles, UI and evals do not change. The live City layers already prove this: the same
`get_council_district` tool answered from a seed row in phase 1 and from ArcGIS in phase 2.

Three fields are added to every production tool result:
- `owner`: the system of record that answered.
- `as_of`: when that system last updated the record.
- `scope`: who may see it (public, resident-own, staff).

The model never writes SQL. Aggregate questions ("how many potholes closed in District 3 last month")
are exposed as one more tool each, backed by a metrics layer (dbt semantic layer, Cube, or a set of
governed views) over the warehouse.

## 3. Systems of record for the City of San Diego

| Concept | System | Access | Tool(s) that would use it |
|---|---|---|---|
| Building permits, plan check | Accela Civic Platform | Accela REST API | `get_permit_status`, `estimate_permit_fee`, `start_application` |
| Get It Done cases (311) | Salesforce | Salesforce REST, plus open dataset on data.sandiego.gov | `create_service_request`, `get_application_status` |
| Business tax certificates | Office of the City Treasurer | Internal API or nightly export | `estimate_business_tax`, `get_application_status` |
| Collection routes and holidays | Environmental Services, ArcGIS | ArcGIS REST (CollectionMapLookup layer) | `get_trash_schedule`, `get_next_pickup`, `get_holiday_schedule` |
| Council agendas, meetings | Legistar / Granicus | Legistar API, RSS (RSS is already wired) | `search_events` |
| Districts, sweeping, zoning | ArcGIS (webmaps.sandiego.gov) | ArcGIS REST | Already live |
| Policy text, fee schedules | sandiego.gov pages, Municipal Code | Crawl into the KB with `source_url` and `last_crawled` | Retrieval |

Each row is one adapter module under `app/live/` following the pattern of `arcgis.py`: one HTTP client
with a timeout, a cache, and a `None` return on failure so the tool degrades to a clean error, never a 500.

## 4. When the data is not clean

| Problem | Where it is handled | What the resident sees |
|---|---|---|
| Address does not match | Resolver: seed, then City geocoder with score >= 80, then ZIP. Production adds a confirm step below the threshold. | "Is this the address you mean?" or a ZIP-level answer labelled as such |
| Inconsistent codes, duplicates | Adapter canonicalizes; keeps raw and normalized values | The summary states which value was used |
| Stale or conflicting records | `as_of` on every result; a precedence rule per concept in the adapter | The answer states the source and its date |
| Missing fields on an application | Validator and the `needs_info` state, already built | Asked for the missing fields in chat |
| Schema drift upstream | Pydantic contracts fail loudly; `dispatch()` turns the failure into an error the model reads; golden set catches the regression | A clean "could not retrieve" with a phone number, not a wrong answer |
| Scanned documents | pypdf today; add OCR (Textract) with a confidence score; low confidence routes to `in_review` | A human checks it |
| PII | Status tools already strip applicant details; production scopes rows by the signed-in user | Only their own records |
| A City service is down | 4 s timeout, 10 min cache, seed fallback | An answer labelled "based on demo data" or a referral |

The model is told, in every profile, to say whether a fact came from live or seed data and never to
state a number a tool did not return. That rule does more for dirty data than any cleaning job: a wrong
record is shown with its source and date, and a resident or staff member can see why.

## 5. Unstructured content at scale

The KB pipeline (`rag/ingest.py`) becomes a crawler:
- Source list per department, with `source_url`, `last_crawled`, and a content hash.
- Re-ingest on change only; chunk ids stay stable so traces keep pointing at the right text.
- Chunks keep the title and heading prefix, so a retrieved paragraph carries its context.
- Hybrid retrieval and RRF do not change. The topic filter maps to departments instead of nine files.

Web search (`search_city_website`, built, off by default) stays the last resort for pages not yet
crawled, restricted to `*.sandiego.gov`, with the fetched page returned as a citable source.

## 6. Phased roadmap

| Phase | Scope | Effort |
|---|---|---|
| 0 | Turn on web search (Brave key), so uncrawled City pages are reachable | 5 minutes |
| 1 | Get It Done open dataset adapter: real service request lookups, read-only | Half a day |
| 2 | Crawl 20 to 30 department pages into the KB with provenance and re-ingest on change | 1 day |
| 3 | ESD collection layer adapter: real collection days per address, retire the ZIP fallback | 1 day, needs the layer id |
| 4 | Accela read adapter: real permit status by tracking number; write path stays in the workflow engine until a City API allows it | 2 to 3 days with credentials |
| 5 | Metrics tools over a warehouse for aggregate questions; row-level scope by user | 1 week |
| 6 | OCR, extraction confidence, and human review queue for scanned uploads | 2 to 3 days |

Nothing in phases 1 through 6 touches the router, the profiles, the UI, or the evals. Each phase adds an
adapter and a golden-set category.

## 7. What to say if asked

"The seed data is a fixture. Nothing the model says comes from the fixture directly, it comes through a
tool with a typed contract and a source label. Replacing the fixture with Accela or Salesforce is an
adapter, and the live City map layers are the proof that the seam works."

## 8. Two production shapes (added 2026-09-15)

The API never names a host, a bucket or a model. Both shapes below change only environment values
and where the containers run. Prices are approximate us-west-2 list prices at pilot scale
(about 1,000 turns a day) in September 2026, before Bedrock usage, which is about $0.03 a turn on
the current tiers.

### Option A. One VM, compose, TLS, backups

For a pilot with one department, a small IT team, and a budget line rather than a platform team.

| Piece | What it does for this app | Monthly |
|---|---|---|
| EC2 m6i.large (2 vCPU, 8 GB), 100 GB gp3 | Runs the five compose services as today. Memory limits already set per service. | ~$80 |
| Caddy (sixth container) | Terminates TLS with a Let's Encrypt certificate, proxies `/` to web and `/api` to api, sets the idle timeout above the 45 s model timeout, adds HSTS. Makes `COOKIE_SECURE=true` and `WEB_ORIGIN=https://...` true. | $0 |
| Route 53 | One hostname. | ~$1 |
| S3 bucket, versioned, lifecycle 90 days | Nightly `scripts/backup.sh` output copied off the host by a cron line. `scripts/restore.sh` is the monthly drill. | ~$2 |
| Instance role scoped to Bedrock invoke and that bucket | No access keys on disk. LiteLLM reads the role through the SDK. | $0 |
| SSM Parameter Store, SecureString | Holds `STAFF_PASSWORD`, `SESSION_SECRET`, `LITELLM_MASTER_KEY`, `S3_SECRET_KEY`; `up.sh` renders `.env` from it at boot instead of writing secrets into user-data. | $0 |
| CloudWatch agent | Ships the json-file container logs and host metrics; two alarms: `/health` non-200 for 2 minutes, disk over 80%. | ~$5 |
| Security group | 443 to the world, 22 to one IP. 3001 and 8080 are not published; Caddy reaches them on the compose network. | $0 |

About $90 a month plus model usage. Failure modes it removes: plaintext staff cookie, secrets in
user-data, backups on the same disk, a full disk from unrotated logs, an unnoticed outage. What it
keeps: one host, so a host failure is downtime until the AMI is relaunched (about 10 minutes with the
script), and the API is one process, so the concurrency ceiling is the process, not the fleet.

### Option B. Managed containers, RDS, S3

For a citywide launch, or any team that already runs ECS.

| Piece | What it does for this app | Monthly |
|---|---|---|
| ECS Fargate, `api` service, 2 tasks of 1 vCPU / 2 GB | The FastAPI container, unchanged image. Two tasks behind the load balancer; `WORKER_ENABLED=false`. | ~$60 |
| ECS Fargate, `worker` service, 1 task of 0.25 vCPU | The same image with `WORKER_ENABLED=true` and no public port. One replica by design, so the 3 s poll has one owner; `FOR UPDATE SKIP LOCKED` makes a second one safe if autoscaling ever adds it. | ~$8 |
| ECS Fargate, `web` service, 2 tasks of 0.5 vCPU | The Next.js container. | ~$30 |
| ECS Fargate, `litellm` service, 1 task | The gateway, task role scoped to Bedrock invoke, `fallbacks` in its config. | ~$15 |
| Application Load Balancer, ACM certificate | TLS, path routing (`/api` to api, everything else to web), idle timeout 120 s so a slow tool round does not drop the stream, health check on `/health` so a degraded task leaves rotation. AWS WAF attached with the managed common rule set and a rate rule. | ~$25 + WAF ~$10 |
| RDS PostgreSQL 16, db.t4g.medium, Multi-AZ, pgvector extension | Replaces the Postgres container. `DATABASE_URL` changes, nothing else; migrations run the same. Automated backups, point-in-time restore, encrypted at rest. | ~$110 |
| S3 bucket | Replaces SeaweedFS. `S3_ENDPOINT` and the keys change, the boto3 code does not. Real signatures, bucket policy, versioning, lifecycle. | ~$2 |
| Secrets Manager | The four secrets injected as task environment; rotation on a schedule for the staff password. | ~$2 |
| CloudWatch Logs and Container Insights | Every task's stdout with request ids; alarms on 5xx rate, p95 latency, task restarts, daily cost from the traces aggregate pushed as a custom metric. | ~$15 |
| NAT gateway | Outbound to Bedrock and sandiego.gov from private subnets. | ~$35 |
| CodePipeline or GitHub Actions with OIDC | The existing workflows build, scan and push the images; a deploy job updates the task definitions. | ~$0 |

About $310 a month plus model usage. Failure modes it removes on top of Option A: a single host, a
single API process, an unauthenticated object store, hand-run backups, in-process state (rate limits
and the worker are already Postgres-backed after M26a, so two API tasks are safe). What it adds: a
platform to operate, and a private-subnet network the team must own.

### What is the same in both

The image, the migrations, the tool contracts, the evals, the dashboard. `ENVIRONMENT=prod` refuses
placeholder secrets and a non-TLS origin in both. The provider swap stays an env file: Bedrock through
LiteLLM today, Azure OpenAI or a self-hosted model tomorrow.

### Recommendation

Start with Option A for the pilot. It is honest about scale, costs a third as much, and every piece
of it carries into Option B unchanged when volume or an IT standard calls for it.
