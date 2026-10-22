# Top Resident Questions — Benchmarking Reality vs. the KB

Purpose: what residents actually ask a city, sourced, so the 9-topic KB (`api/kb/`: trash, permits,
business, service_requests, events, general, parking, utilities, housing) and 16 tools
(`api/app/tools/registry.py`) can be benchmarked against real demand instead of invented questions.
San Diego sources first; peer cities corroborate categories San Diego does not itself rank.

## 1. Top 25 resident request categories by volume

No San Diego source publishes a full ranked top-25. The 2022 City Auditor report is the only
place San Diego itself ranks categories with numbers (6 of them, out of CY2021's 296,209 total
Get It Done reports). Categories 7–25 are not numerically ranked by any San Diego source found;
peer-city 311 data corroborates that they are high-volume nationally, and SD KB/tool coverage is
noted so the gap is explicit rather than assumed.

| # | Category | San Diego evidence | Peer corroboration | SD KB / tool status |
|---|---|---|---|---|
| 1 | Pothole repair | 36,827 reports, 12.4% of CY2021 total. [City Auditor 23-004](https://www.sandiego.gov/sites/default/files/23-004_get_it_done_application_and_service_requests_management.pdf) | — | `service_requests.md`; `create_service_request` |
| 2 | Graffiti removal | 29,530, 10.0%. [Auditor 23-004](https://www.sandiego.gov/sites/default/files/23-004_get_it_done_application_and_service_requests_management.pdf) | LA: 317,000, 22.4% of 1.42M (2024). [Crosstown](https://xtown.la/2025/01/21/myla311-reports-in-los-angeles-rise-5-2-in-2024-graffiti-removal-bulky-item-pickup/) | `service_requests.md`; `create_service_request` |
| 3 | "Other" / uncategorized | 28,042, 9.5%. [Auditor 23-004](https://www.sandiego.gov/sites/default/files/23-004_get_it_done_application_and_service_requests_management.pdf) | — | n/a — catch-all |
| 4 | Dead animal removal | 21,628, 7.3%. [Auditor 23-004](https://www.sandiego.gov/sites/default/files/23-004_get_it_done_application_and_service_requests_management.pdf) | LA: 32,398, highest annual total ever recorded (2024). [Crosstown](https://xtown.la/2025/01/21/myla311-reports-in-los-angeles-rise-5-2-in-2024-graffiti-removal-bulky-item-pickup/) | gap — no KB topic or tool |
| 5 | Streetlight outage | 20,403, 6.9%. [Auditor 23-004](https://www.sandiego.gov/sites/default/files/23-004_get_it_done_application_and_service_requests_management.pdf) | — | tool only (`create_service_request` lists "streetlight"); no KB FAQ |
| 6 | Sidewalk repair | 18,692, 6.3%. [Auditor 23-004](https://www.sandiego.gov/sites/default/files/23-004_get_it_done_application_and_service_requests_management.pdf) | — | gap — no KB topic or tool |
| 7 | Bulky item pickup | Not separately ranked; trash.md cites "~2 free pickups/yr, verify allowance." | LA: 674,968, 47.7% of 1.42M (2024) — but LA requires per-item online scheduling, which inflates its count vs. SD's on-call model. [Crosstown](https://xtown.la/2025/01/21/myla311-reports-in-los-angeles-rise-5-2-in-2024-graffiti-removal-bulky-item-pickup/) | `trash.md` (partly — allowance unverified) |
| 8 | Illegal dumping | Category exists in Get It Done; not numerically ranked. | LA: 114,268, 8.1% (2024). [Crosstown](https://xtown.la/2025/01/21/myla311-reports-in-los-angeles-rise-5-2-in-2024-graffiti-removal-bulky-item-pickup/) | `service_requests.md`; `create_service_request` |
| 9 | Residential noise complaints | No City "most requested" ranking found. | NYC: 738,000+, 21.7% of 3.4M (2024), 356,000+ residential-noise subset. [FOX5NY](https://www.fox5ny.com/news/noise-tops-nycs-311-complaints-list-2024) · Austin: 20,000+ "Noise/Alarm," 6.7% of 298,932 (2025). [KXAN](https://www.kxan.com/news/local/austin/austin-311-data-2025/) | gap — no KB topic or tool |
| 10 | Illegal parking | Handled as citations; not GID-ranked. | NYC: 500,000+, 14.7% (2024), up 155% since 2019. [FOX5NY](https://www.fox5ny.com/news/noise-tops-nycs-311-complaints-list-2024) | `parking.md` covers citations, not "report a car blocking my driveway" |
| 11 | Missed/garbage collection | `trash.md` covered; no numeric SD rank found. | Austin: 25,000+ "Garbage Collection," 8.4% — Austin's top category (2025). [KXAN](https://www.kxan.com/news/local/austin/austin-311-data-2025/) | `trash.md`; `create_service_request` |
| 12 | Homeless encampment reports | GID report type exists ("Encampment"); not numerically ranked. [Get It Done](https://getitdone.sandiego.gov/TSWNewReport?type=Encampment) | LA: 85,991, 6.1% (2024). [Crosstown](https://xtown.la/2025/01/21/myla311-reports-in-los-angeles-rise-5-2-in-2024-graffiti-removal-bulky-item-pickup/) · SF: ~3,000–4,000/mo since fall 2024. [SF Public Press](https://sfpublicpress.org/complaints-from-neighbors-now-driving-citys-response-to-homeless-camps) | gap — no KB topic or tool |
| 13 | Code enforcement (weeds/junk/illegal construction) | DSD Building & Land Use Enforcement handles; not numerically ranked. [sandiego.gov/development-services/building-land-use-enforcement](https://www.sandiego.gov/development-services/building-land-use-enforcement) | Austin: 23,000+ "Code Officer," 7.7% (2025). [KXAN](https://www.kxan.com/news/local/austin/austin-311-data-2025/) | gap — no KB topic or tool |
| 14 | Abandoned vehicle | `parking.md` covered; not numerically ranked. | NYC top-10 category (2024), exact count not published. [FOX5NY](https://www.fox5ny.com/news/noise-tops-nycs-311-complaints-list-2024) | `parking.md` (partly — no towing-timeline detail) |
| 15 | Rental habitability (heat/hot water/plumbing/paint) | `housing.md` covers tenant rights generally; not numerically ranked. | NYC: Heat/Hot Water, Plumbing, Paint/Plaster each independently top-10 (2024). [FOX5NY](https://www.fox5ny.com/news/noise-tops-nycs-311-complaints-list-2024) | `housing.md` (partly) |
| 16 | Blocked driveway | Not addressed in `parking.md`. | NYC top-10 (2024). [FOX5NY](https://www.fox5ny.com/news/noise-tops-nycs-311-complaints-list-2024) | gap |
| 17 | Unsanitary conditions on private property | DSD BLUE handles; not ranked. | NYC top-10 (2024). [FOX5NY](https://www.fox5ny.com/news/noise-tops-nycs-311-complaints-list-2024) | gap |
| 18 | Water quality/pressure complaints | Public Utilities hotline exists; not ranked. [sandiego.gov/public-utilities/customer-support](https://www.sandiego.gov/public-utilities/customer-support) | NYC "Water System" top-10 (2024). [FOX5NY](https://www.fox5ny.com/news/noise-tops-nycs-311-complaints-list-2024) | `utilities.md` (partly — leak covered, discoloration/quality not) |
| 19 | Trash/recycling schedule self-lookup | City's own primary self-service page; no public traffic counter. [getitdone.sandiego.gov/CollectionMapLookup](https://getitdone.sandiego.gov/CollectionMapLookup) | — | `trash.md`; `get_trash_schedule`, `get_next_pickup` |
| 20 | Parking citation payment | High-frequency Treasurer online-payment channel; no public breakdown. [sandiego.gov/treasurer/payments/citation](https://www.sandiego.gov/treasurer/payments/citation) | — | `general.md`, `parking.md` |
| 21 | Building permit status checks | Primary self-service channel; no public volume. [aca.accela.com/SANDIEGO](https://aca.accela.com/SANDIEGO) | — | `permits.md`; `get_permit_status`, `get_application_status` |
| 22 | Business Tax Certificate application/status | Primary self-service channel; no public volume. [pay.sandiego.gov/BTaxApp](https://pay.sandiego.gov/BTaxApp) | — | `business.md`; `estimate_business_tax` |
| 23 | Council district / elected official lookup | No public volume. | — | `general.md`; `get_council_district` |
| 24 | Water leak / water main break | Emergency hotline exists (619-515-3525); no public volume. [sandiego.gov/public-utilities](https://www.sandiego.gov/public-utilities/customer-support) | — | `utilities.md` |
| 25 | Special event / block party permit requests | Office of Special Events; no public volume. | — | `events.md` |

Note: no source anywhere — City, peer city, or chatbot vendor — publishes chatbot question volume
*by category*. Denver's Citibot deployment reports only aggregate volume (100,000+ questions
answered, 5,000+ service requests filed since launch). [Citibot](https://www.citibot.io/the-denver-model-a-city-managers-guide-to-transforming-resident-engagement-with-ai) ·
[Axios](https://www.axios.com/local/denver/2024/04/25/denver-launches-ai-powered-chatbot-sunny).
Ranking above is therefore built from 311/Get It Done topic volume, the best available proxy.

## 2. Sixty resident questions, as residents actually phrase them

Status: **covered** (KB or a tool plausibly answers it) · **partly** (KB/tool addresses part of
it) · **gap** (none of the 9 KB topics or 16 tools address it — correct SD answer + source given).

| # | Category | Resident question | Status | Note |
|---|---|---|---|---|
| 1 | Trash | whats my trash day | covered | `get_trash_schedule` |
| 2 | Trash | recycling didnt come again this week | covered | `trash.md` — biweekly A/B cadence |
| 3 | Trash | can pizza boxes go in recycling | covered | `trash.md` — greasy paper goes in organics |
| 4 | Trash | need a new trash can mine is cracked | covered | `trash.md` + `create_service_request` |
| 5 | Trash | how many bulk pickups do i get a year | partly | `trash.md` states "~2/yr, verify allowance" — unverified in KB itself |
| 6 | Trash | is trash pickup delayed for labor day | covered | `get_holiday_schedule`; `trash.md` |
| 7 | Trash | why do i gotta pay for trash now, never did before | covered | `trash.md` — Measure B, billing since 7/1/2025 |
| 8 | Permits | do i need a permit to redo my bathroom | covered | `permits.md` |
| 9 | Permits | wheres my permit PTS-2026-03412 at | covered | `get_permit_status` |
| 10 | Permits | how much to build a ADU | covered | `permits.md` |
| 11 | Permits | can i pull my own permit im the owner | covered | `permits.md` — owner-builder + DS-3042 |
| 12 | Permits | do i need a permit for solar | covered | `permits.md` — SolarApp+ |
| 13 | Permits | my permit says issues identified wat does that mean | covered | `permits.md` |
| 14 | Business | how much is a business license for 5 employees | covered | `estimate_business_tax` |
| 15 | Business | how do i sign up for a business tax thing | covered | `business.md` |
| 16 | Business | do i need a permit to sell stuff online | covered | `business.md` + `get_referral` (CDTFA) |
| 17 | Business | can i rent my house on airbnb | covered | `business.md`, `housing.md` — STRO |
| 18 | Business | i work from home do i need anything | covered | `business.md` — Home Occupation |
| 19 | Service req | theres a huge pothole on my street | covered | `create_service_request` |
| 20 | Service req | ppl spraypainted the wall again | covered | `service_requests.md`; `create_service_request` |
| 21 | Service req | ppl dumping mattresses behind my house | covered | `service_requests.md` |
| 22 | Service req | streetlight by my house out for weeks | covered | tool lists "streetlight" category; no KB FAQ backs a timeline |
| 23 | Service req | big tree branch fell in the road | gap | Report "Tree Maintenance" via Get It Done. [getitdone.sandiego.gov/TSWNewReport?type=Tree+Maintenance](https://getitdone.sandiego.gov/TSWNewReport?type=Tree+Maintenance) **Closed 2026-09-15** — `service_requests.md` FAQ (Tree Maintenance, tree_trimming, Parks & Recreation); golden 120. |
| 24 | Service req | sidewalks all cracked in front of my house whos responsible | gap | Adjacent owner is generally liable (Sts. & Hwys. Code §5610); City covers damage it caused. [sandiego.gov Safe Sidewalks infographic](https://www.sandiego.gov/sites/default/files/2023-11/Attachment%201%20-%20Sidewalk%20Repair%20Infographic_October%20202_0.pdf) **Closed 2026-09-15** — `service_requests.md` FAQ (§5610, adjacent owner, sidewalk_repair); golden 121. |
| 25 | Service req | my report says referred what's that mean | covered | `service_requests.md` |
| 26 | Service req | wheres my case GID-2026-045821 at | covered | `get_application_status` |
| 27 | Service req | abandoned car on my block for a month | partly | `parking.md` covers filing; no towing-timeline detail |
| 28 | Events | whats going on this weekend for free | covered | `search_events`; `events.md` |
| 29 | Events | when's the next city council meeting | covered | `search_events`; `events.md` |
| 30 | Events | how do i get a permit for a block party | covered | `events.md` |
| 31 | Events | wheres the closest farmers market to north park | covered | `search_events`; `events.md` |
| 32 | General | how do i find out my council district | covered | `get_council_district` |
| 33 | General | do i need to license my dog | covered | `general.md` — refer to SDHS/County |
| 34 | General | how do i register to vote | covered | `general.md` — refer to sdvote.com |
| 35 | General | is the library open today | covered | `general.md` |
| 36 | General | how do i get a library card does it cost anything | gap | Free for CA residents/property owners/military stationed here; $32.50/yr non-resident. [sandiego.gov/public-library/services/lending/librarycard](https://www.sandiego.gov/public-library/services/lending/librarycard) **Closed 2026-09-15** — `general.md` FAQ (free for CA residents, $32.50 non-resident); golden 122. |
| 37 | Parking | got a ticket how do i pay it | covered | `parking.md`, `general.md` |
| 38 | Parking | can i fight a parking ticket | covered | `parking.md` |
| 39 | Parking | can i park my rv in front of my house overnight | covered | `parking.md` |
| 40 | Parking | wheres street sweeping on my street | covered | `get_street_sweeping` |
| 41 | Parking | can i get a permit to park on my street | covered | `parking.md` — residential permit |
| 42 | Utilities | water bill seems really high this month why | covered | `utilities.md` |
| 43 | Utilities | water leak in the street whos responsible | covered | `utilities.md` |
| 44 | Utilities | smells like sewage outside my house | covered | `utilities.md` — sewer backup Q |
| 45 | Utilities | how do i start water service at my new place | covered | `utilities.md` |
| 46 | Utilities | water outta my tap is brown | gap | Call 619-515-3500 for discolored/cloudy/odorous water; don't drink it. [sandiego.gov/public-utilities/customer-support](https://www.sandiego.gov/public-utilities/customer-support) **Closed 2026-09-15** — `utilities.md` FAQ plus a `service_requests.md` cross-reference (619-515-3500); golden 123. |
| 47 | Housing | landlord raising rent a ton is that even legal | covered | `housing.md` |
| 48 | Housing | landlord wants me to sign cash for keys wat do i do | covered | `housing.md` |
| 49 | Housing | can i put my adu on airbnb | covered | `housing.md` |
| 50 | Housing | how do i get section 8 | covered | `housing.md` |
| 51 | Housing | about to be homeless who do i call right now | covered | `housing.md` |
| 52 | Homeless | theres a homeless camp under the bridge by my house | gap | Report via Get It Done "Encampment" (Caltrans instead if on a state highway/underpass). [getitdone.sandiego.gov/TSWNewReport?type=Encampment](https://getitdone.sandiego.gov/TSWNewReport?type=Encampment) **Closed 2026-09-15** — `service_requests.md` FAQ (Encampment, HSSD, Caltrans on state land); golden 124. The tool still files it as `other`; see the M23 note below. |
| 53 | Homeless | where can someone get a shelter bed tonight its cold | gap | Call 211 for assessment/placement; City's Inclement Weather Shelter Program adds capacity Nov–Mar. [sandiego.gov/.../inclement-weather-shelter-program](https://www.sandiego.gov/homelessness-strategies-and-solutions/services/inclement-weather-shelter-program) |
| 54 | Noise | neighbors blasting music at 1am wat do i do | gap | Call non-emergency 619-531-2000 while it's happening; quiet hours 10pm–7am (Muni Code 59.5.04). [sandiego.gov/police/community/noise-complaints](https://www.sandiego.gov/police/community/noise-complaints) **Closed 2026-09-15** — `general.md` and `service_requests.md` FAQs (619-531-2000, quiet hours, §59.5.04); golden 125. |
| 55 | Noise | construction next door starts at 6am is that even allowed | gap | Same noise-ordinance channel; repeat violations can draw a $1,000 administrative citation. [sandiego.gov/police/community/noise-complaints](https://www.sandiego.gov/police/community/noise-complaints) **Closed 2026-09-15** — same noise FAQs; not separately benchmarked. |
| 56 | Code enforcement | neighbors yard is full of junk and weeds hes never home | gap | Report to DSD Building & Land Use Enforcement via Get It Done. [sandiego.gov/development-services/building-land-use-enforcement](https://www.sandiego.gov/development-services/building-land-use-enforcement) **Closed 2026-09-15** — `service_requests.md` FAQ (DSD Building & Land Use Enforcement, stro_code_enforcement); golden 126. |
| 57 | Code enforcement | pretty sure neighbor built a room addition with no permit | gap | Same BLUE channel — illegal construction. [sandiego.gov/development-services/building-land-use-enforcement](https://www.sandiego.gov/development-services/building-land-use-enforcement) **Closed 2026-09-15** — same BLUE FAQ, which names an unpermitted room addition; not separately benchmarked. |
| 58 | Code enforcement | no curb ramp on my corner, cant get my wheelchair up | gap | File at getitdone.sandiego.gov/ADACA or adacompliance@sandiego.gov, 619-236-5979. [sandiego.gov/adacompliance/complaint](https://www.sandiego.gov/adacompliance/complaint) **Closed 2026-09-15** — `service_requests.md` FAQ (getitdone.sandiego.gov/ADACA, 619-236-5979, ada_accessibility); golden 127. |
| 59 | Animal control | stray dog running loose on my street | gap | San Diego Humane Society (City's animal-control partner), 619-299-7012 ext. 1, 24/7. [sandiego.gov/park-and-recreation/activities/animalservices](https://www.sandiego.gov/park-and-recreation/activities/animalservices) **Closed 2026-09-15** — `general.md` and `service_requests.md` FAQs plus a `referrals.json` row (Humane Society, 619-299-7012 ext. 1); golden 128. |
| 60 | Jobs | how do i apply for a job with the city | gap | Apply online only at sandiego.gov/governmentjobs; questions to 619-236-6400. [sandiego.gov/governmentjobs](https://www.sandiego.gov/governmentjobs) **Closed 2026-09-15** — `general.md` FAQ (sandiego.gov/governmentjobs, 619-236-6400); golden 129. |

**Tally: 45 covered, 2 partly, 13 gap.**

### M23 benchmark loop, 2026-09-15

The ten highest-volume `gap` rows above became golden category `production` (ids 120-129, all
`dev`), phrased exactly as this file phrases them. They were run against the live stack once
before any content was written and once after, with no prompt or profile changes in between.
Twelve of the thirteen gaps are now closed by knowledge-base content; row 53 (a shelter bed
tonight, 211 and the Inclement Weather Shelter Program) is still open because it was outside the
ten and no content was written for it.

Two findings the content could not close, because closing them would mean editing a prompt:

- The router sends "water outta my tap is brown", "neighbors blasting music at 1am" and "stray dog
  running loose on my street" to `service_request` rather than `general`. Retrieval for that intent
  is filtered to the `service_requests` topic, which is why each of those three needed a
  cross-reference FAQ in `service_requests.md` as well as the answer in its own topic file.
- `create_service_request` files the encampment report under category `other`, not
  `homeless_encampment`, in both runs. The service_request profile enumerates its categories in the
  prompt and that list does not include `homeless_encampment`, `stro_code_enforcement` or
  `ada_accessibility`; the last two are now chosen correctly because the new FAQs name them, the
  first is not. The reply names the Homelessness Strategies & Solutions Department even though the
  tool returned City Clerk / General Services, so the department in that reply is unsourced.


## 3. Question types that are dangerous for a chatbot

| Type | Example phrasing | What the assistant should say instead |
|---|---|---|
| Emergency (fire, crime in progress, medical) | "theres a fire on my street", "someone's breaking into my neighbor's house right now" | Stop and say: call 911 immediately. Never attempt to dispatch, triage, or advise on the situation. |
| Legal advice | "can my landlord legally evict me for this", "am i gonna win my code enforcement hearing" | State the general City rule if published (e.g., rent-increase notice periods), then refer to San Diego Volunteer Lawyer Program / Legal Aid Society of San Diego — never predict an outcome or advise a legal strategy. |
| Immigration status | "will reporting this get me in trouble with ICE", "does code enforcement check immigration status" | State that City services are provided regardless of immigration status per City policy, and refer to an immigration attorney or nonprofit legal service for anything beyond that — never promise confidentiality or legal protection the assistant cannot verify. |
| Court dates / proceedings | "do i have to show up in court for my citation", "what happens at my hearing" | Refer to the citation notice / Superior Court of California, San Diego self-help center (sdcourt.ca.gov) for dates and procedure — never state a hearing outcome, deadline, or legal consequence from memory. |
| Payments / financial account handling | pasting a credit card number into chat, "can you just pay my water bill for me", "refund my citation" | Never accept, store, or process payment details in the conversation. Direct to the official portal (MyWaterSD, pay.sandiego.gov, sandiego.gov/treasurer/payments/citation) and warn against sharing card numbers in chat. |

## 4. Twenty Spanish questions mirroring the highest-volume English ones

| # | Spanish (as a resident would type it) | English equivalent | Category |
|---|---|---|---|
| 1 | cual es mi dia de basura | What day is my trash picked up? | Trash |
| 2 | por que no recogieron mi reciclaje esta semana | Why wasn't my recycling picked up this week? | Trash |
| 3 | hay un bache enorme en mi calle | There's a huge pothole on my street. | Service request |
| 4 | pintaron graffiti en la pared otra vez | Someone tagged the wall again. | Service request |
| 5 | cuanto cuesta la licencia de negocio para 5 empleados | How much is a business license for 5 employees? | Business |
| 6 | como aplico para el certificado de impuesto de negocio | How do I apply for a Business Tax Certificate? | Business |
| 7 | necesito un permiso para remodelar mi baño | Do I need a permit to remodel my bathroom? | Permits |
| 8 | cual es el estado de mi permiso PTS-2026-03412 | What's the status of permit PTS-2026-03412? | Permits |
| 9 | mi factura del agua salio muy alta este mes | My water bill is very high this month. | Utilities |
| 10 | hay una fuga de agua en la calle | There's a water leak in the street. | Utilities |
| 11 | como pago una multa de estacionamiento | How do I pay a parking ticket? | Parking |
| 12 | los vecinos ponen musica muy fuerte a la 1am | The neighbors play loud music at 1am. | Noise |
| 13 | hay un campamento de personas sin hogar bajo el puente | There's a homeless encampment under the bridge. | Homeless |
| 14 | cuando es la proxima junta del concejo municipal | When is the next City Council meeting? | Events |
| 15 | donde esta el mercado de agricultores mas cercano | Where's the nearest farmers market? | Events |
| 16 | mi perro se perdio y anda suelto en la calle | A stray dog is loose on my street. | Animal control |
| 17 | el apagon de luz de la calle lleva semanas asi | The streetlight has been out for weeks. | Service request |
| 18 | mi arrendador quiere subir la renta mucho, es legal | My landlord wants to raise the rent a lot, is that legal? | Housing |
| 19 | puedo rentar mi casa en airbnb | Can I rent my house on Airbnb? | Housing |
| 20 | como consigo una tarjeta de la biblioteca | How do I get a library card? | General |
