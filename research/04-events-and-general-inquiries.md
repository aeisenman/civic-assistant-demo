# City of San Diego — Events & General Resident Inquiries

Research for a city virtual assistant covering (A) how San Diego publishes events and the Special Events permit process, and (B) general resident inquiries a chatbot must field beyond trash/permits/business. Sourced from sandiego.gov where possible; unverifiable specifics are labeled **[Best guess]**.

## 1. Overview and Key URLs

| Area | URL |
|---|---|
| Citywide events/calendar hub | https://www.sandiego.gov/ (no single unified "events" calendar; calendars are per-department) |
| City Council Legislative Calendar (all council/committee meetings) | https://www.sandiego.gov/city-clerk/officialdocs/meetings-calendar |
| Council Docket / Agendas | https://www.sandiego.gov/city-clerk/city-council-docket-agenda |
| Citywide Agendas & Minutes (boards, commissions, planning groups) | https://www.sandiego.gov/citywide-agendas-minutes |
| Council meeting webcasts | https://sandiego.granicus.com/ViewPublisher.php?view_id=31 |
| District council calendars (e.g., District 1) | https://www.sandiego.gov/citycouncil/cd1/calendar |
| Parks & Recreation Calendar | https://www.sandiego.gov/park-and-recreation/calendar |
| Parks & Recreation Events Listing | https://www.sandiego.gov/park-and-recreation/calendarlisting |
| Parks & Recreation Programs and Activities | https://www.sandiego.gov/park-and-recreation/activities |
| Library Programs & Events | https://www.sandiego.gov/public-library/news-events |
| Library locations & hours | https://www.sandiego.gov/public-library |
| Special Events & Filming (Office of Special Events) | https://www.sandiego.gov/specialevents-filming |
| Special Event Permit application portal | https://specialeventapplication.sandiego.gov/ |
| Special Event Planning Guide (PDF) | https://www.sandiego.gov/sites/default/files/legacy/specialevents/pdf/planningguide.pdf |
| Special Event Related Permits (PDF) | https://www.sandiego.gov/sites/default/files/legacy/specialevents/pdf/SpecialEventRelatedPermits.pdf |
| Park Special Event Request Application (PDF) | https://www.sandiego.gov/sites/default/files/legacy/park-and-recreation/pdf/parkspecialeventapp.pdf |
| Public Utilities — Pay Your Bill | https://www.sandiego.gov/public-utilities/customer-support/pay-your-bill |
| MyWaterSD customer portal | https://customerportal.sandiego.gov/portal/One-TimePayment.aspx |
| Report a water leak / meter leak | https://www.sandiego.gov/public-utilities/customer-support/leaks |
| Parking Citations | https://www.sandiego.gov/parking/citations |
| Pay a Parking Citation (Treasurer) | https://www.sandiego.gov/treasurer/payments/citation |
| Get a Library Card | https://www.sandiego.gov/public-library/services/lending/librarycard |
| Council district lookup map | https://sandiego.maps.arcgis.com/apps/instant/nearby/index.html?appid=0c54f0bab6b448e4aa8ec942fdb89b82 |
| Street Sweeping | https://www.sandiego.gov/streetsweeping |
| Short-Term Residential Occupancy (STRO) | https://www.sandiego.gov/treasurer/short-term-residential-occupancy |
| Get It Done (311 non-emergency reporting) | https://www.sandiego.gov/get-it-done and https://getitdone.sandiego.gov |
| City Holidays | https://www.sandiego.gov/city-holidays |
| County Registrar of Voters | https://www.sdvote.com/ |
| County Animal Services — dog license | https://www.sandiegocounty.gov/das/license-laws/license.html |
| County Parks reservation system | https://parksres.sandiegocounty.gov/ |

The City does **not** have one unified "events calendar" product; events surface across the Council legislative calendar, Parks & Recreation calendar, Library events platform, and third-party listings (e.g., Eventbrite for library programs). This fragmentation is itself a key finding for the assistant design: a RAG layer needs to normalize across these sources.

## 2. Events: Listing Schema & Seed Data

### 2.1 Typical event listing schema

Observed/typical fields across sandiego.gov event sources:

| Field | Notes |
|---|---|
| `title` | Event name |
| `date` | Single date or date range (multi-day festivals, recurring farmers markets) |
| `start_time` / `end_time` | Local Pacific time; council meetings typically state only start time |
| `location` | Venue name + address; council meetings show "Council Chambers, 202 C St, 12th Floor" |
| `department` | Owning department (Parks & Rec, Library, City Clerk, Office of Special Events, Public Utilities, etc.) |
| `cost` | "Free" or dollar amount; many library/park programs are free, some require registration |
| `registration_link` | Eventbrite, Parks & Rec ActiveNet, or library BiblioCommons link; not all events require it |
| `accessibility_info` | ADA accommodation contact, usually a phone/email boilerplate ("To request accommodation, call 619-XXX-XXXX at least 5 business days in advance") |
| `description` | 1–3 sentence summary |
| `category` | e.g., Council Meeting, Public Hearing, Farmers Market, Festival, Library Program, Park Program |
| `recurrence` | For weekly/monthly recurring items (farmers markets, story times) |
| `contact` | Phone/email for the hosting division |
| `council_district` | Sometimes tagged for district-specific events/hearings |

### 2.2 Seed data — 25 dummy events (Sept–Nov 2026)

All entries below are fabricated for testing/demo purposes; they follow realistic naming, timing, and formatting conventions for the City but are **not real scheduled events**.

| # | Title | Date | Time | Location | Department | Cost | Description |
|---|---|---|---|---|---|---|---|
| 1 | City Council Meeting | 2026-09-08 | 10:00 AM | Council Chambers, 202 C St, 12th Floor | City Clerk / City Council | Free | Regular weekly council meeting; docket includes budget amendments and land use items. |
| 2 | Land Use & Housing Committee Meeting | 2026-09-10 | 9:00 AM | Council Committee Room, 202 C St, 12th Floor | City Council | Free | Committee review of proposed zoning changes in Midway-Pacific Highway. |
| 3 | Public Hearing: Short-Term Rental Ordinance Amendment | 2026-09-15 | 2:00 PM | Council Chambers, 202 C St | City Clerk | Free | Public hearing on proposed changes to STRO licensing tiers. |
| 4 | Hillcrest Farmers Market | 2026-09-06 | 8:00 AM–2:00 PM | 3960 Normal St, Hillcrest | Parks & Recreation (permitted vendor market) | Free entry | Weekly certified farmers market with 175+ vendors, produce, and prepared food. |
| 5 | Little Italy Mercato | 2026-09-05 | 8:00 AM–2:00 PM | India St & Date St, Little Italy | Parks & Recreation (permitted vendor market) | Free entry | Weekly farmers market spanning five blocks of Little Italy. |
| 6 | Ocean Beach Wednesday Market | 2026-09-09 | 4:00 PM–8:00 PM | Newport Ave, Ocean Beach | Parks & Recreation (permitted vendor market) | Free entry | Evening farmers/artisan market with live music. |
| 7 | Toddler Story Time | 2026-09-12 | 10:30 AM | North Park Library, 3795 31st St | Library | Free | Weekly interactive story time for ages 1–3 with songs and movement. |
| 8 | Central Library Author Talk: Local History Series | 2026-09-18 | 6:00 PM | San Diego Central Library, 330 Park Blvd | Library | Free, registration requested | Author discussion and Q&A on San Diego's Balboa Park centennial history. |
| 9 | Balboa Park Free Fitness in the Park | 2026-09-13 | 9:00 AM | Balboa Park, Marston Point | Parks & Recreation | Free | Community outdoor yoga/fitness class open to all skill levels. |
| 10 | Adult Coding Basics Workshop | 2026-09-20 | 1:00 PM | Mission Valley Library, 2123 Fenton Pkwy | Library | Free, registration required | Introductory computer/coding workshop for adults. |
| 11 | San Diego LGBTQ+ Pride Parade & Festival | 2026-09-19 to 2026-09-20 | 11:00 AM–8:00 PM | Balboa Park & University Ave, Hillcrest | Office of Special Events (permitted) | Free, some vendor fees | Annual two-day festival and parade with street closures on University Ave. |
| 12 | Environment Committee Meeting | 2026-09-23 | 9:00 AM | Council Committee Room, 202 C St | City Council | Free | Discussion of Climate Action Plan progress report. |
| 13 | Adoptable Pets Day | 2026-09-26 | 10:00 AM–3:00 PM | Kearny Mesa Recreation Center | Parks & Recreation (co-hosted w/ County Animal Services) | Free | Pet adoption and licensing info event. |
| 14 | Mission Bay Park Cleanup Day | 2026-09-27 | 9:00 AM–12:00 PM | Mission Bay Park, Bonita Cove | Parks & Recreation | Free, volunteer | Community volunteer shoreline and park cleanup. |
| 15 | City Council Meeting | 2026-10-06 | 10:00 AM | Council Chambers, 202 C St, 12th Floor | City Clerk / City Council | Free | Regular weekly council meeting; agenda includes FY2027 budget priorities workshop. |
| 16 | Public Hearing: Midway Rising Development Project | 2026-10-08 | 2:00 PM | Council Chambers, 202 C St | City Clerk / Planning Dept | Free | Hearing on entitlements for Midway District redevelopment. |
| 17 | Little Italy Mercato | 2026-10-10 | 8:00 AM–2:00 PM | India St & Date St, Little Italy | Parks & Recreation (permitted vendor market) | Free entry | Weekly farmers market. |
| 18 | Halloween Family Storytime & Craft | 2026-10-24 | 10:30 AM | Pacific Beach/Taylor Library, 4275 Cass St | Library | Free | Spooky-themed story time and pumpkin craft for families. |
| 19 | Fleet Week San Diego Kickoff Festival | 2026-10-03 to 2026-10-11 | Varies | Broadway Pier & North Embarcadero | Office of Special Events (permitted) | Free, some ticketed events | Multi-day celebration of military and maritime heritage with ship tours. |
| 20 | Balboa Park Oktoberfest Community Event | 2026-10-17 | 12:00 PM–6:00 PM | Balboa Park, Village Place | Office of Special Events (permitted) | $10 entry, kids free | Food, beer garden, and live music festival. |
| 21 | Rules Committee Meeting | 2026-10-21 | 9:00 AM | Council Committee Room, 202 C St | City Council | Free | Review of proposed campaign finance ordinance updates. |
| 22 | Dia de los Muertos Community Celebration | 2026-11-01 | 11:00 AM–5:00 PM | Chicano Park, Barrio Logan | Office of Special Events (permitted) | Free | Altars, folklorico dance, and vendor booths honoring Day of the Dead. |
| 23 | City Council Meeting | 2026-11-03 | 10:00 AM | Council Chambers, 202 C St, 12th Floor | City Clerk / City Council | Free | Regular weekly council meeting. |
| 24 | Veterans Day Ceremony | 2026-11-11 | 10:00 AM | Waterfront Park, 1600 Pacific Hwy | Parks & Recreation / City Council | Free | Annual civic ceremony honoring veterans with flag presentation. |
| 25 | Holiday Programming Kickoff: Winter Reading Challenge | 2026-11-21 | All day (branch hours) | All San Diego Public Library branches | Library | Free | Launch of citywide winter reading challenge for all ages, runs through January. |

## 3. Special Event Permit Workflow

Applies to anyone wanting to host an event on public property (streets, sidewalks, parks, beaches) — e.g., festivals, parades, runs/walks, block parties, farmers markets, filming with public impact. Administered by the **Office of Special Events and Filming**, Civic Center Plaza, 1200 Third Ave., Suite 1326, San Diego, CA 92101 · 619-685-1331 · SpecialEvents@sandiego.gov ([sandiego.gov/specialevents-filming](https://www.sandiego.gov/specialevents-filming)).

### 3.1 Numbered workflow

1. **Pre-application planning.** Applicant reviews the Special Event Planning Guide and Special Event Related Permits document to determine venue availability, whether the date falls on a City-published "impacted date" (limited due to public-safety staffing), and which sub-permits will be needed (park use, street closure, alcohol, amplified sound, food vendor, fireworks).
2. **Venue confirmation (if in a City park/beach).** Applicant contacts the relevant Park & Recreation division/facility manager to secure a Park Reservation *before* the citywide application is considered complete — a Park Reservation confirmation is a prerequisite attachment, not an afterthought.
3. **Application submission.** Applicant submits the Citywide Special Event Permit Application online via the Special Event Permit Application portal (https://specialeventapplication.sandiego.gov/), or by PDF for smaller "Neighborhood Block Party" events. Applications may be submitted up to **two years in advance** and must be submitted **no later than 60 days before the event date**. **[Widely-cited best practice, not always explicit on the site]** Larger events (parades, street closures affecting arterial roads, 5,000+ attendees) are commonly recommended to apply 90–120 days out to allow time for multi-department review and traffic control planning.
4. **Fee payment.** Applicant pays the **$341 standard application fee** (60+ days out). Applications filed less than 60 days before the event incur the $341 fee **plus $80 per business day late fee**. Fees for related sub-permits (street closure, park use, amplified sound, alcohol) are billed separately, along with cost-recovery charges for City Police/Fire staffing, barricades, and cleanup if applicable.
5. **Completeness check.** Office of Special Events staff logs the application on a first-come, first-served basis and reviews for completeness (all required fields, site map, insurance certificate, park reservation attached if applicable). Incomplete applications are not queued for full review until resubmitted.
6. **Cross-department routing and review.** Once complete, the application is routed in parallel to:
   - **San Diego Police Department** — traffic control plan, crowd management, staffing needs
   - **San Diego Fire-Rescue Department** — life-safety plan, occupancy limits, fire lane access, tent/stage permits
   - **Parks & Recreation** — park/beach use terms, turf protection, hours
   - **Transportation Department** — street/lane closures, detours, parking meter bagging
   - **Environmental Services** — waste/recycling plan, noise
   - **Special Events Traffic Control / Development Services** — encroachment and right-of-way permits as needed
   Each department returns approval, conditions, or denial comments; conflicts (e.g., competing road closures) are resolved by the Office of Special Events acting as coordinator.
7. **Insurance verification.** Applicant submits a Certificate of Insurance (commonly **$1M–$2M general liability [best-guess range, consistent with STRO precedent of $1M minimum]**) naming the City of San Diego as additional insured; verified before final approval.
8. **Conditions issued / revisions requested.** If departments impose conditions (reduced footprint, added medical staffing, earlier end time), the Office of Special Events communicates these back to the applicant, who may need to revise the site plan or route.
9. **Final approval and permit issuance.** Once all department sign-offs and insurance are on file and fees are paid, the Office of Special Events issues the Special Event Permit, which bundles/cross-references the sub-permits (park use, street closure, etc.).
10. **Day-of compliance.** City staff (Code Enforcement, Police, Fire, Parks) may inspect the event site for compliance with permit conditions; violations can result in on-site correction orders or forfeiture of future permit privileges.
11. **Post-event.** Applicant is responsible for site restoration/cleanup per permit conditions; City may conduct a post-event inspection before releasing any cleaning/damage deposit.

### 3.2 Application form fields (typical)

- Organizer/applicant name, organization, mailing address, phone, email
- Event name, description, and category (festival, race, parade, filming, block party, etc.)
- Event date(s) and hours (setup, event, teardown)
- Proposed location/route with site map or route map attached
- Expected attendance
- Street closure requested (Y/N) — streets/intersections affected
- Park/beach reservation confirmation number (if applicable)
- Amplified sound (Y/N), stage/tent structures (Y/N), fireworks/pyrotechnics (Y/N)
- Alcohol service (Y/N) — requires ABC permit reference
- Food vendors (Y/N) — count, and county health permit references
- Public safety/security plan and medical staffing plan
- Waste management/recycling plan
- Insurance certificate (Certificate of Liability Insurance, City as additional insured)
- ADA accessibility accommodations for attendees
- Emergency contact for day-of event
- Signature/certification agreeing to City indemnification terms

### 3.3 Status vocabulary

`Submitted` → `Under Review` (with sub-states per department: `Police Review`, `Fire Review`, `Parks Review`, `Transportation Review`) → `Incomplete – Additional Info Requested` → `Conditions Issued` → `Approved` → `Permit Issued` → `Denied` / `Withdrawn` → `Completed` (post-event closeout).

## 4. General Inquiries Reference Table

"Direct" = City can answer/complete within sandiego.gov; "Refer" = must route resident to County, State, Court, or other agency.

| # | Inquiry Type | Owning Dept/Agency | Direct or Refer | Canonical URL | One-sentence answer |
|---|---|---|---|---|---|
| 1 | Pay water/wastewater bill | City Public Utilities | Direct | https://www.sandiego.gov/public-utilities/customer-support/pay-your-bill | Pay online via MyWaterSD with a bank account (no fee) or card (1.59% residential convenience fee). |
| 2 | Report a water leak | City Public Utilities | Direct | https://www.sandiego.gov/public-utilities/customer-support/leaks | Call the Water Emergency Hotline at 619-515-3525; City repairs leaks on its side of the meter. |
| 3 | Request a leak bill adjustment | City Public Utilities | Direct | https://www.sandiego.gov/public-utilities/customer-support/leak-adjustment | Submit a leak adjustment request within 120 days of the first high bill caused by a concealed pipe leak. |
| 4 | Pay a parking citation | City Treasurer | Direct | https://www.sandiego.gov/treasurer/payments/citation | Pay online with your citation number within 21 days of issuance to avoid penalties. |
| 5 | Contest a parking citation | City Treasurer / Parking | Direct | https://www.sandiego.gov/parking/citations | File a contest online or by mail within 21 days; low-income payment plans are available. |
| 6 | Get a library card | City Library | Direct | https://www.sandiego.gov/public-library/services/lending/librarycard | Free for CA residents/property owners; start online, then bring photo ID and proof of address to any branch. |
| 7 | Reserve a park facility/picnic shelter | City Parks & Recreation | Direct | https://www.sandiego.gov/park-and-recreation/activities | Reserve picnic areas, sports fields, or event venues through Parks & Recreation's reservation system or by contacting the facility. |
| 8 | License a dog | County Animal Services / Humane Society | Refer (County) | https://www.sandiegocounty.gov/das/license-laws/license.html | Dog licensing is handled by San Diego Humane Society (incorporated cities) or County Animal Services, not the City directly. |
| 9 | Register to vote | County Registrar of Voters | Refer (County) | https://www.sdvote.com/ | Voter registration is run by the County Registrar of Voters at sdvote.com, not the City. |
| 10 | Find my council district | City Clerk / Council | Direct | https://sandiego.maps.arcgis.com/apps/instant/nearby/index.html?appid=0c54f0bab6b448e4aa8ec942fdb89b82 | Enter your address in the interactive Council District map to find your district and council member. |
| 11 | City office hours/holidays | City Human Resources / Citywide | Direct | https://www.sandiego.gov/city-holidays | Most City offices are open Mon–Fri (hours vary by department) and closed on published City holidays. |
| 12 | Street sweeping schedule | City Transportation / Street Division | Direct | https://www.sandiego.gov/streetsweeping | Enter your address in the online street sweeping map; residential streets are typically swept monthly, 7 AM–2 PM. |
| 13 | Short-term rental (STRO) licensing | City Treasurer | Direct | https://www.sandiego.gov/treasurer/short-term-residential-occupancy | Hosts need a TOT certificate, business tax certificate, and STRO license (tiered by rental type) with $1M liability insurance. |
| 14 | Report a pothole, graffiti, streetlight outage | City Get It Done (311) | Direct | https://www.sandiego.gov/get-it-done | Submit via the Get It Done app, web form, or by phone; over 65 non-emergency issue types are tracked to resolution. |
| 15 | Report illegal dumping | City Get It Done / Environmental Services | Direct | https://www.sandiego.gov/get-it-done | Report through Get It Done; City crews are dispatched to remove dumped waste from public right-of-way. |
| 16 | Trash/recycling collection schedule | City Environmental Services | Direct | https://www.sandiego.gov/environmental-services-department | Look up your address-specific collection day on the Environmental Services collection calendar tool. |
| 17 | Business tax certificate | City Treasurer | Direct | https://www.sandiego.gov/treasurer/business-tax | All businesses operating in the City must obtain a Business Tax Certificate from the Treasurer's Office. |
| 18 | Building permit status | City Development Services Dept (DSD) | Direct | https://www.sandiego.gov/development-services | Check permit status through the DSD's Online Permit Center using the permit or project number. |
| 19 | Pay property tax | County Treasurer-Tax Collector | Refer (County) | https://www.sdttc.com/ | Property taxes are billed and collected by the County Treasurer-Tax Collector, not the City. |
| 20 | DMV vehicle registration | State DMV | Refer (State) | https://www.dmv.ca.gov/ | Vehicle registration and driver's licenses are handled by the California DMV, not the City. |
| 21 | Small claims / traffic court questions | Superior Court of CA, San Diego | Refer (State/Court) | https://www.sdcourt.ca.gov/ | Traffic citation contests and small claims filings go through the San Diego Superior Court, not the City. |
| 22 | Homeless services/shelter referral | City Homelessness Strategies & Solutions Dept | Direct | https://www.sandiego.gov/homelessness | Call the Homeless Outreach Team or 211 San Diego for shelter beds, services, and outreach referrals. |
| 23 | Noise complaint | City Code Enforcement / Police (non-emergency) | Direct | https://www.sandiego.gov/get-it-done | Non-urgent noise complaints go through Get It Done; ongoing disturbances can be reported to SDPD's non-emergency line (619-531-2000). |
| 24 | Tree trimming/removal on public property | City Parks & Recreation (Urban Forestry) | Direct | https://www.sandiego.gov/get-it-done | Report hazardous public trees via Get It Done; Urban Forestry evaluates and schedules trimming/removal. |
| 25 | Farmers market locations | City Parks & Recreation (permits vendor markets) | Direct | https://www.sandiego.gov/park-and-recreation/calendar | Farmers markets operate under City vendor-market permits; check the Parks & Rec calendar or individual market websites for days/hours. |
| 26 | Council/committee meeting schedule | City Clerk | Direct | https://www.sandiego.gov/city-clerk/officialdocs/meetings-calendar | Full council and committee meeting dates are on the Legislative Calendar; most council meetings are Tuesdays at 10 AM. |
| 27 | Watch a council meeting | City Clerk / Granicus | Direct | https://sandiego.granicus.com/ViewPublisher.php?view_id=31 | Council and committee meetings are livestreamed and archived on the City's Granicus webcast portal. |
| 28 | Passport application | US Postal Service / State Dept (some libraries) | Refer (Federal) | https://travel.state.gov/ | Passports are a federal service; some San Diego library branches offer passport acceptance by appointment. |
| 29 | Marriage license | County Clerk/Recorder | Refer (County) | https://www.sdarcc.gov/ | Marriage licenses are issued by the County Assessor/Recorder/County Clerk, not the City. |
| 30 | Utility bill for gas/electric (SDG&E) | Investor-owned utility (SDG&E) | Refer (Private utility) | https://www.sdge.com/ | Gas and electric service is provided by SDG&E, a private utility, not the City. |

## 5. Top 20 Resident FAQs (RAG Seed)

1. **What's happening this weekend?** Check the Parks & Recreation calendar (sandiego.gov/park-and-recreation/calendar) and Library events page (sandiego.gov/public-library/news-events) — most weekend listings include family programs, farmers markets, and any permitted festivals.
2. **Is the library open today?** Hours vary by branch; check your branch's page under sandiego.gov/public-library or call 619-236-5800. Most branches close on City holidays.
3. **When is the next City Council meeting?** Regular meetings are typically Tuesdays at 10:00 AM in Council Chambers, 202 C St, 12th Floor; confirm the exact date on the Legislative Calendar.
4. **How do I watch the council meeting online?** Livestream and archived video are on the City's Granicus webcast page (sandiego.gov/city-clerk → Webcasts).
5. **Where's the nearest farmers market?** San Diego has 30+ certified farmers markets; check by neighborhood and day of week — e.g., Sunday: Hillcrest; Saturday: Little Italy, Pacific Beach; Wednesday: Ocean Beach, Little Italy.
6. **How do I get a library card?** Apply online for a temporary card, then bring photo ID and proof of address to any branch to activate it; free for CA residents.
7. **How do I pay my water bill?** Pay online through MyWaterSD (sandiego.gov/public-utilities/customer-support/pay-your-bill), by phone, mail, or in person; bank account payments have no fee.
8. **I have a water leak — who do I call?** Call the Water Emergency Hotline, 619-515-3525. If it's on the City's side of the meter, a crew is dispatched; if it's on your property, it's your responsibility.
9. **How do I pay a parking ticket?** Use your citation number at sandiego.gov/treasurer/payments/citation within 21 days; payment plans exist for qualifying low-income residents.
10. **How do I find my council district?** Use the interactive Council District map and enter your address, or check the ZIP-code list PDF on sandiego.gov.
11. **How do I report a pothole/graffiti/broken streetlight?** Use the Get It Done app, web form, or call 619-236-5555 (non-emergency); most requests are tracked to resolution with a case number.
12. **When is street sweeping on my block?** Enter your address in the online street sweeping map; sweeping is generally 7 AM–2 PM and residential streets are swept about monthly.
13. **Do I need a permit to host an event in a park?** Yes — any organized event using City parks, streets, or public property requires a Special Event Permit and, for parks, a separate Park Reservation from Parks & Recreation.
14. **How far in advance do I need to apply for an event permit?** Applications are accepted up to two years ahead and must be submitted at least 60 days before the event; larger events should plan for 90–120 days to allow multi-department review.
15. **How much does a special event permit cost?** The base application fee is $341 (60+ days out); late applications add $80/business day, plus separate fees for street closures, park use, and public safety staffing.
16. **Can I rent out my house on Airbnb in San Diego?** You need a Short-Term Residential Occupancy (STRO) license, an active Transient Occupancy Tax certificate, a Rental Unit Business Tax account, and $1M liability insurance.
17. **How do I license my dog?** Dog licensing is handled by San Diego Humane Society (for incorporated cities including San Diego) or County Animal Services (unincorporated areas) — not directly by the City.
18. **How do I register to vote / find my polling place?** Register online at sdvote.com through the County Registrar of Voters; the City does not manage voter registration.
19. **What are City Hall's hours and which holidays are offices closed?** Most departments operate Mon–Fri during standard business hours and close on published City holidays listed at sandiego.gov/city-holidays.
20. **Is there a City chatbot or 311 I can just call?** Yes — Get It Done (app, web, and phone) functions as the City's 311-style non-emergency reporting and inquiry channel for service requests; general phone inquiries can also go through department main lines.

## 6. Backend Automation Opportunities

- **Intent classification / routing.** Classify inbound resident messages into event lookup, bill payment, permit application, service request (Get It Done), or "refer to another agency" (County/State/Court/private utility) — the table in Section 4 is a ready-made routing map (department, direct-vs-refer flag, canonical URL) that can seed a classifier's label set and a deterministic fallback lookup.
- **Cross-department referral engine.** For inquiries the City cannot resolve (dog licensing, voter registration, property tax, DMV, marriage license, SDG&E), auto-generate a referral response with the correct agency name, URL, and phone — reducing "wrong department" transfers and dead-end answers.
- **Event RAG index with schema normalization.** Because events live across at least four different systems (Legislative Calendar, Parks & Rec calendar, Library/BiblioCommons/Eventbrite, Office of Special Events "impacted dates" list), an automation layer should periodically scrape/ingest each source into the unified schema in Section 2.1, then answer "what's happening this weekend" or "is there a council meeting this week" from one normalized index instead of live-querying four sites per question.
- **Special event permit completeness checker.** Before human staff review, an LLM-driven intake bot can validate that an applicant's submission includes all required fields from Section 3.2 (site map, insurance certificate, park reservation confirmation if applicable, ADA plan), flag missing items, and pre-populate the "Incomplete – Additional Info Requested" status automatically, cutting the manual completeness-review step in the workflow.
- **Lead-time and date-conflict advisor.** Given a proposed event date/location, a workflow engine can check against a maintained "impacted dates" and existing-permit calendar, warn applicants if their date is within the 60-day minimum lead time (triggering the late fee) or conflicts with another permitted event/venue capacity, and recommend the 90–120 day lead time for large-footprint events before they submit.
- **Multi-department review orchestration.** Model the Police/Fire/Parks/Transportation/Environmental Services review fan-out (Section 3.1, step 6) as a workflow with parallel approval tasks, SLA timers per department, and automatic escalation/nudge if a department hasn't responded within X business days — turning an email/paper-driven process into a trackable status pipeline with the vocabulary in Section 3.3.
- **Bill-pay and citation deep-linking.** For "pay my water bill" / "pay my parking ticket" intents, the assistant can hand off directly to MyWaterSD or the Treasurer citation portal with prefilled context (account/citation number capture) rather than just returning a URL, reducing follow-up turns.
- **Council district and address-based personalization.** Use the council-district lookup as a backend service so the assistant can auto-answer "who is my council member" and surface district-specific meeting/event content without the resident needing to know their district number.
- **Anomaly/complaint triage for Get It Done.** Route free-text resident reports (pothole, graffiti, illegal dumping, noise) into the correct Get It Done category automatically using intent classification, attach any provided photo/GPS metadata, and return the resulting case number conversationally instead of directing users to fill out the form themselves.
