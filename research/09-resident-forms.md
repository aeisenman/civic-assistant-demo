# 09 — Resident & Business Forms: Does the Intake Design Generalize?

Research question: beyond the demo's three schemas (`PermitFields`, `BusinessTaxFields`,
`ServiceRequestFields` in `api/app/workflows/schemas.py`) and the one status spine
(`submitted → validating → needs_info → routed → in_review → approved/rejected → issued →
closed`, `api/app/workflows/engine.py`), what else do San Diego residents and businesses
actually file, and would the same pydantic-schema-drives-everything pattern hold up? Researched
via WebSearch/WebFetch against sandiego.gov, data.sandiego.gov/seshat, and City ArcGIS layers,
September 2026. Every fact below is sourced; where no City-published number exists this says so
rather than estimating one.

## 1. Inventory — 26 forms and applications

Volume column: a hard published number where one exists, otherwise the best available proxy
(dataset size, cumulative counter, qualitative signal), always with its source. "API/dataset"
names the concrete endpoint, not just "yes."

| Form | Dept | Who files | Volume / demand (source) | Fee | Filed today | API / open dataset | Required fields (partial list) |
|---|---|---|---|---|---|---|---|
| Building Permit *(existing)* | DSD | Owner/contractor | Dataset: 653 MB all-approvals file, daily [data.sandiego.gov/datasets/development-permits](https://data.sandiego.gov/datasets/development-permits/) | Valuation-based, IB-101/501 | Accela ACA online | ArcGIS `DSDPermits` layer + seshat CSV | applicant, address, permit type, description, valuation |
| Business Tax Certificate *(existing)* | Treasurer | Any business | Active-cert CSV 18 MB, tens of thousands of rows [data.sandiego.gov/datasets/business-listings](https://data.sandiego.gov/datasets/business-listings/) | Employee-tiered, $34–$125+ | Online/mail/in-person | seshat CSV | business name, owner, address, start date, employees, ownership type |
| Get It Done Service Request *(existing)* | Multiple (routed) | Resident | 296,209 reports in 2021; 3.5M+ cumulative since 2016; 1,000+/day now — [insidesandiego.org](https://www.insidesandiego.org/ten-years-getting-it-done-city-san-diego) | Free | Web/app/phone | seshat daily CSV [data.sandiego.gov/datasets/get-it-done-reports](https://data.sandiego.gov/datasets/get-it-done-reports/) (read-only, no write API) | category, address, description |
| Special Event Permit | Office of Special Events | Event organizer | No public count found | $341 base + $80/business-day if <60 days out — [00-synthesis.md §3](00-synthesis.md) | [specialeventapplication.sandiego.gov](https://specialeventapplication.sandiego.gov/) | special_events CSV exists but is **stale** (2023 last-modified, 2021 rows) — [05-live-data-sources.md](05-live-data-sources.md) | event name/dates/location, attendance, street closure, alcohol, insurance cert |
| Neighborhood Block Party Permit | Office of Special Events | Resident | No public count | Lower than full Special Event fee (not itemized) | PDF application — [00-synthesis.md §52](00-synthesis.md) | None found | block/street segment, date, neighbor consent |
| Encroachment / Right-of-Way Permit | DSD / Engineering & Capital Projects | Contractor, utility, owner | 9,415 cumulative records, `APPROVAL_TYPE LIKE '%Encroachment%'` — ArcGIS `DSDPermits` layer 1 query, this session | Plan check $3,179–$16,694 + inspection $2,649–$4,637 tiered by linear ft + valuation-based deposit — [IB-502](https://www.sandiego.gov/development-services/forms-publications/information-bulletin/502) | Accela ACA | [webmaps.sandiego.gov ArcGIS DSDPermits/MapServer/1](https://webmaps.sandiego.gov/arcgis/rest/services/DoIT_Public/DSDPermits/MapServer/1/query) | D-sheets, storm water checklist, project contacts, ownership disclosure, encroachment exhibit |
| Traffic Control Permit | DSD | Contractor | 32,210 cumulative records, same ArcGIS layer/query as above (highest record count of any type checked) | $87.68 flat + plan-check tiers — [IB-502](https://www.sandiego.gov/development-services/forms-publications/information-bulletin/502) | Accela ACA | Same ArcGIS layer | DS-269 plan, work dates/hours, closure limits |
| Sidewalk Vendor Permit | Treasurer | Individual vendor | No public count; only third-party enforcement-cost reporting — [NBC7](https://www.nbcsandiego.com/news/local/each-san-diego-street-vendor-costs-taxpayers-1800-could-be-6200-next-year/3228747/) | $38/yr — [FY25 fee schedule](https://www.sandiego.gov/sites/default/files/2024-07/fy25-user-fee-schedule_0.pdf) | **In-person appointment only**, no online portal — [sandiego.gov/sidewalk-vending/application](https://www.sandiego.gov/sidewalk-vending/application) | None found | photo ID, seller's permit #, county health permit (food) |
| Public Records Request (CPRA) | City Clerk / IT (custodial depts) | Anyone (anonymous allowed) | 43,876 cumulative requests shown live — [sandiego.nextrequest.com](https://sandiego.nextrequest.com/) | Free; $0.25/page copies | Online only, NextRequest portal | Public request log viewable without login (no formal API) | description of records, date range |
| Claim for Damages | Risk Management | Resident/business/attorney | 1,557 new claims FY2022, $66.6M in claim costs — [FY2022 Risk Mgmt Annual Report](https://www.sandiego.gov/sites/default/files/2023-11/rmannualreport.pdf) | Free | Paper RM-9 by mail/fax/in-person, or Ventiv online portal (third-party vendor) | None found | claimant info + SSN, incident date/location, basis of claim, amount claimed, signature |
| Fire Alarm Monitoring Permit | SDFD/SDPD alarm program | Any owner with monitored alarm | No permit-count published; ~100 false alarms/day cited by secondary press (not verified) — [firehouse.com](https://www.firehouse.com/leadership/news/10462808/san-diego-may-charge-for-false-alarm-calls) | $31/yr (raised from $20, effective 7/1/2025) — [sdpdalarmpermits.sandiego.gov](https://sdpdalarmpermits.sandiego.gov/) | Online portal or mail | None found | property address, alarm company + license #, 2 keyholder contacts |
| Fire Alarm/Sprinkler Plan Review | SDFD Fire Prevention Bureau | Contractor | No count | Tiered by device/head count, $176–$882+ — [IB-506 Table 506A](https://www.sandiego.gov/development-services/forms-publications/information-bulletins/506) | Online form (since 3/2021) or Accela | None found | DS-506 fee worksheet, DS-345 contacts, stamped plans |
| Tents/Canopies Permit | SDFD | Event organizer | No count | $327 tiered by sq ft — [FY17 fee schedule](https://www.sandiego.gov/sites/default/files/fy17feeschedule_5.pdf) | Not confirmed | None found | site diagram, dimensions |
| Fireworks/Pyrotechnics Display Permit | SDFD | Event producer | No count | $240/event + fire-watch hourly — [specialevents.pdf](https://www.sandiego.gov/sites/default/files/legacy/fire/pdf/specialevents.pdf) | Paper application | None found | State Fire Marshal report, licenses, insurance cert |
| Public Assembly Permit (50+ people) | SDFD | Event/venue organizer | No count | Not confirmed | Paper application | None found | site plan + floor plan with exits |
| Film Permit | San Diego Film Office (Parks & Rec) | Production company | 439 permits, most recent year; economic impact fell $17.4M→$10.6M — [timesofsandiego.com](https://timesofsandiego.com/arts/2026/05/26/one-battle-after-another-san-diego-film-industry-city-budget/) | Free registration; $341+$80/day if late; $50 non-refundable for park filming — [sdparks.org](https://www.sdparks.org/content/sdparks/en/shop/PermitsandFees.html) | Online, [specialeventapplication.sandiego.gov](https://www.sandiego.gov/specialevents-filming/filming/registration) | None found | contact, location, dates, equipment, special effects |
| STRO (Short-Term Residential Occupancy) License | Treasurer | Property owner/host | **7,954 active licenses** — [data.sandiego.gov/datasets/stro-licenses](https://data.sandiego.gov/datasets/stro-licenses/) | $33–41 application + $193–$1,129 license, tiered — [06-parking-utilities-housing.md](06-parking-utilities-housing.md) | Accela ACA | ArcGIS `Treasurer/STRO_ACTIVE_LICENSES` layer + seshat CSV | property address, tier, TOT certificate |
| Residential Parking Permit | Transportation Dept | Resident in a permit district | No public count | $11.50/yr (max 4/address); $9 temp 2-week — [sandiego.gov/parking/permits/respermit](https://www.sandiego.gov/parking/permits/respermit) | Online | None found | address, proof of residency, delinquent-citation check |
| Temporary Overnight RV Permit (TORVP) | Transportation Dept | RV owner | No count | $1.50/24hr, max 72/yr — [sandiego.gov/parking/permits/torvp](https://www.sandiego.gov/parking/permits/torvp) | Online | None found | address, proof of residency, dates |
| Water Service Start (Move-In) | Public Utilities | New occupant/owner | No transaction count; ~1.4M water customers total (proxy) | Not published (deposit may apply) | Online [water.sandiego.gov/s/movein](https://water.sandiego.gov/s/movein) or phone | None found | service address, move-in date |
| Water Service Stop (Move-Out) | Public Utilities | Departing occupant/owner | No count | Final bill = estimated read | Online [water.sandiego.gov/s/moveout](https://www.sandiego.gov/public-utilities/customer-support/stop-service) or phone | None found | service address, move-out date, forwarding address |
| Rental Unit Business Tax Certificate | Treasurer | Landlord (any rental property) | Folded into the Business Tax Certificates dataset; not separately counted by NAICS — [data.sandiego.gov/datasets/business-listings](https://data.sandiego.gov/datasets/business-listings/) | $50 base + $5/unit (SFR) up to $150 + $8/unit (101+ units) — [rtaxfees](https://www.sandiego.gov/treasurer/taxesfees/btax/rtaxfees) | Billed by mail annually, or online | Same BTC dataset (not isolatable) | owner name, property address, unit count |
| Sign Permit *(seed data exists)* | DSD | Business/sign contractor | Part of Development Permits dataset (not isolated) | Flat, per `permit_types.json` | Accela ACA | Same as Building Permit | vicinity map, dimensions, setbacks |
| Grading Permit *(seed data exists)* | DSD | Contractor | Part of Development Permits dataset | Valuation/cubic-yard based | Accela ACA | Same as Building Permit | site/grading plan |
| Demolition Permit *(seed data exists)* | DSD | Owner/contractor | Part of Development Permits dataset | Flat/valuation | Accela ACA | Same as Building Permit | structure description, address |
| Dog/Pet License | **Not a City of San Diego function** | Pet owner | N/A | N/A | [sandiego.docupet.com](https://www.sandiego.gov/park-and-recreation/activities/animalservices) | N/A | N/A |

Note on the last row: licensing is delegated to the San Diego Humane Society (the City's
contracted animal-control agency) via the DocuPet platform, not administered by a City
department; unincorporated county areas use County DAS instead —
[sandiego.gov/park-and-recreation/activities/animalservices](https://www.sandiego.gov/park-and-recreation/activities/animalservices).
Kept in the table because it was an explicit candidate to check; it is out of scope for a
City-only demo.

## 2. Ranked shortlist — six highest-value additions

Ranked by real volume, fit with the existing state machine, and whether a certificate/permit
is issued at the end.

| Rank | Form | Why |
|---|---|---|
| 1 | STRO License | Real, counted volume (7,954 active); fits the spine exactly; ends in an issued license number. Already has the deepest existing research (`06-parking-utilities-housing.md`). |
| 2 | Encroachment / Right-of-Way Permit | Highest raw record counts found in this research (32,210 Traffic Control + 9,415 Encroachment, cumulative); good fit; ends in an issued permit; showcases a deposit/tiered fee model the demo doesn't have yet. |
| 3 | Special Event Permit | Already the most-asked FAQ in the existing KB (`00-synthesis.md` §2 Q13); ends in an issued permit; stress-tests the spine's single `routed` status against a real multi-department parallel review (Police/Fire/Parks/Transportation). |
| 4 | Residential Parking Permit | Simple, well-understood resident transaction; clean fit; ends in an issued decal/permit number; good contrast case (cheap, fast) next to the heavier permits above. |
| 5 | Claim for Damages | Real published annual volume (1,557 claims, FY2022); output is a decision letter, not a certificate, so it stretches the "issued" hook's meaning; also one of the three OCR-heavy forms below, testing the scanned-document intake path directly. |
| 6 | Public Records Request | Largest raw counter of all (43,876 cumulative on NextRequest); weakest fit of the six — no certificate is issued, "approved" doesn't quite describe a records production — included because it best tests whether the spine generalizes past permits. |

### Field-level detail

**1. STRO License** — Treasurer, no published SLA.
```
applicant_name: str            # required
contact_email: str             # required
property_address: str          # required
tier: Literal["tier1","tier2","tier3","tier4"]   # required
host_resides_onsite: bool | None   # required if tier == "tier2"
days_rented_per_year: int | None   # required if tier == "tier1"; must be <=20
tot_certificate_number: str | None # required before "issued"
owner_or_agent: Literal["owner","authorized_agent"]  # required
```
Fee: `application_fee + license_fee` by tier — tier1 $33+$193, tier2 $33+$284, tier3/4 $41+$1,129
([06-parking-utilities-housing.md](06-parking-utilities-housing.md)). Statuses: full spine;
`in_review` also checks the citywide 1% housing-stock cap for tier3/4.

**2. Encroachment / Right-of-Way Permit** — DSD/Engineering, no published review SLA; permit
valid 2 years + two 6-month extensions.
```
applicant_name: str             # required
project_address: str            # required
encroachment_type: Literal["driveway_apron","utility_cut","dumpster_or_sidewalk_closure",
                            "retaining_wall","tree_planting","banner_over_street","other"]
linear_feet: float | None        # required if encroachment_type == "utility_cut"
valuation_usd: float | None      # drives the deposit tier
start_date: date                 # required
end_date: date                   # required, must be >= start_date
insurance_cert_doc_id: str | None  # required for Process 2+
```
Fee: plan-check ($3,179–$16,694 by sheet count) + inspection ($2,649–$4,637 by linear-ft
band) + valuation-based deposit ($2,500 flat under $25k, scaling toward 4% over $250k) — IB-502.
Statuses: full spine; `routed` branches on process tier (1/2/4/5).

**3. Special Event Permit** — Office of Special Events, 60-day minimum lead time.
```
organizer_name: str             # required
event_name: str                 # required
event_date_start: date          # required, must be submitted >=60 days prior or late fee applies
location: str                   # required
expected_attendance: int        # required
street_closure: bool            # required
alcohol_service: bool           # required
certificate_of_insurance_doc_id: str | None   # required before issuance
site_map_doc_id: str | None     # required
```
Fee: `$341` base, `+ $80 * business_days_short` if filed <60 days out, plus un-modeled
sub-permit fees (street closure, sound, alcohol, staffing). Statuses: full spine — `routed`
is really a fan-out to Police/Fire/Parks/Transportation, which the current single-status
design can't represent without extension; flagged as a real gap, not glossed over.

**4. Residential Parking Permit** — Transportation Dept, no published SLA.
```
resident_name: str              # required
property_address: str           # required, must be inside an established permit district
permit_type: Literal["annual","temporary_2week"]  # required
num_permits_requested: int      # required, max 4 per address (5 in Area E)
proof_of_residency_doc_id: str  # required
```
Fee: `$11.50 * num_permits_requested` (annual) or `$9` flat (temporary). Statuses: full spine,
though `in_review` is likely a rubber stamp once `validating` clears delinquent citations.

**5. Claim for Damages** — Risk Management, 45-day statutory processing window.
```
claimant_name: str              # required
claimant_address: str           # required
claimant_ssn_or_tax_id: str | None   # required (Medicare reporting, MMSEA §111)
incident_date: date              # required, must be within 6 months (Gov Code §911.2)
incident_location: str          # required
basis_of_claim: str             # required, long text
amount_claimed_usd: float       # required
claim_type: Literal["limited","unlimited"] | None  # required if amount_claimed_usd > 12500
signature_confirmed: bool       # required
```
Fee: none. Statuses: full spine; `approved`/`rejected` maps to settlement vs. a denial letter
(Government Claims Act remedies notice), not a certificate — `issued` becomes "decision letter
sent," a semantic stretch worth naming explicitly.

**6. Public Records Request** — City Clerk / departmental custodians, 10-day statutory response
(+14-day extension, Gov Code §7922.535).
```
requester_name: str | None       # optional — anonymous requests allowed
requester_email: str | None      # recommended, not required
records_description: str        # required, long text
date_range_start: date | None
date_range_end: date | None
delivery_preference: Literal["electronic","paper_copy","in_person_inspection"]  # required
```
Fee: free; `$0.25/page` for paper copies. Statuses: weakest fit of the six — there is no
certificate; `issued` would need to mean "records delivered" and `rejected` would need to carry
a statutory exemption citation rather than a generic reason string.

## 3. Where a scan or photo is the normal filing path (OCR matters)

| Form | Why it's normally a scan/photo | Source |
|---|---|---|
| DS-3042 Owner-Builder Verification | Must be read, initialed, signed, **notarized** if the owner isn't present in person, then uploaded to the DSD portal — never filled as native web-form fields | [IB-153](https://www.sandiego.gov/development-services/forms-publications/information-bulletins/153), [ds3042.pdf](https://www.sandiego.gov/sites/default/files/legacy/development-services/pdf/industry/forms/ds3042.pdf) |
| RM-9 Claim for Damages | Instructions say it "must be accurately completed, printed, signed... and mailed or delivered in person," or faxed — no online field-entry path exists | [Risk Mgmt FAQ](https://www.sandiego.gov/riskmanagement/services/liability/faqg), [rm-9-claim-form.pdf](https://www.sandiego.gov/sites/default/files/rm-9-claim-form.pdf) |
| Special Event Certificate of Insurance | Insurer-issued PDF with specific "Additional Insured" endorsement language naming the City — inherently a third-party document uploaded with the application, not typed into a form | [Risk Mgmt special-events FAQ](https://www.sandiego.gov/riskmanagement/services/liability/faqse), [insurance requirements PDF](https://www.sandiego.gov/sites/default/files/city_of_san_diego_insurance_requirements.pdf) |

Runner-up: the sworn Contractor/Subcontractor Workers' Compensation Declaration attached to
building-permit applications is the same pattern (a signed legal declaration, not form fields) —
[sandiego.gov/development-services/permits-inspections/contractor-and-subcontractor-verification](https://www.sandiego.gov/development-services/permits-inspections/contractor-and-subcontractor-verification).

## 4. Where the demo's three schemas diverge from the real City forms

| Schema | Divergence | Real form |
|---|---|---|
| `PermitFields` | No `historic_flag` (structure age ≥45 yr) or `applicant_role` (Owner/Agent/Other), both required on the real DS-3032; `owner_builder: bool` exists but nothing enforces that a true owner-builder application also needs a DS-3042 attached, nor that a No-Plan approval needs a DS-6005 | [DS-3032 application](https://www.sandiego.gov/sites/default/files/legacy/development-services/pdf/industry/forms/ds3032.pdf), [00-synthesis.md §2](00-synthesis.md) |
| `PermitFields` | `valuation_usd` is the only fee input modeled; the real fee is inspection fee (IB-101, valuation-based) **plus** a separate plan-check fee (IB-501, roughly 65–85% of the permit fee) that this schema/fee logic doesn't compute at all | [IB-501](https://www.sandiego.gov/development-services/forms-publications/information-bulletins/501), `api/seed_data/permit_types.json` comment on `BLDGPLAN` |
| `BusinessTaxFields` | No field for "police-regulated" or "fire-regulated" activity flags, which on the real BTaxApp Parts 4/5 route the application to SDPD or Fire-Rescue for extra review — this schema has no routing input for that at all | [00-synthesis.md §2](00-synthesis.md) BusinessTaxApplication workflow step 3 |
| `BusinessTaxFields` | No distinction between a standard Business Tax Certificate and a **Rental Unit** Business Tax Certificate, which uses a completely different fee formula (`$50 base + $5/unit` tiered by unit count, not the `$34`/`$125+$5/employee` employee-tier formula) — a landlord using this schema would get the wrong fee | [rtaxfees](https://www.sandiego.gov/treasurer/taxesfees/btax/rtaxfees) |
| `ServiceRequestFields` | `category` is a free-text string; the real Get It Done taxonomy is a closed set of ~65 types rolled up into 23 categories, so extraction can invent a category that doesn't exist in the real system | [00-synthesis.md §1](00-synthesis.md) ServiceRequest schema |
| `ServiceRequestFields` | `photo_note` is a free-text note about a photo, not an actual photo/document reference; the real system requires an attached photo for graffiti and illegal-dumping reports and won't accept a text description in place of one | [03-trash-and-service-requests.md](03-trash-and-service-requests.md) |

## Sources not otherwise inlined
ArcGIS `DSDPermits` layer 1 record counts (Encroachment 9,415 / Traffic Control 32,210) were
pulled live in this research pass via `https://webmaps.sandiego.gov/arcgis/rest/services/DoIT_Public/DSDPermits/MapServer/1/query`
with `returnCountOnly=true`; both are all-time cumulative totals (dataset covers ~2003–present),
not single-year figures — an order-of-magnitude signal, not an annual count.
