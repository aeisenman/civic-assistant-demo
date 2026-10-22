# Demo script (10 minutes)

Rehearsable. Text to type is in `>` blocks; one line of narration per beat. Phase 2 (2026-09-05)
added real City data behind the same tools, three new KB topics, and a wider eval set — this
script now walks through those, and drops the incomplete-form-recovery and voter-registration
beats from the phase-1 script to stay near ten minutes (both still work; ask if there's time).

## Setup checklist (do this 5 minutes before)

1. `bash scripts/reset_demo.sh`, and wait for it to print the URLs.
2. Confirm which `.env` is active: this script assumes `.env.bedrock` (real Bedrock, live City
   data on). On the Ollama profile everything runs except the live-data and web-search beats.
3. Sign in as staff once: open <http://localhost:3001/login>, use `STAFF_USERNAME` /
   `STAFF_PASSWORD` from `.env` (the profiles ship `staff` / `staff`), and check the nav says
   "Signed in as City Staff". The session lasts 12 hours, so this survives the whole demo.
4. Four browser tabs: <http://localhost:3001> (the resident app), `/staff` (the queue),
   `/staff/dashboard` (reporting) and `/staff/traces`.
5. A Finder window at `api/forms/`, so the two PDFs are one drag away.
6. Warm the stack up: send "hi" in the chat and wait for the reply, so the first real answer
   is not paying a cold LiteLLM/KB-ingest roundtrip.
7. Check the nav pill is green, and read the badge next to it: "demo — fictional applications,
   live City map data". That sentence is the honesty story for beat 5 — point at it now.

## Beats

### 1. Trash pickup, the trace, and the address resolver (110 s)

> What day is my trash picked up at 4521 Adams Ave?

Expect: the zone, the collection day and the next recycling date, with citation chips. No "ISO"
or "Week A/B" language — trash and organics are weekly, recycling alternates, and the tool
computes an actual date. Click the **Trace** line under the reply and point at the model-calls
table: one small-tier classification, one smart-tier tool call, one smart-tier answer.

Now show the part that did not work in phase 1:

> What day is trash picked up at 10615 Calle Mar de Mariposa?

That address was never in the seed table. Expect a real answer anyway: "Based on demo data,
here's what I found for 10615 Calle Mar de Mariposa (92130) ... this answer came from a
ZIP-code-level lookup, not a per-address match. Please confirm your specific street's collection
day at getitdone.sandiego.gov/CollectionMapLookup." Open the trace: `match: "geocoded"` — the
City's real geocoder resolved the street address to a ZIP, then the fictional zone map took over
from there. Say: "One resolver now backs every address-taking tool: exact seed match, then the
real City geocoder, then a bare ZIP as a last resort. A resident used to get 'not found' for any
address we hadn't typed into a JSON file by hand. Same thing happens for a bare ZIP with no street
at all — 'when is the trash day for 92130' answers instead of failing outright."

### 2. Trash without an address: the holiday case (25 s)

> Is trash pickup delayed next week for Labor Day?

Expect an answer with no address on file: "Yes! Labor Day falls on Monday, September 7, 2026...
So every route that week runs one day later than usual... If you'd like to know your specific
pickup day and exact shifted date, just share your address." Say: "A new `get_holiday_schedule`
tool answers the general question first and only then offers to narrow it down — it doesn't stall
on 'what's your address' when the question didn't need one."

### 3. Business tax, a fee with its tiers (40 s)

> How much is a business tax certificate for 3 employees?

Expect: the base fee, the SB-1186 accessibility fee and the minimum wage enforcement fee, about
$43.88, labelled an estimate. Say: "The arithmetic is a pure function in `tools/fees.py`, shared
with the validator, so the number quoted is the number filed."

### 4. Events, and knowing what day it is (25 s)

> What's happening this weekend?

Expect: events from the seeded calendar for the coming weekend, not 2023, and — new in phase 2 —
real council meeting agendas pulled from the City's Granicus RSS feed merged in alongside them.
Say: "Early on the model searched September 2023, because it had no idea what day it is. Every
system prompt now ends with today's date; that's in DECISIONS.md. The meeting agendas are the one
piece of 'events' that's genuinely live now, not seeded."

### 5. Live City data, and the honesty story (85 s)

> Who is my council member if I live at 202 C St?

Expect: "According to the City's live map data, 202 C St (92101) is in Council District 3,
represented by Stephen Whitburn. You can reach his office at (619) 236-6633..." — a real district,
a real name, a real phone number, straight from the City's ArcGIS council-district layer, not a
seed row. Open the trace: `source: "live"`, `match: "geocoded"`.

Say: "That phrase — 'according to the City's live map data' — is not decoration. When a tool
result is real, the model is told to say so; when it falls back to our fictional zone table it
says 'based on demo data' instead, same as the trash answer a minute ago. That's also why the nav
badge reads 'fictional applications, live City map data' rather than just 'demo data': the
applications and tracking numbers in this system are still make-believe because there is no
public write API for permits or Get It Done — but street sweeping, zoning, council districts and
permit records on file are real City data now. If the City's geocoder or ArcGIS is slow or down,
every live call times out at 4 seconds and falls back to the seed table cleanly — it never 500s."
If there's time, ask the same style of question for street sweeping ("When is street sweeping on
C St downtown?") or permits ("Are there any permits on file for 202 C St?") — the second one
returns real PMT- numbers, and the model explains those are City records, distinct from this
demo's own PRM-/BTC-/SR- tracking numbers.

### 6. A question the old KB could not answer (60 s)

> Can I park my RV on the street overnight in Pacific Beach?

Expect a real, cited answer: "Based on the City's rules, not by default. San Diego's Neighborhood
Parking Protection Ordinance prohibits any vehicle... over 27 feet long and 7 feet tall from
parking on a public street between 2:00 a.m. and 6:00 a.m... However, there is a legal option:
the Temporary Overnight RV Permit (TORVP)... $1.50... up to 3 consecutive days... 72 permits per
year." Say: "One of the twelve live probes that kicked off phase 2 asked this exact question and
the model made up a fee from general knowledge — there was no parking content in the KB at all.
`parking.md`, `utilities.md` and `housing.md` are new; they're retrieved the same unfiltered way
as every other `general` question, cited the same way, and the strict-sources rule means the
model won't fall back to its own memory anymore. Water bills and short-term rental licensing work
the same way now."

### 7. A guardrail: no speculation on data that doesn't exist (30 s)

> What's the status of tracking number SR-2026-999888?

Expect a clean miss, not an invented status: "Unfortunately, the system couldn't find tracking
number SR-2026-999888... If you believe the number is correct... please call the City's general
line at 619-236-5555." Say: "No guessed status, no apology-shaped hallucination — the tool result
comes back empty and the model is told never to state a number or a result it hasn't actually
gotten from a tool this conversation. That rule is what stopped the RV-parking guessing before
the KB existed, too."

### 8. Upload a permit application (75 s)

Paperclip, choose `api/forms/sample_permit_application.pdf`; the chip says "300+ chars
extracted". Then send:

> Here is my permit application.

Expect: the extracted fields, a tracking number `PRM-2026-0004xx`, the department, an estimated
fee, and a green tracking card. Say: "The upload went to SeaweedFS, pypdf pulled the text, and
the extract tier filled the same pydantic model that renders the form and drives validation. The
reply is templated, not generated: I do not want a model paraphrasing a tracking number."

### 9. Staff queue: watch it move, then issue it (75 s)

Switch to `/staff`. The new `PRM-` row should already be `in_review`. Say: "A worker in the API
process polls every three seconds. It moved this from submitted to validating; the validator
found nothing missing, so it routed, then routed to in_review. Everything after that needs a
person." Click the row, point at the timeline, then **Advance to approved**, **Advance to
issued**, **Download certificate**. Say: "Issuing runs the entry hook for that status, which
renders a PDF into object storage. The engine is the only thing that can change a status, so the
audit trail cannot be skipped." If asked who "staff" is on the timeline: that is the username of
the account signed in — the whole `/staff` console and certificate downloads are behind a real
login (scrypt password, HttpOnly session cookie), because this side of the app issues documents.

### 9b. Optional, if time: the incomplete form, and filling the gap in chat (90 s)

Back in the chat, attach `api/forms/sample_permit_incomplete.pdf` and send:

> And here is the one for the garage.

Expect: a tracking number and "I still need: permit type, valuation (USD)"; the queue shows
`needs_info`. Then reply:

> The permit type is Building Permit with Plans and the valuation is $80,000

Expect: "I've updated PRM-2026-0004xx", then the queue moves it to `in_review` with a fee.
Say: "The follow-up is extracted against a narrowed schema holding only the missing fields,
merged, and resubmitted. The state machine re-validates from scratch, so it decides
completeness, not the model." This is the clearest view of the workflow engine; skip it only
if the clock says so.

### 9c. Optional, if asked "how hard is a new form?": the STRO licence (20 s)

Attach `api/forms/sample_stro_application.pdf` and send it — it files as `STR-2026-0005xx` and
reaches `in_review` on its own. Say: "That fourth type is a pydantic model, a validator branch, a
fee table, a tracking sequence and a PDF title. The status spine, the worker, the staff page and
the API did not change."

### 10. Traces and the eval story (80 s)

Switch to `/staff/traces` and refresh. Every turn from this demo is a row: intent, tier, model,
tokens, latency, cost. Expand one to show the tool JSON and its `source`/`match` fields. Then
click **Dashboard**: the same rows aggregated in SQL — turns and cost per day, intent and tier
mix, tool calls and their error rate, citation rate, and the ten most recent questions the
assistant answered with no sources behind it, which is the list of what to write next.

Say: "The golden set grew this week from 30 questions with 10 held out to 54 with 18 held out —
adversarial, multi-turn and multi-intent categories on top of the original single-turn set,
still scored mechanically, still never used to tune a prompt. Running all 54 on this stack this
morning: standard questions score 96.9% intent, 93.8% tool choice, 100% citations, 100% keyword
match, 100% guardrail. Adversarial — prompt injection, unknown addresses, out-of-scope questions
— is 80/100/100/90/90. Multi-turn, where a follow-up like 'and recycling?' has to resolve against
an address given a turn earlier, is 100/83/100/83/100. Multi-intent — two requests in one
message, like a pothole report plus a trash-day question — is where it's weakest: 100% intent,
but only 50% of those turns actually call every tool the request needed; it answers one half and
drops the other. That's a known, named weakness, not a hidden one — there's a milestone open
right now to fix it with an 'act on everything, then ask' prompt rule, and it isn't done, so I'm
not going to give you a number for it today." (If M10 has landed by the time you give this demo,
update this beat with its own before/after multi-intent numbers instead of saying it's in
progress.)

### 11. The provider swap, and what phase 2 cost (55 s)

Show `.env.ollama` next to `.env.bedrock`. Say: "The API speaks only the OpenAI protocol and
never names a model, it names a tier. Swapping providers is `cp .env.bedrock .env` plus one
compose profile that starts a LiteLLM gateway mapping small, smart, escalate, extract and embed
to Haiku, Sonnet, Opus, Nova Lite and Titan. `deploy/aws/up.sh` puts the same stack on one EC2
instance with a Bedrock-scoped instance role. This whole phase-2 day — the twelve live probes
that found the bugs, all the KB and live-data work, every eval run including the 54-question one
you just saw — cost about $5 of real Bedrock spend against a $10 budget the author set, tracked
turn by turn with `scripts/spend.sh` against the `traces` table. That number is a big part of why
tiering by task instead of running everything on the biggest model matters."

## If something breaks

| Symptom | Why | What to do on the spot |
|---|---|---|
| First answer takes 10-30 s or times out | LiteLLM/KB ingest just started, or (Ollama profile only) a 7B model is cold-loading into memory | Say so, it is honest. This is why step 5 of the checklist exists. Keep talking; it arrives. |
| The nav pill is red | One of db / s3 / llm / embed is down | Hover it, it names the component. `docker compose logs api --tail 30`. `/health` is deliberately per-component rather than a 500. |
| A live-data answer says "based on demo data" where you expected "live map data" | The address only matched the seed table, or the City's ArcGIS endpoint timed out (4 s) and the tool fell back | That's the fallback working as designed, not a bug — say so, and point at `source` in the trace's tool call. |
| The model answers without calling the tool | The model dropped a tool call, especially after a long turn | Open the trace and show it: this is exactly the failure the eval numbers measure. Re-ask more directly ("look up 4521 Adams Ave"). |
| The model invents a tool, or bad arguments | JSON slip on a smaller model or a schema mismatch | `dispatch()` returns an error string instead of raising, so the model gets another round. Show the error in the trace. |
| A question answers from general knowledge instead of citing a source or declining | Strict-sources rule regression (should not happen post-M6) | Open the trace, check `rag_chunk_ids`/`tool_calls` are empty, and say this is exactly the class of bug the 2026-09-05 probes were built to catch. |
| Upload says "no text found" | The PDF is a scan, and there is no OCR | Intended behaviour: say the demo has no OCR and offer to type the details. The committed sample PDFs are text-based. |
| An application sits in `submitted`, or the queue does not update | Worker off, or the 5 s poll | Check `WORKER_ENABLED` in `.env` and `docker compose logs api`. Click a filter to force a refetch. |
| A web-search question ("How do I get a library card?") gets the "not configured" line | `SEARCH_PROVIDER=none` — no Brave key has been decided on yet | Say so; it is honest and it is exactly what the tool is supposed to do when it is off, not a crash. |
| Everything is wrong | Stale database state | `bash scripts/reset_demo.sh`, about a minute. |
