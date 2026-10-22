# Design notes

Why this is built the way it is. `docs/ARCHITECTURE.md` says what the pieces are and `docs/EXPLAINER.md`
what each file does; this is the reasoning, the alternatives I turned down, and the things that broke.

## The brief, and how I scoped it

The brief was one sentence: a city wants chatbots and virtual assistants to handle resident inquiries,
permit status, trash pickup schedules, starting a business with licensing questions, and city events. Five
subject areas, two different jobs mixed together — looking something up, and getting something filed — and
no statement of which matters more.

I decided the lookups are the product and the filings are the proof it is more than a FAQ. The assistant
answers across seven intents (`permits`, `business`, `trash`, `service_request`, `events`, `general`,
`smalltalk`) and runs three workflows end to end: a building permit application, a business tax certificate,
and a Get It Done service request. A resident uploads a PDF form or fills an inline form inside the chat,
and one state machine takes it from `submitted` to a certificate PDF a staff member issues.

The city is fictional but modelled on the real one: Sonnet agents read the real Development Services permit
families, the Treasurer's business tax rules, Environmental Services collection policy and Get It Done
categories into `research/`, and the schemas, fee formulas and FAQ text come from that synthesis. A generic
invented city would have been easier and much less convincing — "Business Tax Certificate, not business
license, filed within 15 days" is the kind of detail that tells an evaluator I read the source material.

I left out payments (every fee is an estimate; taking money is PCI scope and demonstrates nothing about the
agent), resident accounts (a browser session id ties a conversation together; the only auth is on the staff
side), OCR, Spanish (one probe answered it correctly, but I could not score Spanish mechanically, so I do
not claim it), and real write integrations — Accela and Get It Done have no public write API, so filing is
simulated and the UI says so.

## Five decisions that shaped everything

**1. Facts come from tools; policy comes from RAG.** Trash zones, permit statuses, fees and events are rows;
policy and FAQ prose is text. Rows are answered by function calls against Postgres, text by retrieval over a
pgvector knowledge base, and the split is enforced by which tools an intent is allowed to see. The
alternative was to embed everything, tabular data included, and let one retriever handle both. Retrieval
over tabular facts is the classic RAG failure: "what day is trash collected at 4521 Adams Ave" against an
embedded address table returns the nearest-sounding row, not the right one, and it fails silently. A SQL
lookup is exact, auditable, and appears in the trace with its arguments. Retrieval is itself hybrid for a
related reason — pgvector cosine top-8 fused with full-text top-8 by reciprocal rank fusion, because dense
search finds paraphrases and full-text pins exact strings like "SB-1186"; weighted score blending was
rejected because it needs tuning per corpus, where RRF needs no calibration between two incomparable scales.

**2. A classifier picks the intent; rules pick the model tier.** Every turn starts with a small model
classifying the message into `{intent, confidence, complexity, secondary_intents}`. `select_tier()` then
applies three rules in code: escalate if confidence is below 0.6, complexity is `high`, or there is a
secondary intent; otherwise use the smart tier. The reason is written as a sentence onto the trace, so "why
did this turn cost four cents" is answerable after the fact. The tiers are logical roles — `small`, `smart`,
`escalate`, `extract` — mapped to concrete models by environment variables; no model name appears in the
code. The alternative was a keyword router: regexes for "trash", "permit", "business". It would have scored
better on my own eval set and taught me nothing, because the evals exist to measure what the classifier does
and keyword patches would hide it. I allowed one non-model shortcut, a tracking-number regex, because
`PRM-`/`BTC-`/`SR-` literally *is* the domain. The honest version has a real cost: the classifier sits on
the critical path before the first token, which is why a streamed answer does not start faster.

**3. One OpenAI-protocol client, LiteLLM in front of Bedrock.** Every model call goes through
`app/llm/client.py`, which speaks the OpenAI protocol against `LLM_BASE_URL`. Ollama serves that natively;
Bedrock does not, so a LiteLLM gateway maps the four tier aliases plus `embed` to Bedrock model ids.
Switching providers is `cp .env.bedrock .env` and a rebuild, and I ran all five aliases against real Bedrock
in us-west-2 so that is a tested claim rather than an architectural intention. I rejected the Anthropic SDK
directly (no key on this machine, and it locks the provider in) and Bedrock's own OpenAI-compatible
endpoint, which I tested: it exposes only Haiku and rejects chat completions for the other Anthropic models.
The client is also where tracing, pricing and streaming live, so there is one place a call could go untimed
or unpriced. Extraction is the one tier that is not Claude: Amazon Nova Lite reads uploaded forms for its
300k window at $0.06/$0.24 per million tokens against Haiku's $1.00/$5.00, and it filled 12 fields of the
sample business tax form on the live run in 1,397 ms for $0.000135.

**4. A state machine owns status, and nothing else writes it.** `workflows/engine.py` holds one
`TRANSITIONS` table shared by all three application types. `advance()` is the only writer of
`applications.status`: it validates the transition, writes an `application_events` row, updates the status,
then runs the entry hook for the new status, so the audit timeline is a byproduct of moving rather than
something anyone has to remember to log. An illegal jump raises and the API returns 409. The alternative was
letting the agent drive the workflow. An application's status is a compliance artefact; a model deciding it
would be unauditable and occasionally wrong, with no upside. The model's only job here is extraction —
tracking numbers, fees and missing-field lists are templated from facts the engine already knows. I also
rejected a transition table per type: the research gives three vocabularies (DSD plan check, Treasurer, Get
It Done) with the same shape, and three tables would be three times the code plus three sets of staff
buttons.

**5. Evals report; nobody tunes to them.** The golden set is 59 questions in four categories — `standard`,
`adversarial`, `multi_turn`, `multi_intent` — split 40 dev / 19 holdout (33 standard, 13 adversarial, 6 multi-turn, 7 multi-intent). Scoring is entirely mechanical:
intent match, expected tool called, citations present when the item expects RAG, a loose keyword check, and
literal `must_contain_any` / `must_not_contain` guardrails. I rejected an LLM judge: the dev provider is a
7B local model and a judge built on it would be less reliable than the thing it judges. Mechanical scoring
is dumber, but it never quietly moves. The rule that matters more than the score is that the golden set is a
measurement, not a target — nobody edits a prompt, a router rule or a KB file because an item failed. One
change came out of an eval: the model was searching September 2023 for "events in September", so the system
prompt now carries today's date, which fixes every date question rather than the item that caught it. The
corollary I had to write down explicitly is that a scorer assertion may be widened after a run but a prompt
may not. Item 34 failed because the phrase list lacked "wasn't able to find" while the reply was correct.
Fixing a wrong test and tuning a prompt to a question are different acts, even though both move a number.

## Hybrid real data, and the honesty rule

Everything was fictional through the first five milestones. That is defensible for applications and
indefensible for a council district, so the demo is now split by whether a real source exists. Fictional:
applications, tracking numbers, workflow statuses, fee tables, the twelve trash zones and the 40 seeded
addresses — nothing this assistant files is real, because there is no public write API for permits or Get It
Done. Real and read-only: the City's ArcGIS geocoder, council districts, street sweeping, zoning, permit
records on file, and council-meeting agendas from the Granicus RSS feed, all public and unauthenticated,
with a 4-second timeout, a 10-minute in-process cache, and a fallback to seed data or a clean error — never
a 500. In between: trash collection days, where the City publishes no per-address schedule at all, so a
geocoded or ZIP-only address gets a ZIP-level answer from the fictional zones, labelled `confidence:
"zip-level"`, with a link to the City's real collection map to confirm.

The honesty rule is that the assistant has to say which kind of answer it is giving. Every tool result
carries `source: "live"` or `source: "seed"`, both appear in the trace next to the tool name, and the shared
preamble gives the model the sentence for each: "according to the City's live map data" or "based on demo
data". The nav badge says "demo — fictional applications, live City map data", because that is now two
claims rather than one, and the permits tool says out loud that `PMT-` numbers are the City's while
`PRM-2026-` numbers are this assistant's. I rejected making everything real: CSV pipelines for data that
gains nothing from being real, and no time to do it.

## What broke, and how I found it

On 2026-09-05 I stopped building and spent twelve turns using the running stack as a resident, against the
live Bedrock deployment rather than the golden set. It found more than the eval suite had, because a fixed
question set only asks what you already thought to ask. Each finding below is what broke, the eval item that
now pins it, and the fix.

**Organics on alternating weeks.** The assistant told a resident their organics went out in "Week A only":
the seed schema alternated organics with recycling, where real Environmental Services policy is trash and
organics weekly, recycling every other week. *Eval:* items 1 and 2 expect "trash and organics every
Wednesday; recycling every other Wednesday". *Fix:* `organics_week` stays in the schema for compatibility
and nothing reads it — no migration, one behavioural change.

**ISO-week jargon.** The same answers explained odd and even ISO weeks to residents, who cannot act on "Week
B". *Eval:* the trash items' expected answers name a date. *Fix:* `get_trash_schedule` computes
`next_recycling_date`; the zone notes and `trash.md` FAQs became one plain sentence.

**A fee that was never calculated.** Asked about opening a coffee shop, the assistant referred to "the
estimate above" having called no fee tool at all. *Eval:* items 47 and 49 name every tool that must be
called, and item 40 forbids the back-reference phrases ("as I mentioned", "I told you", "was approved by").
*Fix:* a preamble rule — never mention an estimate, fee or result you have not obtained from a tool in this
conversation; ask for the input, or call the tool with a stated assumption and say that it is one.

**A referral miss on a row that exists.** "Who issues the health permit" found nothing although the County
health permit row was in the table, because `get_referral` did a single substring match. *Eval:* item 47
requires `get_referral` alongside `estimate_business_tax`. *Fix:* the lookup splits the query into words of
four or more letters, matches each against topic, agency and note, and ranks by matched count; the profiles
list the topics on file so the model asks with words that exist.

**Model memory leaking in as fact.** Asked whether an RV could park overnight in Pacific Beach, the
assistant produced a confident answer with a permit fee out of its training data; nothing in the knowledge
base covered parking. *Eval:* the adversarial category, where `must_not_contain` includes "generally
speaking" on the out-of-scope items. *Fix:* two — a preamble rule that general knowledge of San Diego or
California rules is never a source, even hedged, and `parking.md`, `utilities.md` and `housing.md`, which
took the knowledge base from 82 chunks to 120.

**A real address that did not exist.** A resident typed a real Carmel Valley address and was told it was not
found; "trash day for 92130" had no path to an answer at all, because each address-taking tool did its own
exact match against 40 fictional rows. *Eval:* items 53 and 54 — a real unseeded address and a bare ZIP,
both of which must answer rather than refuse. *Fix:* one resolver, `app/live/geocode.py`, used by every
tool: seed row, then the City geocoder, then a bare ZIP, returning how it matched so the answer can be
labelled.

**The tool allow-list, not the prompt, behind the multi-intent failures.** Multi-intent tool use scored 50%:
"there's a pothole at 1002 Grand Ave, and what day is the trash picked up there?" answered one half and told
the resident the other was unavailable. The audit the milestone required before touching a prompt showed the
trash tool was simply not on the `service_request` profile's allow-list. *Eval:* item 48 names both tools.
*Fix:* cheap read-only lookups — schedules, events, council district, status, referral — ride on every
domain profile, while fee estimators, `start_application` and `create_service_request` stay behind their own
intent. The same audit found a tool whose schema required a `description` the validator never used, so the
model kept stopping to ask for it: a tool-contract bug, not a prompt problem.

**Geocoder and permit-layer quirks.** Two things only real endpoints teach you. The City locator scores
`SingleLine="202 C St"` in the sixties and `Address="202 C St"` at 100, and a comma-tailed address scores 58
against the wrong street — so the resolver sends `Address=` and retries on the part before the first comma,
because residents type the tail. And the permit layer's `LIKE` is case-sensitive while the geocoder returns
"202 C ST" against a stored "202 C St", so an address with 18 records returned none until both sides were
wrapped in `UPPER()`.

## Cost and latency

All numbers below come from the runs recorded in `STATE.md`. Phase 2 ran against a $10 budget and used about
$7.77 of app-side estimated Bedrock spend, tracked per turn from the `traces` table; the first five
milestones — every eval, smoke run and manual check across two days — cost $0.99 over 108 turns. A full
54-item eval run costs $1.30. The 32-item `standard` category on the final container costs $0.74 and scores
intent 96.9%, tool 100%, citations 100%, keywords 100%, guardrail 100%; across all 54 items at the 13:15
run, 94.4 / 88.9 / 100 / 96.3 / 98.1. `multi_intent` tool use went from 50% to 100% and `multi_turn` from
83.3% to 100% after the allow-list and schema fixes above — not a prompt tuned to those items.

The provider comparison is the number I would actually show. Same 30 questions, same prompts, same router,
same day; the only thing that changed is `.env`.

| | Ollama qwen2.5:7b | Bedrock Claude |
|---|---|---|
| dev intent / tool | 80.0% / 80.0% | 95.0% / 90.0% |
| holdout intent / tool | 90.0% / 90.0% | 90.0% / 100.0% |
| mean latency (dev / holdout) | 6.8 s / 6.0 s | 6.1 s / 6.3 s |
| total cost | $0.00 | $0.4991 |

About 1.7 cents a turn, and latency is a wash: the local 7B is slow because it is a 7B on a laptop, and the
Bedrock path spends most of its six seconds generating a longer, better answer. What money buys is
classification and tool selection, not speed — the argument for tiering rather than putting the largest
model on every turn. Streaming was my answer to the latency: the turn is written once as an async generator
of `status` / `tool` / `token` / `done` events, `/api/chat/stream` serves them as server-sent events, and
`/api/chat` drains the same generator, so evals and smoke cannot drift from what a resident sees.

## Limits, and what I would do next

- **First token is not fast.** The classifier runs before any answer token, so a resident waits through a
  full small-model call before the stream starts — time to first token stays above two seconds on a RAG
  answer. Classifying concurrently with retrieval, or skipping the classifier on a follow-up turn inside an
  established intent, would take most of that back.
- **No OCR.** A scanned PDF is stored and reported as unreadable — the most common real intake path, missing.
- **No write integrations.** Applications live in Postgres; production means Accela, SAP and Salesforce
  connectors plus retry and reconciliation. There is no Open311 or Accela write API to build against, so
  filing stays simulated and labelled.
- **One staff role.** A single seeded account with a scrypt password and a 12-hour cookie. Real deployments
  need SSO, roles, per-record authorisation, and a failed-login counter that is not per process.
- **Mechanical evals only.** 54 hand-written questions is a smoke test. At scale I would sample from real
  traffic, and revisit the no-judge rule once there is a frontier model on both sides: a judge is the only
  way to score answer quality rather than keyword presence, and the categories a phrase list handles worst
  (adversarial refusals, multi-turn coherence) are where scoring is weakest.
- **Observability is one table.** Traces answer "what did it do on this turn"; nothing answers "is the
  tool-error rate rising" or "has the classifier drifted". Metrics, alerting on tool-error rates and
  classifier confidence, and turn replay are the first things I would add.
- **PII.** Names, addresses, emails and phone numbers land in `traces` in the clear; redaction and retention
  limits come before any real resident touches this.
