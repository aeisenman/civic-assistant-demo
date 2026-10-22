\
# Production readiness: checklist against real standards

Scored against this repo as of 2026-09-14 (commit `f371a3b`). Sources are the authoritative
document for each criterion, not a summary site, wherever one could be fetched. "System today"
cites the file or doc that is the evidence. Status: `met`, `partial`, `gap`.

## 1. Checklist

### Accuracy and grounding

| # | Criterion | Source | System today | Status | Smallest change |
|---|---|---|---|---|---|
| A1 | Every fact in a reply traces to a tool result or cited chunk, never model memory | [NIST AI 600-1, Confabulation](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf) | `<source>` fencing + preamble rule in `app/agents/profiles.py` `BASE_RULES`; ARCHITECTURE.md "Orchestrator turn sequence" step 7 | met | — |
| A2 | Model never does arithmetic on a tool's numbers to invent a new figure | [NIST AI 600-1, Confabulation](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf); [OWASP LLM09:2025 Misinformation](https://genai.owasp.org/llm-top-10/) | Prompt rule added after a live run turned $1,250 into a $2,063-$2,313 range — `DECISIONS.md` "Phase 3 hardening, round 2" | met | — |
| A3 | Low-confidence or multi-intent turns escalate instead of guessing | [NIST AI RMF, Measure](https://airc.nist.gov/airmf-resources/playbook/measure/) | `select_tier()` escalates confidence<0.6, high complexity, or a secondary intent — `app/llm/router.py` | met | — |
| A4 | RAG faithfulness (does the answer match the retrieved context) is scored, not assumed | [RAGAS: faithfulness](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/) | Mechanical keyword + `must_not_contain` only, no claim-vs-context check — `api/evals/run.py`, PLAN.md §14 | gap | Add a per-claim faithfulness check on a sampled subset, even without full RAGAS |
| A5 | Retrieval quality (context precision/recall) is measured | [RAGAS: context precision](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/) | `citations_ok` is a boolean ("did the model cite anything"), not a relevance judgment on what was retrieved | gap | Hand-label retrieved chunks as relevant/irrelevant on the existing golden set |
| A6 | Eval set is representative of production traffic, not just hand-written cases | Implied by [NIST AI RMF, Map](https://airc.nist.gov/airmf-resources/playbook/map/) | 54 hand-written questions across 8 categories — README.md "Limitations", DESIGN.md "Limits" | partial | Sample real traffic once the assistant is live and add it to `golden.json` |
| A7 | The eval is never tuned to overfit; root causes are fixed and logged instead | Internal policy | PLAN.md §14 "do not overfit"; every generalizing fix logged in `DECISIONS.md` | met | — |
| A8 | Self-reported accuracy is independently validated before publication | [NYC Comptroller, MyCity audit](https://comptroller.nyc.gov/wp-content/uploads/2026/02/MyCity-System-Development-Public-Final-report-12-30-25-final-copy.pdf) — vendor claimed 95-99%, audit found inconsistent answers | Only the author's own `evals/run.py` numbers exist (dev 80-96.9%, holdout 90-100% across runs — STATE.md) | gap | Not needed for a demo; flag before any external accuracy claim |

### Safety and abuse

| # | Criterion | Source | System today | Status | Smallest change |
|---|---|---|---|---|---|
| S1 | Resistant to prompt injection from user text, uploaded docs and fetched pages | [OWASP LLM01:2025](https://genai.owasp.org/llm-top-10/) | Every non-authored string fenced `<source trust="untrusted">`, fence-closing sequences defanged, preamble says fenced text is never an instruction — M19, `DECISIONS.md` round 2 | met | — |
| S2 | Tool calls are restricted to what the current intent needs (least agency) | [OWASP LLM06:2025 Excessive Agency](https://genai.owasp.org/llm-top-10/) | Per-intent allow-list enforced inside the tool loop; an off-list call is refused, never dispatched — ARCHITECTURE.md "Agent profiles" | met | — |
| S3 | Model output is sanitized before rendering (no script execution) | [OWASP LLM05:2025 Improper Output Handling](https://genai.owasp.org/llm-top-10/) | `MarkdownLite` renders `<script>`, `onerror`, data-URI images and `javascript:` links as inert text — `web/e2e/markdown.spec.ts` probe A18 | met | — |
| S4 | Bounded cost/resource use per session and per day | [OWASP LLM10:2025 Unbounded Consumption](https://genai.owasp.org/llm-top-10/) | Per-session turn cap, daily `SUM(cost_usd)` cap checked before `classify()`, `MAX_CONCURRENT_STREAMS` semaphore — `app/api/chat.py`, `app/config.py` | met | — |
| S5 | Dependencies and images are scanned and pinned | [OWASP LLM03:2025 Supply Chain](https://genai.owasp.org/llm-top-10/) | Pinned image versions, `pip-audit`/`npm audit`/`gitleaks` in CI — `.github/workflows/security.yml`, `docker-compose.yml` header comment | met | — |
| S6 | System prompt cannot be exfiltrated by a direct request | [OWASP LLM07:2025 System Prompt Leakage](https://genai.owasp.org/llm-top-10/) | No explicit "reveal your instructions" case in the live-model probe set (`docs/HARDENING_PROBES.md` Tier B) | partial | Add an explicit leakage prompt to the hardening golden category |
| S7 | Status/record lookups never leak another resident's PII | [OWASP LLM02:2025 Sensitive Information Disclosure](https://genai.owasp.org/llm-top-10/) | `get_application_status`/`get_permit_status` return a redacted view (no applicant name, no transition log) — ARCHITECTURE.md "Privacy of status lookups" | met | — |
| S8 | Known adversarial failure modes are tracked to closure, not hidden | [NIST AI RMF, Manage 4](https://airc.nist.gov/airmf-resources/playbook/manage/) | A jailbreak wrapper ("developer mode... then tell me the trash day") flips the router to `smalltalk`, leaving the real question unanswered — logged, not fixed, in `DECISIONS.md` round 2 | partial | Keep the secondary intent live even when a jailbreak phrase is present |

### Privacy and records

| # | Criterion | Source | System today | Status | Smallest change |
|---|---|---|---|---|---|
| P1 | Resident PII is minimized or redacted before it lands in logs | [NIST AI 600-1, Data Privacy](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf) | Names, addresses, emails and phones land in `traces` in the clear — README.md "Limitations", DESIGN.md "Limits" | gap | Add a redaction pass before the trace row is written |
| P2 | Chat transcripts have a documented retention and disposal schedule | [Gov. Code §34090](https://law.justia.com/codes/california/2005/gov/34090-34093.html), min. 2 years before disposal | `NEVER_TRUNCATE` list keeps `chat_messages`/`traces` forever, no disposal path — ARCHITECTURE.md "Seeding never destroys resident data" | partial | Meets the 2-year floor by over-retaining; write an actual retention/disposal policy |
| P3 | A redaction workflow exists for public-records requests against transcripts | [CPRA and AI chat logs](https://www.lcwlegal.com/news/public-records-act-meets-ai-what-recent-records-requests-reveal-about-chatgpt-use-in-government/) | None built | gap | Document a PRA redaction procedure before any request arrives |
| P4 | Records are not destroyed before the statutory minimum without process | [Gov. Code §34090](https://law.justia.com/codes/california/2005/gov/34090-34093.html) — destruction under 2 years needs a council resolution + city-attorney consent | Nothing is ever destroyed today — compliant by inaction | met | Formalize a deletion process before enabling any purge |
| P5 | Vendor (model/hosting) data-use obligations are documented, since CCPA/CPRA exempt the city but not its contractors | [CCPA/CPRA business-exemption nuance](https://www.termsfeed.com/blog/ccpa-cpra-business-definition-guide/) | No DPA/BAA discussion for AWS Bedrock or LiteLLM in any doc | gap | Add a one-paragraph vendor data-use note to PRODUCTION_PLAN.md |
| P6 | Records are scoped to the authenticated resident who owns them | Internal, matches [NIST AI 600-1 Data Privacy](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf) | No resident auth exists; a session id is a browser UUID — `ASSUMPTIONS.md` #5; redaction substitutes for scoping today | gap | `PRODUCTION_PLAN.md` §6 phase 5 already names this as the fix |
| P7 | Staff access to PII is authenticated and attributable to a person | Internal | scrypt password auth, 12-hour session, every transition's actor recorded — ARCHITECTURE.md "Staff authentication" | met | — |

### Accessibility and language

| # | Criterion | Source | System today | Status | Smallest change |
|---|---|---|---|---|---|
| X1 | Text contrast meets WCAG 2.1 AA (SC 1.4.3, 4.5:1) | [W3C SC 1.4.3](https://www.w3.org/WAI/WCAG21/Understanding/contrast-minimum.html) | `muted` token at 4.76:1 replaced `slate-400` at 2.6:1 for timestamps/placeholders — ARCHITECTURE.md "Accessibility", `docs/HARDENING_AUDIT.md` S4 | met | — |
| X2 | Every control is keyboard-operable (SC 2.1.1) | [W3C SC 2.1.1](https://www.w3.org/WAI/WCAG21/Understanding/keyboard.html) | Staff drawer's modal focus trap is built; composer, quick-action chips and citation chips have not had a dedicated keyboard audit | partial | Run a keyboard-only pass across all four pages |
| X3 | A visible focus indicator exists everywhere, including inside a modal (SC 2.4.7) | [W3C SC 2.4.7](https://www.w3.org/WAI/WCAG21/Understanding/focus-visible.html) | One accent focus ring applied globally — `web/app/globals.css` | met | — |
| X4 | Streamed/async content is announced to assistive tech without a focus change (SC 4.1.3) | [W3C SC 4.1.3](https://www.w3.org/WAI/WCAG21/Understanding/status-messages.html) | Message list is `role="log" aria-live="polite"` — `web/app/page.tsx:278-279` | met | — |
| X5 | Custom widgets expose correct name/role/value (SC 4.1.2) | [W3C SC 4.1.2](https://www.w3.org/WAI/WCAG21/Understanding/name-role-value.html) | Staff drawer is `role="dialog" aria-modal="true"`, labelled by the tracking number — ARCHITECTURE.md "Accessibility" | met | — |
| X6 | Independent Section 508 / WCAG 2.1 AA conformance testing (VPAT) | [ADA Title II applicability, deadline 2026-04-24 for state/local gov](https://www.section508.gov/develop/applicability-conformance/) | No formal audit or VPAT exists | gap | Commission a 508 audit before any real resident-facing launch |
| X7 | Official ".gov" identity banner and identifier component | [USWDS Banner](https://designsystem.digital.gov/components/banner/), [USWDS Identifier](https://designsystem.digital.gov/components/identifier/) | "No UI kit" by design — ARCHITECTURE.md "Web" | gap | Add the USWDS banner + identifier components |
| X8 | Meaningful access is provided in the City's threshold languages | [EO 13166 four-factor test](https://www.faa.gov/sites/faa.gov/files/2022-07/Day%201%20session%203%202022%20FAA%20Title%20VI%20IND_508.pdf); [San Diego Title VI Implementation Plan](https://www.sandiego.gov/sites/default/files/2023-12/title-vi-implementation-plan.pdf) | `<html lang="en">` is hardcoded, no UI locale switch; the model can answer in Spanish if asked, with an untranslated fragment observed ("basado en demo data" — `docs/verification/2026-09-07-e2e.md`) | gap | Add a UI language switch and review the model's fixed English fragments |

### Reliability and operations

| # | Criterion | Source | System today | Status | Smallest change |
|---|---|---|---|---|---|
| R1 | Users are told upfront they are talking to a bot, not a person | [digital.gov chatbot guidance](https://digital.gov/2021/04/07/using-chatbots-to-improve-customer-experience) | System prompt says "the City of San Diego's virtual assistant"; empty-state copy says "the assistant will file it" — no explicit "you are talking to a bot" line | partial | Add one explicit disclosure sentence to the empty state |
| R2 | A path to a human exists when the bot cannot help | [digital.gov chatbot guidance](https://digital.gov/2021/04/07/using-chatbots-to-improve-customer-experience) | `get_referral` tool names an outside agency; no live handoff to a City human agent in the UI | partial | Publish a phone/email fallback in the UI itself, not only through the model |
| R3 | Health checks distinguish "process up" from "dependency down" | Internal, matches [NIST AI RMF, Manage 4](https://airc.nist.gov/airmf-resources/playbook/manage/) | `/health` (db, s3, kb count) vs. staff-only `/health/deep` (llm); `web` waits on `api` healthy — ARCHITECTURE.md "What compose guarantees" | met | — |
| R4 | The system is safe to run as more than one replica | Internal | In-process worker, in-process login-lockout counter, per-process `MAX_CONCURRENT_STREAMS` — `api/app/auth.py:47`, README.md "Auth" | gap | Move the lockout counter and worker leadership into Postgres, on the pattern `advance()` already uses |
| R5 | A published uptime SLA is met and measured | [AI Service Level Agreement](https://www.mavenagi.com/glossary/ai-service-level-agreement) — 99.9%+ typical target | Single API container, `restart: unless-stopped`, no redundancy, uptime not measured | gap | Out of scope for a demo; flag as a pre-production blocker |
| R6 | Backups are scheduled, offsite and tested | Internal, matches [NIST AI RMF, Manage](https://airc.nist.gov/airmf-resources/playbook/manage/) | `scripts/backup.sh` (pg_dump -Fc + seaweed tar) exists but runs manually, local disk only — ARCHITECTURE.md "Backups" | partial | Cron it and ship the archive off the host |
| R7 | Operational health (error rates, drift) is monitored beyond one table | Internal | "Traces are the only observability... nothing answers is the tool-error rate rising" — DESIGN.md "Limits", README.md "Monitoring" | gap | Export trace aggregates to a metrics backend with alerting |
| R8 | Model and downstream calls are bounded so one hang cannot cascade | Internal | 45s LLM timeout/1 retry, 4s live-data timeout, 15s `statement_timeout`, 90s stream ceiling — ARCHITECTURE.md, `app/config.py` | met | — |

### Security

| # | Criterion | Source | System today | Status | Smallest change |
|---|---|---|---|---|---|
| SEC1 | Traffic between resident, web and API is encrypted in transit | General best practice, implied by [Section 508 applicability](https://www.section508.gov/develop/applicability-conformance/) for public-facing gov services | "No TLS and no domain" — `deploy/aws/README.md:123`, plain HTTP on 3001/8080 | gap | Put a TLS-terminating proxy (Caddy/ALB) in front; `COOKIE_SECURE` already anticipates it |
| SEC2 | No default/placeholder secret can start a production instance | [OWASP LLM03:2025](https://genai.owasp.org/llm-top-10/); [NIST AI RMF, Govern 6.1](https://airc.nist.gov/airmf-resources/playbook/govern/) | `ENVIRONMENT=prod` model validator refuses `staff`/`civic`/`CHANGEME`/etc. and names every offender — `app/config.py`, `DECISIONS.md` round 2 | met | — |
| SEC3 | Cloud credentials follow least privilege | [NIST AI 600-1, Value Chain and Component Integration](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf) | LiteLLM mounts one scoped credentials file, not the whole `~/.aws` — `DECISIONS.md` round 2 | met | — |
| SEC4 | Network exposure is minimized to only what a browser needs | Internal | Only `api:8080` and `web:3001` on `0.0.0.0`; Postgres, SeaweedFS S3 and LiteLLM on `127.0.0.1`; SeaweedFS's two UIs unpublished — ARCHITECTURE.md "What compose guarantees" | met | — |
| SEC5 | Object storage enforces authentication | Internal, matches [OWASP LLM02:2025](https://genai.owasp.org/llm-top-10/) | "SeaweedFS enforces no S3 signature at all" because no identity config is loaded — ARCHITECTURE.md "Storage" | gap | Load a SeaweedFS identity config before pointing at anything but a demo bucket |
| SEC6 | Dependency vulnerabilities block the build, not just warn | [OWASP LLM03:2025](https://genai.owasp.org/llm-top-10/) | `pip-audit` gates CI; `npm audit --audit-level=high` is reported, not fatal — `.github/workflows/security.yml` | partial | Flip npm audit from warning to failing on high/critical |
| SEC7 | A WAF/DDoS layer sits in front of the public endpoints | Internal | None; no CDN or WAF | gap | Out of scope for a demo; add an ALB + AWS WAF at real deploy |
| SEC8 | Retrieval/embedding pipeline has no cross-tenant leakage path | [OWASP LLM08:2025 Vector and Embedding Weaknesses](https://genai.owasp.org/llm-top-10/) | Single-tenant demo database; no tenant boundary exists to violate | met | Revisit if this ever becomes multi-tenant |

### Governance and transparency

| # | Criterion | Source | System today | Status | Smallest change |
|---|---|---|---|---|---|
| G1 | The AI use case, scope and intended users are documented before deployment | [NIST AI RMF, Map](https://airc.nist.gov/airmf-resources/playbook/map/); [CA GenAI Guidelines](https://www.cdt.ca.gov/wp-content/uploads/2024/07/3a-GenAI-Guidelines.pdf) | `ARCHITECTURE.md`, `DESIGN.md`, `PRODUCTION_PLAN.md` all describe scope, fixtures vs. real data, and limits | met | — |
| G2 | An executive owner and governance intake process reviews the use case | [San Diego's real AI governance framework](https://cities-today.com/how-san-diego-built-a-foundation-for-ai-at-scale/), [intake/subcommittee process](https://hoodline.com/2026/04/san-diego-city-hall-quietly-puts-ai-sidekick-on-the-job/) | None — this is a portfolio demo, not a City-reviewed deployment | gap | Out of scope for a demo; required before any real City use |
| G3 | Compliance with the City's own AI board policy is verified | [San Diego Council Policy A-140](https://codelibrary.amlegal.com/codes/san_diego/latest/sandiego_board/a_140__artificial__intelligence__board__policy) (text unverified — fetch blocked) | Not checked; the policy's actual text could not be confirmed during this research | gap | Verify A-140's text directly before any real-deployment claim |
| G4 | Consequential decisions keep a human in the loop | [CA GenAI equity guidelines, human-in-the-loop](https://cities-today.com/how-san-diego-built-a-foundation-for-ai-at-scale/) | Approve/reject/issue require a staff button click; only field extraction is a model call — ARCHITECTURE.md "Intake" | met | — |
| G5 | Every answer discloses whether its data is live or a fixture, and as-of | `PRODUCTION_PLAN.md` §1/§4 (internal rule, generalized from [NIST AI 600-1, Information Integrity](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf)) | Every tool result carries `source`/`match`; the trace shows both — ARCHITECTURE.md "Traces" | met | — |
| G6 | Outputs are evaluated for disparate quality across languages/groups | [NIST AI 600-1, Harmful Bias and Homogenization](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf); [CA GenAI equity guidelines](https://www.genai.ca.gov/wp-content/uploads/sites/360/2024/12/GenAI-Equity-Guidelines-2024.12.19.pdf) | Not tested; no non-English items in `golden.json` | gap | Add Spanish-language and dialect variants to the golden set |
| G7 | Every model decision leaves an audit trail | [NIST AI RMF, Measure 3](https://airc.nist.gov/airmf-resources/playbook/measure/) | One `traces` row per turn: routing, tools, tokens, cost, error — ARCHITECTURE.md "Traces" | met | — |
| G8 | Changes to prompts/routing/KB are logged with their reasoning | Internal | Every generalizing fix requires a `DECISIONS.md` entry — PLAN.md §14 | met | — |

### Cost

| # | Criterion | Source | System today | Status | Smallest change |
|---|---|---|---|---|---|
| C1 | Cost is tracked per turn | Internal, matches [OWASP LLM10:2025](https://genai.owasp.org/llm-top-10/) | `traces.cost_usd` computed from `LLM_PRICES_JSON` | met | — |
| C2 | A circuit breaker caps runaway daily spend | [OWASP LLM10:2025 Unbounded Consumption](https://genai.owasp.org/llm-top-10/) | `DAILY_COST_CAP_USD` checked before `classify()` — `DECISIONS.md` round 1 | met | — |
| C3 | Cost per conversation is benchmarked against an external standard | No published municipal per-conversation cost standard found — [StealthAgents research hub](https://stealthagents.com/research/first-contact-resolution-statistics-2026) scope note | ~1.7 cents/turn observed on Bedrock — `ASSUMPTIONS.md` | partial | No external benchmark exists to compare against; state that explicitly rather than inventing one |
| C4 | A warning fires before the hard cost cap is hit | Internal | The cap answers 429 only after the daily sum is exceeded; no earlier warning | gap | Add an 80%-of-cap warning log/alert |
| C5 | Cost is broken down by tier/model for optimization | Internal | Per-call breakdown lands on each trace via `TraceCollector`, but nothing aggregates it | partial | Extend `scripts/spend.sh` to group by tier |

## 2. First-90-days KPIs

| KPI | Target range (published) | Source | Computable from `traces` today? |
|---|---|---|---|
| Containment rate (resolved without human) | 20-40% in the first ~6 months, 70-90% once mature | [Alhena AI](https://alhena.ai/blog/ai-chatbot-containment-vs-deflection-rate/) | No — no "resolved"/"escalated" flag is written to a trace |
| Channel share of total 311 volume | Realistically small at first — Atlanta's 311 bot handled 1.79% of requests in year one, 2.58% in year two | [arXiv:2506.12259](https://arxiv.org/abs/2506.12259) | No — needs total non-bot 311 volume, which this system never sees |
| First-contact resolution (FCR) | 70%+ for the contact types actually in self-service scope | [StealthAgents](https://stealthagents.com/research/first-contact-resolution-statistics-2026) | Partial — no explicit "resolved" signal, but a proxy exists: sessions with no `needs_info` loop and no follow-up message |
| CSAT | ~89% on non-escalated turns, ~67% once escalated to a person | [StealthAgents](https://stealthagents.com/research/customer-support-escalation-statistics-2026) | No — no feedback/rating is ever captured in the UI or the database |
| Uptime | 99.9%+ typical target for an AI-backed service | [MavenAGI](https://www.mavenagi.com/glossary/ai-service-level-agreement) | No — `traces` only records completed turns, not uptime history; needs external monitoring |
| Escalation/referral rate | 20-35% reduction vs. no self-service triage (directional, not city-specific) | [StealthAgents](https://stealthagents.com/research/customer-support-escalation-statistics-2026) | Yes — `% of traces where tool_calls includes get_referral` |
| Latency (time to full answer) | Sub 2-5s target for chat-style AI services | [BuildMVPFast](https://www.buildmvpfast.com/blog/ai-agent-sla-uptime-accuracy-response-time-guarantee-2026) | Yes — `avg`/`p95` of `traces.latency_ms` |
| Intent routing accuracy | No external vendor number; internal golden-set baseline is 84-96.9% across runs | STATE.md eval history | Yes, via the eval harness; a live proxy is the distribution of `traces.confidence` |
| Tool-call error rate | No external benchmark found | Internal reliability signal | Yes — `% of tool_calls/calls entries carrying an "error" key` |
| Cost per conversation | No published municipal benchmark found | scope note (demo only) | Yes — `avg(cost_usd)` grouped by `session_id` |
| Tool-loop exhaustion rate (`tool_rounds = 4`) | No external benchmark; internal reliability signal | ARCHITECTURE.md "Traces" | Yes — `% of traces where tool_rounds = 4` |
| Multilingual coverage | Comparable municipal deployments (e.g. Phoenix myPHX311) build English+Spanish in as a baseline | [Granicus](https://granicus.com/blog/how-local-governments-can-use-ai-powered-chatbots/) | No — the system does not track reply language today |

Five of twelve are directly computable from `traces` as it exists; three more have a workable proxy.
The rest — containment, channel share, CSAT, uptime, multilingual coverage — need instrumentation
this system does not have: an explicit resolution/escalation flag, a feedback control in the UI, an
uptime monitor outside the app, and a language field on the trace row.

## 3. Ten questions a skeptical infrastructure engineer would ask

1. **"Scale the API to two replicas — what breaks?"** The in-process worker runs twice (safe but
   wasteful, because `advance()`'s row lock and conditional `UPDATE` already handle concurrent
   writers); the staff-login lockout counter is per-process, so a 6th failed attempt on replica A
   does not lock out replica B (`api/app/auth.py:47`); `MAX_CONCURRENT_STREAMS` becomes `N x 16`
   instead of one real ceiling.
2. **"Your Postgres and SeaweedFS data live in bind-mounted host directories — what's the DR story
   if that disk is lost?"** `scripts/backup.sh` does a `pg_dump -Fc` plus a tar of the SeaweedFS
   volume, but it runs manually and writes to `data/backups/` on the same host — no schedule, no
   offsite copy.
3. **"SSE streaming holds a DB session open for the whole turn — what happens under load?"** The
   pool is `5 + 10` sessions and `MAX_CONCURRENT_STREAMS=16` caps concurrent streams below pool
   exhaustion, so request 17 waits on the semaphore, not the pool — but there is no backpressure
   signal to anything in front of the API, because nothing is in front of it.
4. **"If LiteLLM or Bedrock throttles or hangs, does a resident get a stuck spinner?"** No — the
   model client has a 45s timeout and one retry, and the orchestrator wraps the whole turn so a
   failure returns a fallback reply with a 200, never a dropped connection. The LiteLLM container
   itself has `restart: unless-stopped` but no second instance or failover target.
5. **"pgvector uses an HNSW index built on an empty table — what happens at real KB scale?"** Not
   load-tested. It's correct at 120 chunks; `PRODUCTION_PLAN.md` §5 anticipates 20-30 department
   pages of crawl, still a small corpus, with no benchmark past that.
6. **"Your cost breaker runs `SUM(traces.cost_usd)` before every `classify()` call — does that
   become a hot path at real 311 volume?"** It's an unindexed-by-cost aggregate query per turn;
   `traces_created_idx` helps but the query was never benchmarked past demo traffic.
7. **"SeaweedFS enforces no S3 signature — what actually stops another process from reading every
   uploaded document and certificate?"** Network isolation only: the S3 port is `127.0.0.1`-only
   and the two unauthenticated SeaweedFS UIs are not published at all. There is no real
   authentication on the object store itself — the architecture doc says so directly.
8. **"The workflow worker polls every 3 seconds in the same process as the API — what happens to
   chat latency during a big worker tick?"** Not measured. Worker and chat requests share one
   asyncio event loop and one connection pool; there is no separate worker process or container to
   isolate that contention.
9. **"No TLS in the deploy script — is any of this actually encrypted?"** The browser-to-web and
   web-to-api hops are plain HTTP (`deploy/aws/README.md`: "No TLS and no domain"). The
   API-to-LiteLLM-to-Bedrock hop rides HTTPS to AWS itself, but every resident-facing hop does not.
10. **"`ENVIRONMENT=prod` fails closed on placeholder secrets — but what forces that check to run at
    all?"** Nothing outside the app's own pydantic validator. `deploy/aws/up.sh` sets
    `ENVIRONMENT=prod` correctly, but a manual `docker compose up` with `ENVIRONMENT=dev` left in
    `.env` would skip every one of those checks — there is no infrastructure-level gate on top of
    the code's own guard.

## 4. Out of scope for a demo — state it, don't half-build it

- TLS, a real domain, a CDN and a WAF (`deploy/aws/README.md` already says "No TLS and no domain")
- FedRAMP/ATO-style federal authorization review
- Real Accela / Salesforce / Treasurer write integrations (`PRODUCTION_PLAN.md` §3, §6 phased roadmap)
- OCR for scanned uploads (README.md, DESIGN.md "Limitations")
- Multi-replica-safe worker and rate limiter (this document, question 1)
- An independent Section 508/VPAT audit and a USWDS ".gov" banner
- A formal Language Access Program and a localized UI
- Staff SSO/roles and per-record resident authorization (README.md "Auth", "Human review")
- A written retention/disposal policy and a Public Records Act redaction workflow
- A data-processing/BAA agreement with AWS for Bedrock
- RAGAS- or LLM-judge-based evaluation at scale (PLAN.md §14 — the local model is too weak to judge itself)
- 24/7 monitoring, alerting and on-call
- An independent, published accuracy audit (the NYC MyCity precedent above is why this matters)

Naming these here, rather than shipping a partial version of each, is itself the production-readiness
answer this checklist is for.
