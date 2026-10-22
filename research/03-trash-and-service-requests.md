# City of San Diego — Trash/Recycling/Organics Collection & Resident Service Requests (Get It Done)

Research date: 2026-09-02. Sources are cited inline; anything not directly confirmed on a
sandiego.gov page is labeled **[BEST GUESS]** and modeled on realistic mid-size-city 311 practice.

---

## 1. Overview and URLs

### A) Trash / Recycling / Organics (Environmental Services Department — ESD)
ESD runs curbside residential collection for single-family homes and small (≤4-unit) multi-family
properties inside city limits.

- Collection Services hub: https://www.sandiego.gov/environmental-services/collection
- Collection Schedules page: https://www.sandiego.gov/environmental-services/collection/schedule
- Collection Schedule Lookup tool (address → route/day): https://getitdone.sandiego.gov/CollectionMapLookup
- General Refuse Collection Information and Rules (what-goes-where, placement rules): https://www.sandiego.gov/environmental-services/collection/general
- Containers (replacement/repair/size change): https://www.sandiego.gov/environmental-services/collection/general/containers
- Container Check/Complaint Feedback: https://www.sandiego.gov/environmental-services/collection/cce
- Trash Service Updates (Measure B fee rollout): https://www.sandiego.gov/environmental-services/trash-service-updates
- Measure B background: https://www.sandiego.gov/environmental-services/trash-service-updates/measure-b
- "Talking Trash: What to Do about Missed Collections": https://www.sandiego.gov/get-it-done/talking-trash-what-do-about-missed-collections
- Missed Collection report form: https://getitdone.sandiego.gov/TSWNewReport?type=Missed+Trash
- Waste container size/service portal (property owners): https://wasteportal.sandiego.gov
- FAQ ("What's my trash pick up schedule?"): https://sdgov.my.site.com/ViewArticle?URLName=What-s-my-trash-pick-up-schedule
- Customer service: 858-694-7000 / trash@sandiego.gov

### B) Resident Service Requests (Get It Done)
Get It Done is the City's 311-style non-emergency reporting platform (web + iOS/Android app),
run through a case-management backend (TeamDynamix/ServiceNow-style workflow; see dataset dictionary).

- Program home: https://www.sandiego.gov/get-it-done
- Support/how-to: https://www.sandiego.gov/get-it-done-support
- Mobile app guide: https://www.sandiego.gov/get-it-done/how-to-get-it-done-on-the-new-mobile-app
- New report intake form: https://getitdone.sandiego.gov/TSWNewReport
- View/search existing reports (map + list): https://getitdone.sandiego.gov/TSWViewReportByList , https://getitdone.sandiego.gov/Index.html
- FAQ search: https://getitdone.sandiego.gov/SiteArticlesList
- Open Data — Get It Done Reports dataset (case-level records, since May 2016): https://data.sandiego.gov/datasets/get-it-done-reports/
- "Expect Delays with Your Report" (SLA/backlog disclosure): https://www.sandiego.gov/get-it-done/expect-delays-with-your-report
- 2022 City Auditor performance audit of Get It Done: https://www.sandiego.gov/sites/default/files/23-004_get_it_done_application_and_service_requests_management.pdf
- App stores: https://apps.apple.com/us/app/get-it-done-san-diego/id1065050595 , https://play.google.com/store/apps/details?id=com.connectedbits.sd311

---

## 2. Trash: Schedule Lookup, Holiday Shift, Sample Zones, Bin Rules

### How the schedule lookup works
1. Resident enters a street address into the **Collection Schedule Lookup** (getitdone.sandiego.gov/CollectionMapLookup) or the Get It Done app's map layer.
2. The lookup geocodes the address into an internal **collection route/zone** maintained by ESD (the City is divided into dozens of route areas, roughly aligned to service days Monday–Friday).
3. The tool returns the resident's **trash day**, **organics day** (same day as trash, weekly), and **recycling week/day** (every-other-week cadence — "Week A" or "Week B" alternating biweekly on the assigned weekday).
4. Residents are told to place containers "at the curb or alley by 6:00 a.m." on their assigned day and collection runs 6:00 a.m.–5:30 p.m. (route dependent). [Sources: https://www.sandiego.gov/environmental-services/collection , https://www.sandiego.gov/environmental-services/collection/schedule]

### Holiday-shift rule
- Observed holidays with no collection: New Year's Day, Memorial Day, Labor Day, Thanksgiving, Christmas Day.
- **Rule:** If a holiday falls on a weekday, that day's collection and every remaining collection day that week shifts forward (later) by one day. Example: holiday on Tuesday → Tuesday's route collects Wednesday, Wednesday's route collects Thursday, Thursday's route collects Friday, Friday's route collects Saturday.
- If the holiday falls on Friday, the whole week (all 5 route-days) can compress, and Saturday becomes a working collection day for the week's last route.
- Source: https://www.sandiego.gov/environmental-services/collection/schedule (holiday schedule page referenced from Collection Schedules).

### 12 sample zones/routes for dummy data
**[BEST GUESS / SYNTHETIC — for prototyping only, not official ESD route boundaries.]**
Modeled on the real cadence (weekly trash, weekly organics same day, biweekly alternating recycling).

| Zone ID | Neighborhood cluster (example) | Trash day | Organics day | Recycling day | Recycling cadence |
|---|---|---|---|---|---|
| Zone A | Clairemont / Bay Park | Monday | Monday | Tuesday | Alternating (Week A) |
| Zone B | Pacific Beach / Mission Beach | Monday | Monday | Tuesday | Alternating (Week B) |
| Zone C | La Jolla / University City | Tuesday | Tuesday | Wednesday | Alternating (Week A) |
| Zone D | Kearny Mesa / Serra Mesa | Tuesday | Tuesday | Wednesday | Alternating (Week B) |
| Zone E | North Park / University Heights | Wednesday | Wednesday | Thursday | Alternating (Week A) |
| Zone F | Normal Heights / Kensington | Wednesday | Wednesday | Thursday | Alternating (Week B) |
| Zone G | Mission Valley / Linda Vista | Thursday | Thursday | Friday | Alternating (Week A) |
| Zone H | College Area / Rolando | Thursday | Thursday | Friday | Alternating (Week B) |
| Zone I | Point Loma / Ocean Beach | Friday | Friday | Monday | Alternating (Week A) |
| Zone J | Southeastern San Diego | Friday | Friday | Monday | Alternating (Week B) |
| Zone K | San Ysidro / Otay Mesa | Monday | Monday | Wednesday | Alternating (Week A) |
| Zone L | Rancho Bernardo / Rancho Peñasquitos | Tuesday | Tuesday | Thursday | Alternating (Week B) |

### Bin rules quick table

| Bin | Color | Frequency | Goes in it | Never goes in it |
|---|---|---|---|---|
| Trash | Gray/black | Weekly | General non-recyclable household waste, food scraps (if not using organics), broken household items (bagged) | Liquids, hot ashes/coals, hazardous waste, construction debris, medical sharps |
| Recycling | Light blue | Biweekly (alternating) | Clean paper/cardboard, rigid plastics #1–2/5, metal cans, glass bottles/jars — placed loose, dry | Plastic bags/film, food-soiled items, textiles, electronics, batteries |
| Organics | Green | Weekly | Food scraps, yard trimmings, food-soiled paper | Plastic bags (incl. "compostable" bags unless permitted), liquids, treated wood, pet waste |

Sources: https://www.sandiego.gov/environmental-services/collection/general (placement/removal times, spacing, prohibited items); "What Goes Where?" multilingual guides linked from ESD.

**Container placement rules:** set out by 6:00 a.m., removed from the curb by 6:00 p.m. same day, and kept 3 feet from other containers, parked cars, poles, trees, and mailboxes. (https://www.sandiego.gov/environmental-services/collection/general)

---

## 3. Trash: End-to-End Workflows

### (a) Missed pickup report
1. Resident checks the ESD "Trash Service Updates" page or Get It Done map first to see if their route is flagged as delayed city-wide (weather, holiday backlog, truck breakdown). https://www.sandiego.gov/environmental-services/trash-service-updates
2. If not a known delay, resident submits a **Missed Collection** (a.k.a. "Missed Trash") report via Get It Done app/web (https://getitdone.sandiego.gov/TSWNewReport?type=Missed+Trash) or calls 858-694-7000, including address, bin type missed, and photo (optional).
3. System auto-creates a case (`service_name` = Missed Collection) with status **New**, routes it to ESD Collection Services dispatch.
4. ESD dispatch reviews the case against route logs; if legitimately missed, a same-day or next-business-day return crew is scheduled. Status moves to **In Process**.
5. Crew completes the return pickup (typically same day if reported before a route-specific cutoff, otherwise next business day — [BEST GUESS: cutoff ~2:00 p.m.]).
6. Case is marked **Closed** with an "action taken" note (e.g., "container serviced on return route"); resident optionally gets a status-change notification via app/email if they created an account. Source for status labels: https://www.sandiego.gov/get-it-done (In Process/Referred/Closed definitions) and https://www.sandiego.gov/get-it-done/talking-trash-what-do-about-missed-collections.

### (b) Bulky item pickup request
1. Resident (single-family/small multi-family customer) requests a **Bulky Item Pickup** via Get It Done app/web or by calling 858-694-7000.
2. Resident selects/lists items (furniture, large appliances, etc.) up to the per-visit item limit; **[BEST GUESS, commonly cited: 2 free bulky pickups per year, up to ~6 items per pickup]** — verify exact limits at pickup time as ESD periodically adjusts allowances.
3. System assigns a scheduled pickup date/window (often 1–3 weeks out) and creates a case with status **New** → **Scheduled/In Process**.
4. Resident places items at the curb (not blocking sidewalk/street) the night before or by a set morning time on the scheduled date.
5. ESD bulky crew collects items on the scheduled date; items not eligible (hazardous waste, construction debris, tires) are left with a notice explaining why.
6. Case is marked **Closed**; if items are left behind due to ineligibility, the case may be marked **Referred** (resident directed to a Household Hazardous Waste appointment or private hauler) instead of Closed.

### (c) Container replacement/repair request
1. Resident identifies the issue: container **missing/stolen**, container **damaged** (cracked, wheels broken, lid missing), or needs a **different size / additional container**.
2. Missing/stolen → submit "Replace Missing Container Request" via Get It Done or call 858-694-7000. Damaged → submit "Repair or Replace Damaged Container Request." Size change/extra container (property owner only) → wasteportal.sandiego.gov or 858-694-7000.
3. Case created with status **New**; ESD container-services queue reviews the request and, for billing-relevant changes (extra containers, size upgrades), cross-checks the account tied to the Recycling/Refuse Fee (see Measure B fee below).
4. A replacement/repair is scheduled — [BEST GUESS: typical delivery window 5–10 business days] — status **In Process**.
5. Crew delivers/repairs/swaps the container at the curb, usually without requiring the resident to be home.
6. Case marked **Closed** once delivery/repair is confirmed (crew logs container serial/RFID tag against the address).
Source: https://www.sandiego.gov/environmental-services/collection/general/containers

---

## Measure B / Trash Fee Context (background for both areas)
- **The People's Ordinance (1919, amended 1981/1986):** historically prohibited the City from charging single-family homes for trash collection while requiring it to provide the service.
- **Measure B (approved November 2022):** amended the People's Ordinance to let the City charge a monthly fee for residential solid waste/recycling/organics collection (single-family homes and small multi-family complexes up to 4 units). https://www.sandiego.gov/environmental-services/trash-service-updates/measure-b , https://ballotpedia.org/San_Diego,_California,_Measure_B,_Waste_Management_Measure_(November_2022)
- **Fee rollout:** billing began **July 1, 2025**; base rate reported at **$42.76/month** for three 95-gallon carts (trash + recycling + organics), independent of volume used. https://www.kpbs.org/news/living/2025/09/12/san-diego-reminds-residents-of-sept-30-deadline-to-select-new-trash-pickup-plan , https://www.insidesandiego.org/city-san-diego-adopts-new-trash-fee
- **FY2028–29 update:** June 2026 Council action revised the fee schedule and **deferred** the previously-funded expansion to weekly recycling and expanded bulky-item pickup programs through FY2029 due to reduced fee revenue collection. [Source found via search of NBC San Diego coverage; treat exact figures as **[BEST GUESS — verify current rate before using in production]**.]

---

## 4. Service Requests: Categories, Routing, Status, SLAs, Form Fields

### Category list (20+; Get It Done groups ~65+ specific service types under these top-level categories)
1. Pothole / street pavement repair
2. Graffiti removal (public and private property visible from street)
3. Streetlight out / traffic signal issue
4. Missed trash/recycling/organics collection
5. Illegal dumping
6. Homeless encampment / homeless outreach referral
7. Parking enforcement (72-hour parking violation, blocked driveway, etc.)
8. Tree trimming / damaged tree / tree down
9. Sidewalk repair / trip hazard
10. Stormwater / drainage issue (clogged drain, flooding)
11. Weed abatement / overgrown vegetation on public right-of-way
12. Dead animal removal
13. Abandoned vehicle
14. Container left out past collection hours
15. Damaged or missing trash/recycling/organics container
16. ADA accessibility complaint (curb ramp, sidewalk obstruction)
17. Short-Term Residential Occupancy (STRO) violation
18. Code enforcement — private property/building maintenance violation
19. Park facility issue (playground equipment, restroom, irrigation)
20. Dumpster encroaching on public right-of-way
21. Household Hazardous Waste drop-off appointment request
22. Bulky item pickup request
23. "Other" — catch-all for issues not matching an established category

Sources: https://www.cbs8.com/article/news/local/working-for-you/get-it-done-app-nears-10-year-mark-san-diego-millions-service-requests/509-7c8730cc-8daf-4b84-8c3d-c189d54ba493 ; https://www.sandiego.gov/get-it-done ; https://data.sandiego.gov/datasets/get-it-done-reports/ (case_record_type/service_name taxonomy).

### Department routing map

| Request category | Routed department |
|---|---|
| Pothole, sidewalk repair, street resurfacing | Transportation Dept. (Streets Division) |
| Graffiti removal | Transportation Dept. / ESD (multi-department in practice) |
| Streetlight/traffic signal out | Transportation Dept. (Traffic Engineering) |
| Missed collection, container issues, illegal dumping (residential), bulky item, HHW | Environmental Services Dept. (ESD) |
| Homeless encampment/outreach | Homelessness Strategies & Solutions Dept. |
| Parking enforcement, abandoned vehicle | Police Dept. — Parking Enforcement / Neighborhood Policing |
| Tree trimming, weed abatement, park facility issue | Parks & Recreation Dept. (Urban Forestry / Park Maintenance) |
| Stormwater/drainage | Transportation Dept. — Stormwater Division |
| ADA complaint | ADA Compliance / Transportation |
| STRO violation | Development Services Dept. (Code Enforcement) |
| Code enforcement (private property/building) | Development Services Dept. (Code Enforcement) |
| Dead animal removal | Environmental Services Dept. / Animal Services (varies by location: street vs. private) |
| Passport service appointment / "Other" | City Clerk / General Services intake, triaged manually |

**[BEST GUESS for exact department names/splits — the City's org chart occasionally moves these divisions; verify current department names against sandiego.gov org chart before hard-coding.]**

### Status vocabulary
- **New** — case submitted, not yet triaged/assigned. [BEST GUESS label; confirmed states below are official]
- **In Process** — City staff assigned and actively working the issue (shown as green in the app). https://www.sandiego.gov/get-it-done
- **Referred** — case handed to an outside agency (e.g., Caltrans for a state highway, SDG&E for a utility pole) or an internal department not yet integrated with Get It Done; no further status updates typically follow.
- **Closed** — issue resolved; resident can open the case to view the "action taken" note.
- (Some categories also show **Duplicate**, linked via `service_request_parent_id` in the open-data schema, when multiple residents report the same issue.)

Sources: https://www.sandiego.gov/get-it-done ; https://data.sandiego.gov/datasets/get-it-done-reports/

### Typical SLAs (turnaround expectations)
**[BEST GUESS — exact SLA targets by category were not published in a single accessible source during this research pass; the City Auditor's Oct 2022 performance audit (PDF) likely contains category-level targets but the file did not extract as text. Figures below are realistic placeholders based on comparable mid-size-city 311 programs and press coverage of Get It Done backlogs.]**

| Category | Target first response | Target resolution |
|---|---|---|
| Missed collection | Same day–next business day | 1–2 business days |
| Illegal dumping | 1–3 business days | 5–10 business days |
| Pothole | 3 business days (safety-flagged faster) | 30–45 days |
| Graffiti (public) | 3–5 business days | 10 business days |
| Streetlight out | 5 business days | 15–30 days |
| Encampment report | 3–5 business days | Varies (weeks; multi-agency) |
| Parking enforcement (72-hr) | 3–5 business days | Highly variable — press coverage cites 14 days average in some areas, 125+ days in others |
| Tree trimming (non-emergency) | 5 business days | 60–90 days |
| Container repair/replace | 5 business days | 5–10 business days |

Press context on real-world delay: an Axios San Diego piece (March 2026) reported Get It Done facing a backlog with growing complaint volume; a Hoodline piece cites the app "drowning in 85,000 complaints." (https://www.axios.com/local/san-diego/2026/03/25/get-it-done-app-backlog-complaints-delay , https://hoodline.com/2026/03/san-diego-s-get-it-done-app-drowning-in-85-000-complaints/) — actual SLA performance often lags published targets.

### Fields a request form collects
Based on the Get It Done intake form and open-data schema (https://getitdone.sandiego.gov/TSWNewReport , https://data.sandiego.gov/datasets/get-it-done-reports/):
- **Category/service type** (dropdown, e.g., "Missed Trash," "Pothole")
- **Sub-type/detail** (e.g., "Path/Walkway/Road Pavement/Pothole")
- **Location** — street address or map pin (lat/long captured), auto-resolves council district (1–9) and community plan area
- **Description** (free text, `public_description`)
- **Photo upload** (optional but encouraged, especially for graffiti/dumping/pothole)
- **Contact info** — name, email, phone (optional for anonymous reports on most categories; required for some like code enforcement)
- **Source/origin of report** (`case_origin`: Web, Mobile app, Phone, Staff-entered)
- **Date/time requested** (auto-timestamped)
- **Case ID** (system-generated, used for status lookup)
- For duplicates: `service_request_parent_id` linking to an existing open case

---

## 5. Top 20 Resident FAQ (RAG seed content)

1. **What day does my trash get picked up?**
   Look up your address at the Collection Schedule Lookup (getitdone.sandiego.gov/CollectionMapLookup) — it shows your trash, recycling, and organics days. Trash and organics collect weekly on the same day; recycling collects every other week. (https://www.sandiego.gov/environmental-services/collection/schedule)

2. **Why didn't my recycling get picked up this week?**
   Recycling is collected biweekly (alternating weeks), not every week — check your specific Week A/B assignment in the schedule lookup before reporting a miss.

3. **What time do I need to put my bins out?**
   Bins must be at the curb/alley by 6:00 a.m. on your collection day and removed by 6:00 p.m. the same day. (https://www.sandiego.gov/environmental-services/collection/general)

4. **My trash wasn't picked up — what do I do?**
   First check the Trash Service Updates page for known delays; if your route isn't listed, file a "Missed Collection" report via Get It Done or call 858-694-7000. (https://www.sandiego.gov/get-it-done/talking-trash-what-do-about-missed-collections)

5. **How does the holiday schedule work?**
   No collection on New Year's Day, Memorial Day, Labor Day, Thanksgiving, or Christmas. If a holiday falls on a weekday, that day's route and all remaining routes that week shift one day later.

6. **What can I put in my recycling bin?**
   Clean, dry, loose paper/cardboard, rigid plastics, metal cans, and glass — no plastic bags or food-soiled items. See the "What Goes Where?" guide.

7. **Can I put food scraps in my green bin?**
   Yes — food scraps and yard waste go in organics; avoid plastic bags (including most "compostable" bags unless explicitly permitted).

8. **How do I get a bulky item picked up?**
   Request a Bulky Item Pickup through Get It Done or call 858-694-7000; residents typically get a limited number of free pickups per year with an item cap per visit. **[BEST GUESS on exact limits — verify current allowance.]**

9. **My trash can is broken/missing — how do I get a new one?**
   Submit a "Repair or Replace Damaged Container" (for damage) or "Replace Missing Container" (for stolen/missing) request via Get It Done, or call 858-694-7000. (https://www.sandiego.gov/environmental-services/collection/general/containers)

10. **How do I get a bigger or an extra trash can?**
    Property owners can request size changes or extra containers at wasteportal.sandiego.gov or by calling 858-694-7000.

11. **Why am I being charged a trash fee now?**
    Voters approved Measure B in 2022, letting the City charge for residential trash/recycling/organics service for the first time in over a century; billing began July 1, 2025 (~$42.76/month for the standard three-cart service). (https://www.sandiego.gov/environmental-services/trash-service-updates/measure-b)

12. **Does the trash fee apply to apartments/condos?**
    The fee generally applies to single-family homes and small multi-family properties (up to 4 units) that receive City collection; larger multi-family/commercial properties use private haulers and are billed separately. **[BEST GUESS — confirm exact unit-count threshold.]**

13. **How do I report a pothole?**
    Submit a "Pothole" report via Get It Done (web or app) with the location and a photo if possible.

14. **How do I report graffiti?**
    Submit a "Graffiti" report via Get It Done; include the address/location and a photo — most public graffiti is targeted for removal within about a week.

15. **How do I report illegal dumping?**
    Submit an "Illegal Dumping" report via Get It Done with the location and photo; do not attempt to remove hazardous materials yourself.

16. **How do I check the status of a report I submitted?**
    Use your case ID at getitdone.sandiego.gov (View Reports) or in the Get It Done app; statuses are New, In Process, Referred, or Closed.

17. **What does "Referred" status mean?**
    Your report was sent to an outside agency (e.g., Caltrans, a utility) or a City department not yet integrated into Get It Done; no further status updates are typically provided after that.

18. **How long will it take for my request to be resolved?**
    It varies widely by category — missed collection is usually next business day, while infrastructure items like potholes or streetlights can take weeks. See SLA table in Section 4. **[BEST GUESS ranges — the City does not publish a single authoritative SLA sheet publicly.]**

19. **Can I report an issue anonymously?**
    Most Get It Done categories don't require contact info, but providing an email lets you receive status updates and reduces duplicate follow-up calls.

20. **What's the difference between Get It Done and calling 911 or the non-emergency police line?**
    Get It Done is for non-emergency City service issues (potholes, missed trash, graffiti, code violations). Life-threatening emergencies should always go to 911; non-urgent police matters (not requiring dispatch) go to the police non-emergency line, not Get It Done.

---

## 6. Backend Automation Opportunities (document/form-intake + LLM workflow)

1. **Auto-classification of free-text submissions** — Many residents describe an issue in free text or upload a photo without picking the right category; an LLM classifier (photo + text) could map the request to one of the ~65 Get It Done service types (and the ~20+ rolled-up categories in Section 4) with a confidence score, reducing manual re-categorization by City staff.

2. **Auto-routing to department** — Once classified, an automation layer applies the category → department routing table (Section 4) to pre-assign the case, cutting the "New → triaged/In Process" hop that today likely requires staff review, especially for high-volume categories like missed collection and graffiti.

3. **Deduplication** — Cluster incoming reports by geolocation + category + time window (e.g., 5 reports of "pothole" within 50 meters in 48 hours) and auto-link them via `service_request_parent_id`-style relations instead of opening N separate cases — directly addresses the backlog/volume complaints reported by Axios/Hoodline (Section 4 SLA notes).

4. **Photo/text quality gate** — Flag submissions missing required info (no address resolvable, no photo for photo-preferred categories like graffiti/dumping) and auto-prompt the resident for the missing field before the case reaches a human queue.

5. **Missed-collection triage against route data** — Cross-reference a "Missed Collection" report's address against the ESD route/zone schedule (Section 2) and known service-delay flags (from the Trash Service Updates feed); auto-resolve/auto-close reports that fall inside a published delay window with an explanatory reply, and only escalate genuine misses to dispatch.

6. **Auto-drafted resident reply / status-change notification** — Generate a plain-language status update ("Your missed-collection report for 123 Main St has been scheduled for pickup tomorrow") whenever a case's status field changes, using the case's category, action-taken notes, and standard FAQ language (Section 5) as grounding.

7. **SLA-breach monitoring and escalation** — Track `date_requested` vs. category SLA targets (Section 4) and auto-escalate/flag cases approaching or past target, which is exactly the failure mode press coverage says the current system struggles with (85k-complaint backlog, 125-day parking cases).

8. **Auto-close verification loop** — For categories with clear physical verification (container repaired, bulky items picked up), use crew-logged completion timestamps or a resident-submitted confirmation photo to auto-transition a case from In Process to Closed rather than waiting on manual sign-off.

9. **Referral hand-off drafting** — For cases that belong to outside agencies (Caltrans, SDG&E, county), auto-draft the referral packet (location, category, photo, description) formatted for the receiving agency's intake, reducing the "Referred, no further updates" dead-end residents currently experience.

10. **Duplicate-container/fee-account reconciliation** — For container replacement/size-change requests, auto-check the request against the Measure B billing account (Recycling/Refuse Fee) tied to the address so container-count changes and billing stay in sync without a separate manual billing update step.

11. **RAG-grounded resident chatbot** — Use the Section 5 FAQ set (plus the official "What Goes Where?" and schedule-lookup data) as the retrieval corpus for a resident-facing chat/voice assistant that answers "what day is my trash" or "why was I charged $42.76" without opening a case at all — deflecting simple lookups from the Get It Done queue entirely.

---

*Line count target: ≤450. All URLs above point to sandiego.gov, getitdone.sandiego.gov, or data.sandiego.gov domains unless otherwise noted as press/secondary sources for context (KPBS, NBC San Diego, Axios, Hoodline, Ballotpedia, insidesandiego.org).*
