# Synthesis — Design Input for City of San Diego Virtual Assistant
Condensed from 01-permits.md, 02-business-licensing.md, 03-trash-and-service-requests.md, 04-events-and-general-inquiries.md. Read this instead of those four files.
## 1. Entity Schemas
| PermitApplication field | Type | Required | Example |
|---|---|---|---|
| permit_id | string | Y | PTS-2026-03412 |
| permit_type | enum | Y | No-Plan Building Permit |
| project_address | string | Y | 1200 3rd Ave, San Diego CA |
| owner_name | string | Y | Jane Smith |
| applicant_role | enum(Owner/Agent/Other) | Y | Owner |
| project_valuation_usd | number | N (Y if Building w/ Plans) | 50000 |
| historic_flag (structure ≥45yr) | bool | Y | true |
| status | enum | Y | In Review |
Status enum (order, owning dept): Submitted(DSD intake) → In Review(DSD plan reviewers) → Issues Identified(DSD reviewers; loops to In Review) → Approved/Ready to Issue(DSD reviewers) → Issued(DSD issuance staff) → Inspections(DSD inspector) → Finaled/Closed(DSD inspector). Side-states: Void, Withdrawn, Expired, On Hold.
| BusinessTaxApplication field | Type | Required | Example |
|---|---|---|---|
| btc_number | string | Y (system) | BTC-2026-88213 |
| dba_name | string | Y | Jane's Coffee Cart |
| ownership_type | enum | Y | Sole Proprietorship |
| business_address | string | Y (no PO Box) | 455 5th Ave, San Diego CA |
| business_start_date | date | Y | 2026-09-01 |
| employee_count | int | Y | 5 |
| police_regulated_flags | array | Y (empty ok) | [Tobacco Retailer] |
| status | enum | Y | Active/Issued |
Status enum: New Application(Applicant) → Pending/Processing(Treasurer) → Active/Issued(Treasurer) → Renewal Due(Treasurer, courtesy) → Delinquent/Past Due(Treasurer Compliance) → Operating Without Payment(Treasurer Compliance) → Revoked/Denied(Treasurer) → Closed/Inactive(Treasurer).
| ServiceRequest field | Type | Required | Example |
|---|---|---|---|
| case_id | string | Y (system) | GID-2026-045821 |
| category | enum (~65 types/23 groups) | Y | Pothole |
| address_or_pin | string | Y | 3500 5th Ave |
| council_district | int 1-9 | Y (derived) | 3 |
| description | text | N | Large pothole blocking bike lane |
| photo_url | string | N (Y for graffiti/dumping) | https://... |
| department | enum | Y (derived) | Transportation Dept |
| status | enum | Y | In Process |
Status enum: New(system) → In Process(assigned dept) → Referred(outside agency, terminal) → Closed(assigned dept). Side-state: Duplicate (linked via parent_case_id).
| StroLicense field (M24, detail in [09-resident-forms.md](09-resident-forms.md) §2 and [06-parking-utilities-housing.md](06-parking-utilities-housing.md)) | Type | Required | Example |
|---|---|---|---|
| license_number | string | Y (system) | STR-2026-000401 |
| host_name | string | Y | Elena Moreau |
| property_address | string | Y | 3355 University Ave, San Diego CA |
| unit_type | enum(single_family/condo/apartment/duplex/accessory_dwelling_unit/other) | Y | single_family |
| tier | enum(tier1/tier2/tier3/tier4) | Y | tier3 |
| host_resides_onsite | bool | Y if tier2 (primary-residence attestation) | false |
| nights_offered_per_year | int | Y if tier1 (≤20) or tier3/4 (≥90 to keep the licence) | 180 |
| owner_or_agent | enum(owner/authorized_agent) | Y | owner |
| tot_certificate_number | string | Y (no published format) | TOT-2026-114502 |
| rental_unit_btc_number | string | Y | RUBT-2026-33871 |
| local_contact_name / local_contact_phone | string | Y (24-hour contact) | Marcus Webb / 619-555-0198 |
| attestation_accepted | bool | Y (must be true) | true |
| status | enum | Y | In Review |
Owning department: Office of the City Treasurer; no published review SLA (30 days is a stated demo assumption). Fee = application fee + licence fee by tier: tier1 $33+$193, tier2 $33+$284, tier3/4 $41+$1,129 (estimates, sandiego.gov/stro). Status enum: the same spine as the three above.
| Event field | Type | Required | Example |
|---|---|---|---|
| event_id | string | Y | EVT-011 |
| title | string | Y | SD LGBTQ+ Pride Parade & Festival |
| date_start / date_end | date | Y / N | 2026-09-19 / 2026-09-20 |
| location | string | Y | Balboa Park & University Ave |
| department | string | Y | Office of Special Events |
| cost | string | Y | Free, some vendor fees |
| category | enum | Y | Festival |
| council_district | int | N | 3 |
Event has no application status (not applicant-submitted); its permit counterpart is Special Event Permit, workflow in §2.
## 2. Workflow Steps (submit → extract → validate → route → review → decision → issue/notify)
**PermitApplication** (DSD, 7 steps): 1 Submit via Accela ACA with DS-3032 + supplemental forms → 2 Extract fields (approval type, address, APN, valuation, sq ft, contractor license) → 3 Completeness check: DS-3042 present if owner-builder checked, DS-6005 if No-Plan, signature+date present, contractor license present if declared → 4 Route to disciplines by scope (structural/fire/electrical/mechanical/plumbing/planning; historic review if structure ≥45yr) → 5 Plan-check cycle(s); Issues Identified loops back until all disciplines clear → 6 Approved → fee invoice (valuation-based) → payment → Issued → 7 Inspections scheduled/passed → Finaled.
**BusinessTaxApplication** (Treasurer, 6 steps): 1 Submit Parts 1-5 via BTaxApp portal/mail/in-person → 2 Extract fields (ownership type, address, employee_count, activity code, police/fire flags) → 3 Validate: address not a PO Box, employee_count present, Part 4 checked → route SDPD, Part 5 checked → route Fire-Rescue → 4 Compute fee from employee tier → 5 Payment clears → BTC issued (Active/Issued) → 6 Annual renewal recalculated; late (>15 days after business_start_date) triggers penalty.
**ServiceRequest** (Get It Done, 5 steps): 1 Submit via web/app/phone (category, address, description, photo) → 2 Classify free text into 1 of ~65 service types/23 rolled-up categories → 3 Validate: address geocodes inside city limits & resolves council_district; photo required for graffiti/illegal-dumping → 4 Route to department via category map (§4) → 5 Dispatch → In Process → Closed (or Referred if outside agency).
**Special Event Permit** (Office of Special Events, 7 steps): 1 Pre-application planning + park reservation confirmed if on City property → 2 Submit citywide application (specialeventapplication.sandiego.gov), ≤2yr ahead, ≥60 days before event → 3 Extract fields (dates, location, attendance, street-closure Y/N, alcohol Y/N) → 4 Completeness check: site map, insurance certificate, park reservation # if applicable → 5 Fee: $341 base (+$80/business-day if filed <60 days out) → 6 Parallel review: Police/Fire/Parks/Transportation/ESD issue conditions → 7 Approved → Permit Issued → day-of compliance check → Completed.
**Machine-checkable validation rules:**
- Valuation drives permit fee tier and triggers full plan check (IB-501/IB-101); structure age ≥45yr flags historic review.
- Owner-builder checked → require DS-3042 attached; approval type = No-Plan → require DS-6005 attached.
- ADU floor area <750 sqft → exempt from development impact fees; solar ≤38.4kW AC on SFR/duplex → eligible for SolarApp+ instant path; commercial TI <20,000 sqft with no plumbing/stair/occupancy change → eligible for IB-150 fast track.
- employee_count drives BTC fee tier (≤12 vs ≥13); business_address must not be a PO Box.
- Special Event application date must be ≥60 days from submission or late fee applies; ServiceRequest address must geocode inside San Diego city limits.
## 3. Fee Rules (codeable)
- **Business Tax Certificate fee:** ≤12 employees → $34 base + $4 SB-1186 fee = $38 total; ≥13 employees → $125 + $5/employee + $4 SB-1186; both tiers add $1.47/employee Minimum Wage Enforcement Fee (eff. 7/1/2025). Late (>15 days after business_start_date): late fee = max($25, 10% of tax owed) + 1%/month ongoing penalty; operating-without-payment surcharge $68 (≤12 emp) / $250 (≥13 emp). [02-business-licensing.md §5 Q2,Q5; sandiego.gov/treasurer/taxesfees/btax/btaxfees]
- **Permit fee estimate by type:** Simple Permit ~$100–300/trade; No-Plan combo (IB-203) ≈$411.02, single-trade $115–165; Building Permit with Plans = valuation-based inspection fee (~$4 per $100k construction value, IB-101) + plan-check fee (~65–85% of permit fee, IB-501); ADU total permit+impact fees $6,000–$20,000 (units <750 sqft exempt from impact fees); Solar ~$150–500. [01-permits.md §2,§5 Q5; IB-501, IB-101]
- **Special Event Permit fee:** $341 standard application fee (≥60 days before event); +$80/business-day late fee if filed <60 days out; sub-permit fees (street closure, park use, amplified sound, alcohol) and Police/Fire staffing cost-recovery billed separately. [04-events-and-general-inquiries.md §3.1 step 4]
## 4. Structured Lookup Data to Seed (SQL tables, answered by tool calls — not RAG)
**Trash zones (12, synthetic — modeled on real cadence, not official ESD boundaries):**
| Zone | Neighborhood cluster | Trash day | Organics day | Recycling day | Recycling cadence |
|---|---|---|---|---|---|
| A | Clairemont / Bay Park | Monday | Monday | Tuesday | Alternating Week A |
| B | Pacific Beach / Mission Beach | Monday | Monday | Tuesday | Alternating Week B |
| C | La Jolla / University City | Tuesday | Tuesday | Wednesday | Alternating Week A |
| D | Kearny Mesa / Serra Mesa | Tuesday | Tuesday | Wednesday | Alternating Week B |
| E | North Park / University Heights | Wednesday | Wednesday | Thursday | Alternating Week A |
| F | Normal Heights / Kensington | Wednesday | Wednesday | Thursday | Alternating Week B |
| G | Mission Valley / Linda Vista | Thursday | Thursday | Friday | Alternating Week A |
| H | College Area / Rolando | Thursday | Thursday | Friday | Alternating Week B |
| I | Point Loma / Ocean Beach | Friday | Friday | Monday | Alternating Week A |
| J | Southeastern San Diego | Friday | Friday | Monday | Alternating Week B |
| K | San Ysidro / Otay Mesa | Monday | Monday | Wednesday | Alternating Week A |
| L | Rancho Bernardo / Rancho Peñasquitos | Tuesday | Tuesday | Thursday | Alternating Week B |
Holiday shift rule: no collection on New Year's Day, Memorial Day, Labor Day, Thanksgiving, Christmas; if a holiday falls on a weekday, that day's route and every remaining route that week shifts one day later (a Friday holiday can push a route to Saturday). [03-trash-and-service-requests.md §2]
**Events (25, seed data verbatim from source, compacted to 4 columns):**
| # | Title | Date | Dept | Cost |
|---|---|---|---|---|
| 1 | City Council Meeting | 2026-09-08 | City Clerk/Council | Free |
| 2 | Land Use & Housing Committee Meeting | 2026-09-10 | City Council | Free |
| 3 | Public Hearing: STRO Ordinance Amendment | 2026-09-15 | City Clerk | Free |
| 4 | Hillcrest Farmers Market (weekly) | 2026-09-06 | Parks & Rec | Free entry |
| 5 | Little Italy Mercato (weekly) | 2026-09-05 | Parks & Rec | Free entry |
| 6 | Ocean Beach Wednesday Market (weekly) | 2026-09-09 | Parks & Rec | Free entry |
| 7 | Toddler Story Time (weekly) | 2026-09-12 | Library | Free |
| 8 | Central Library Author Talk: Local History | 2026-09-18 | Library | Free, RSVP |
| 9 | Balboa Park Free Fitness in the Park | 2026-09-13 | Parks & Rec | Free |
| 10 | Adult Coding Basics Workshop | 2026-09-20 | Library | Free, RSVP |
| 11 | SD LGBTQ+ Pride Parade & Festival | 2026-09-19–20 | Office of Special Events | Free, some vendor fees |
| 12 | Environment Committee Meeting | 2026-09-23 | City Council | Free |
| 13 | Adoptable Pets Day | 2026-09-26 | Parks & Rec / County Animal Svcs | Free |
| 14 | Mission Bay Park Cleanup Day | 2026-09-27 | Parks & Rec | Free, volunteer |
| 15 | City Council Meeting | 2026-10-06 | City Clerk/Council | Free |
| 16 | Public Hearing: Midway Rising Dev Project | 2026-10-08 | City Clerk/Planning | Free |
| 17 | Little Italy Mercato (weekly) | 2026-10-10 | Parks & Rec | Free entry |
| 18 | Halloween Family Storytime & Craft | 2026-10-24 | Library | Free |
| 19 | Fleet Week SD Kickoff Festival | 2026-10-03–11 | Office of Special Events | Free, some ticketed |
| 20 | Balboa Park Oktoberfest Community Event | 2026-10-17 | Office of Special Events | $10, kids free |
| 21 | Rules Committee Meeting | 2026-10-21 | City Council | Free |
| 22 | Dia de los Muertos Community Celebration | 2026-11-01 | Office of Special Events | Free |
| 23 | City Council Meeting | 2026-11-03 | City Clerk/Council | Free |
| 24 | Veterans Day Ceremony | 2026-11-11 | Parks & Rec/Council | Free |
| 25 | Holiday Programming Kickoff: Winter Reading Challenge | 2026-11-21 | Library | Free |
**Permit types (~10) with fee estimate + typical turnaround:**
| Type | Fee estimate | Typical turnaround |
|---|---|---|
| Simple Permit | ~$100–300/trade | Instant (licensed contractor) / ~2 biz days (owner-builder) |
| No-Plan Building Permit | Combo ≈$411; single-trade $115–165 | ~10 biz days (historic/pre-const check) then issuance |
| Building Permit with Plans | Valuation-based + plan-check ~65–85% of permit fee | 4–8+ wks (TI); 3–5mo+ (ADU/complex) |
| ADU | $6,000–$20,000 total (impact fees) | 3–5 months (standard plans), 6–12mo (custom) |
| Solar PV (residential) | ~$150–500 | 1–5 biz days (SolarApp+) / 10–21 days (manual) |
| Tenant Improvement (commercial) | Valuation-based | 4–8 wks std; ≤7 days/same-day (IB-150 fast track) |
| Sign Permit | Varies (IB-501/IB-111) | ~2 biz days issuance queue |
| Grading Permit | Valuation/quantity-based | ~2 biz days issuance queue |
| Demolition/Removal | Modest flat/valuation fee | ~3 biz days issuance queue |
| Special Event Permit | $341 base (+$80/day if <60 days out) | Reviewed per lead time; issued after multi-dept sign-off |
**Service-request category → department routing map:**
| Category | Department |
|---|---|
| Pothole / sidewalk repair / street resurfacing | Transportation Dept (Streets Division) |
| Graffiti removal | Transportation Dept / ESD |
| Streetlight / traffic signal out | Transportation Dept (Traffic Engineering) |
| Missed collection / container issue / bulky item / HHW / illegal dumping (residential) | Environmental Services Dept (ESD) |
| Homeless encampment / outreach | Homelessness Strategies & Solutions Dept |
| Parking enforcement / abandoned vehicle | Police Dept (Parking Enforcement) |
| Tree trimming / weed abatement / park facility issue | Parks & Recreation Dept |
| Stormwater / drainage | Transportation Dept (Stormwater Division) |
| ADA accessibility complaint | ADA Compliance / Transportation |
| STRO violation / code enforcement (property/building) | Development Services Dept (Code Enforcement) |
| Dead animal removal | ESD / Animal Services (street vs private) |
| "Other" / uncategorized | City Clerk / General Services intake (manual triage) |
**Council districts (9) with sample neighborhoods** — *not present in source files; approximate real-world SD districts, synthesized for demo seed data. Verify against sandiego.gov council district map before production use.*
| District | Sample neighborhoods |
|---|---|
| 1 | La Jolla, University City |
| 2 | Pacific Beach, Point Loma |
| 3 | Hillcrest, North Park |
| 4 | Encanto, Skyline |
| 5 | Rancho Bernardo, Scripps Ranch |
| 6 | Mira Mesa, Clairemont |
| 7 | Tierrasanta, Mission Valley |
| 8 | San Ysidro, Otay Mesa |
| 9 | City Heights, College Area |
## 5. RAG Knowledge Base Inventory (60 items)
1. [permits] Do I need a permit to remodel my kitchen/bathroom? — No-Plan Permit if no structural change; Building Permit with Plans if moving walls/adding sqft/major plumbing-electrical work. (IB-203)
2. [permits] How do I check my permit status? — Log into Accela ACA (aca.accela.com/SANDIEGO); pre-2018 records are in OpenDSD (opendsd.sandiego.gov).
3. [permits] What does "Issues Identified" mean? — A plan-review discipline found corrections needed; all open items across disciplines must be resolved before resubmittal (IB-610).
4. [permits] How long does a building permit take? — Simple/No-Plan: days; solar via SolarApp+: 1–5 days; standard plans: 4–8+ wks (TI) to 3–5 months (ADU).
5. [permits] What is the fee for a building permit? — Valuation-based (~$4/$100k, IB-101) + plan-check fee (~65% of permit fee, IB-501); varies by type.
6. [permits] Can a homeowner pull their own permit? — Yes, as Owner-Builder; sign the DS-3032 declaration plus a separate DS-3042 Verification form.
7. [permits] How long is a permit valid? — 3 yrs (SFR/duplex) or 4 yrs (other) from issuance; work must start within 1 yr; extend via Form DS-117.
8. [permits] Do I need a permit for solar panels? — Yes; qualifying systems (≤38.4kW AC, SFR/duplex) use SolarApp+ for 1–5 day instant issuance.
9. [permits] Simple Permit vs No-Plan Permit? — Simple = single-trade MEP, no plan review, often instant; No-Plan = like-for-like repair on a finaled structure, ~10-day review.
10. [permits] How much does an ADU cost and how long does it take? — $6,000–$20,000 total fees (<750sqft exempt impact fees); 3–5 months standard plans, 6–12 months custom.
11. [permits] Do I need a permit for a business sign? — Yes, a Sign Permit; needs vicinity map, dimensions, setbacks; electrical/high-rise signs also need inspection.
12. [permits] What happens after my permit is Issued? — Schedule required inspections (footing, framing, rough MEP) through the portal; all must pass, including final, to reach Finaled.
13. [business] Do I need a business license? — City issues a Business Tax Certificate (not a "license"); required for anyone doing business in the City >6 days/year.
14. [business] How much does a Business Tax Certificate cost? — ≤12 employees: $38 total ($34+$4 SB-1186); ≥13: $125+$5/employee+SB-1186, plus $1.47/employee min-wage fee.
15. [business] How do I apply? — Online at pay.sandiego.gov/BTaxApp, by mail (PO Box 122289), or in person at Civic Center Plaza.
16. [business] How long does it take to get my certificate? — Online: immediate on payment; mail: up to ~2 weeks.
17. [business] What if I apply late? — Must file within 15 days of business start; late fee = greater of $25 or 10% owed, plus 1%/month penalty.
18. [business] Do I need to renew every year? — Yes, on a recurring cycle; City sends courtesy (not legally required) reminders.
19. [business] I work from home — do I need a certificate/special permit? — Yes, a Business Tax Certificate (check Home-Based Business); no extra land-use permit needed if Home Occupation rules are met (no on-site employees, no client visits, ≤25% floor area).
20. [business] Do I need to check zoning before signing a lease? — Yes, via DSD's ZAPP tool; the Business Tax Certificate relies on self-certified zoning compliance, not a City pre-check.
21. [business] Do I need a fictitious business name (DBA) filing? — Yes if your business name isn't just your legal surname + description; file with County ARCC, publish in a newspaper, valid 5 years.
22. [business] Do I need a seller's permit? — Yes if selling/leasing tangible goods subject to CA sales tax; free from CDTFA, often instant online.
23. [business] What do I need for an Airbnb/short-term rental? — STRO license (City Treasurer), active TOT certificate, Rental Unit Business Tax; ADUs cannot be used for STR.
24. [business] Where can I get free help starting a business? — City Economic Dept (619-236-6700), SBDC, SCORE San Diego, and SBA San Diego District Office.
25. [trash] What day is my trash picked up? — Look up your address at getitdone.sandiego.gov/CollectionMapLookup; trash/organics weekly, recycling biweekly.
26. [trash] Why wasn't my recycling picked up this week? — Recycling runs biweekly (alternating Week A/B), not weekly — check your assignment before reporting a miss.
27. [trash] What time do bins need to be out? — At the curb/alley by 6:00 a.m. on collection day, removed by 6:00 p.m. same day.
28. [trash] My trash wasn't picked up — what do I do? — Check Trash Service Updates for known delays first; if not listed, file a Missed Collection report or call 858-694-7000.
29. [trash] How does the holiday schedule work? — No collection on 5 major holidays; if one falls on a weekday, that day's route and all remaining routes that week shift one day later.
30. [trash] What can go in recycling? — Clean, dry, loose paper/cardboard, rigid plastics, metal cans, glass — no bags or food-soiled items.
31. [trash] Can food scraps go in the green bin? — Yes, food scraps and yard waste; avoid plastic bags (even most "compostable" ones).
32. [trash] How do I get a bulky item picked up? — Request via Get It Done or 858-694-7000; typically ~2 free pickups/year with an item cap (verify current allowance).
33. [trash] My trash can is broken/missing — how do I get a new one? — Submit a Repair/Replace or Missing Container request via Get It Done or call 858-694-7000.
34. [trash] How do I get a bigger or extra trash can? — Property owners request size changes/extra containers at wasteportal.sandiego.gov or 858-694-7000.
35. [trash] Why am I being charged a trash fee now? — Measure B (2022) let the City charge for residential collection for the first time in a century; billing began 7/1/2025 (~$42.76/month, 3 carts).
36. [trash] Does the trash fee apply to apartments/condos? — Generally single-family homes and small multi-family (≤4 units); larger properties use private haulers.
37. [service_requests] How do I report a pothole? — Submit a Pothole report via Get It Done (web or app) with location and photo if possible.
38. [service_requests] How do I report graffiti? — Submit a Graffiti report via Get It Done with address and photo; most public graffiti targeted for removal within ~1 week.
39. [service_requests] How do I report illegal dumping? — Submit an Illegal Dumping report via Get It Done with location and photo; don't handle hazardous materials yourself.
40. [service_requests] How do I check the status of a report? — Use your case ID at getitdone.sandiego.gov or the app; statuses are New, In Process, Referred, or Closed.
41. [service_requests] What does "Referred" status mean? — Sent to an outside agency (e.g. Caltrans, a utility) or a non-integrated City dept; no further status updates typically follow.
42. [service_requests] How long will my request take to resolve? — Varies widely — missed collection is next business day; potholes/streetlights can take weeks (no single published SLA sheet).
43. [service_requests] Can I report an issue anonymously? — Most categories don't require contact info, but an email lets you get status updates.
44. [service_requests] Get It Done vs 911/police non-emergency? — Get It Done is for non-emergency service issues; true emergencies always go to 911, non-urgent police matters go to the police non-emergency line.
45. [events] What's happening this weekend? — Check the Parks & Rec calendar and Library events page; listings include family programs, farmers markets, and permitted festivals.
46. [events] When is the next City Council meeting? — Typically Tuesdays 10:00 AM in Council Chambers, 202 C St — confirm exact date on the Legislative Calendar.
47. [events] How do I watch a council meeting online? — Livestream and archived video on the City's Granicus webcast page.
48. [events] Where's the nearest farmers market? — 30+ certified markets citywide; e.g. Sunday Hillcrest, Saturday Little Italy/Pacific Beach, Wednesday Ocean Beach/Little Italy.
49. [events] Do I need a permit to host an event in a park? — Yes, a Special Event Permit, plus a separate Park Reservation from Parks & Recreation if using a City park.
50. [events] How far ahead must I apply for an event permit? — Up to 2 years ahead, minimum 60 days before the event; large events should plan 90–120 days for multi-dept review.
51. [events] How much does a special event permit cost? — $341 base fee (≥60 days out); +$80/business day if filed late, plus separate street-closure/park-use/safety-staffing fees.
52. [events] Can I get a permit for a block party? — Yes, via a smaller "Neighborhood Block Party" PDF application through the Office of Special Events.
53. [general] Is the library open today? — Hours vary by branch; check the branch page or call 619-236-5800; most close on City holidays.
54. [general] How do I pay my water bill? — Pay online via MyWaterSD, by phone, mail, or in person; bank-account payments have no fee (card ~1.59%).
55. [general] I have a water leak — who do I call? — Water Emergency Hotline 619-515-3525; City repairs leaks on its side of the meter.
56. [general] How do I pay a parking ticket? — Pay online with your citation number at sandiego.gov/treasurer/payments/citation within 21 days.
57. [general] How do I find my council district? — Enter your address in the interactive Council District map.
58. [general] When is street sweeping on my block? — Enter your address in the online street sweeping map; typically monthly, 7 AM–2 PM.
59. [general] How do I license my dog? — Handled by San Diego Humane Society or County Animal Services, not the City directly.
60. [general] How do I register to vote? — Register at sdvote.com via the County Registrar of Voters; not a City function.
## 6. Refer-Out Table (City cannot handle directly)
| # | Inquiry type | Agency | URL |
|---|---|---|---|
| 1 | Dog licensing | San Diego Humane Society / County Animal Services | sandiegocounty.gov/das/license-laws/license.html |
| 2 | Voter registration | County Registrar of Voters | sdvote.com |
| 3 | Property tax payment | County Treasurer-Tax Collector | sdttc.com |
| 4 | Vehicle registration / driver's license | CA DMV | dmv.ca.gov |
| 5 | Small claims / traffic court | Superior Court of CA, San Diego | sdcourt.ca.gov |
| 6 | Passport application | US Dept of State (some libraries accept) | travel.state.gov |
| 7 | Marriage license | County Assessor/Recorder/County Clerk | sdarcc.gov |
| 8 | Gas/electric utility billing | SDG&E (private utility) | sdge.com |
| 9 | Food facility health permit | County DEHQ Food & Housing Division | sandiegocounty.gov/content/sdc/deh/fhd/food/food.html |
| 10 | Fictitious Business Name (DBA) filing | County Assessor/Recorder/County Clerk | sdarcc.gov/.../fictitious-business-name.html |
| 11 | Seller's Permit (sales/use tax) | CDTFA (State) | cdtfa.ca.gov/services/registration.htm |
| 12 | Business entity registration (LLC/Corp/LP) | CA Secretary of State | sos.ca.gov/business-programs |
| 13 | Employer ID Number (EIN) | IRS (Federal) | irs.gov/businesses/small-businesses-self-employed |
| 14 | State payroll tax employer registration | CA EDD | edd.ca.gov |
| 15 | Contractor state license | CSLB (State) | cslb.ca.gov |
## 7. Golden Eval Set (30 questions)
| # | Question | Intent | Answer via | Expected answer |
|---|---|---|---|---|
| 1 | What day is my trash picked up? | trash | Tool: trash_schedule_lookup(address) | Returns the zone's trash/organics day and recycling week (A/B). |
| 2 | Why wasn't my recycling picked up this week? | trash | RAG | Recycling is biweekly — not a missed pickup unless it's your assigned week. |
| 3 | My trash wasn't collected today, what do I do? | service_request | Tool: create_service_request(category=Missed Trash) | Files a Missed Collection case, routed to ESD dispatch. |
| 4 | How much does a business tax certificate cost for 5 employees? | business | Tool: fee_calculator(employee_count=5) | $38 total ($34 base + $4 SB-1186, ≤12 employees). |
| 5 | How much for 20 employees? | business | Tool: fee_calculator(employee_count=20) | $125 + $5×20 = $225, plus SB-1186 and min-wage fees. |
| 6 | How do I apply for a business tax certificate? | business | RAG | Apply online at pay.sandiego.gov/BTaxApp, by mail, or in person. |
| 7 | Do I need a permit to remodel my bathroom? | permits | RAG | No-Plan Permit unless structural changes, then Building Permit with Plans. |
| 8 | What's the status of permit #PTS-2026-03412? | permits | Tool: permit_status_lookup(permit_id) | Returns current status (e.g., In Review) from the permit record. |
| 9 | How much will my $50,000 renovation permit cost? | permits | Tool: fee_calculator(permit, valuation=50000) | Valuation-based estimate: ~$4/$100k inspection fee + ~65-85% plan-check fee. |
| 10 | How long does a solar permit take? | permits | RAG | 1–5 business days via SolarApp+ for qualifying systems (≤38.4kW AC, SFR/duplex). |
| 11 | Is there a farmers market near North Park this week? | events | Tool: event_search(location=North Park) | Queries events table for markets tagged near North Park. |
| 12 | When is the next city council meeting? | events | Tool: event_search(category=Council Meeting) | Queries events table; typically Tuesdays 10:00 AM, Council Chambers. |
| 13 | How do I get a permit for a block party? | events | RAG | Special Event Permit (or Block Party PDF) via specialeventapplication.sandiego.gov. |
| 14 | How much does a special event permit cost? | events | RAG | $341 base fee (≥60 days out), +$80/business day if filed late. |
| 15 | I want to report a pothole on my street. | service_request | Tool: create_service_request(category=Pothole) | Creates a Pothole case routed to Transportation Dept. |
| 16 | How do I report graffiti? | service_request | Tool: create_service_request(category=Graffiti) | Creates a Graffiti case; photo recommended. |
| 17 | What's the status of case GID-2026-045821? | service_request | Tool: service_request_status_lookup(case_id) | Returns New / In Process / Referred / Closed. |
| 18 | Can I put pizza boxes in recycling? | trash | RAG | No — greasy/food-soiled paper goes in organics, not recycling. |
| 19 | Do I need a permit to work from home as a consultant? | business | RAG | No extra land-use permit if Home Occupation rules met; still need a Business Tax Certificate. |
| 20 | How do I pay my parking ticket? | general | RAG | Pay online with citation number at sandiego.gov/treasurer/payments/citation within 21 days. |
| 21 | How do I pay my water bill? | general | RAG | Pay via MyWaterSD online portal; bank-account payments have no fee. |
| 22 | Who is my city council member? | general | Tool: council_district_lookup(address) | Returns council district (1-9) and member for the address. |
| 23 | How do I register my dog? | general | RAG (refer) | Refer to San Diego Humane Society / County Animal Services — not a City function. |
| 24 | How do I register to vote? | general | RAG (refer) | Refer to County Registrar of Voters at sdvote.com. |
| 25 | When is street sweeping on my block? | general | Tool: street_sweeping_lookup(address) | Returns scheduled sweeping day/window (typically monthly, 7 AM-2 PM). |
| 26 | I have a broken trash can, how do I fix it? | trash | Tool: create_service_request(category=Container Repair) | Creates a Repair/Replace Container case, ~5-10 business day window. |
| 27 | Do I need a seller's permit to sell t-shirts online? | business | RAG (refer) | Yes — refer to CDTFA Seller's Permit (State), free to obtain. |
| 28 | How many free bulky item pickups do I get per year? | trash | RAG | Typically ~2 free pickups/year with an item cap per visit (verify current allowance). |
| 29 | What does "Issues Identified" mean on my permit? | permits | RAG | Plan reviewers found corrections needed; must resolve all before resubmitting (IB-610). |
| 30 | Can I rent out my house on Airbnb? | business | RAG | Need an STRO license, TOT certificate, Rental Unit Business Tax, and $1M liability insurance. |
