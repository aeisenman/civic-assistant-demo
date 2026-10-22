# 06 — Parking, Utilities, Housing (M7 KB expansion)

Research note for `api/kb/parking.md`, `api/kb/utilities.md`, `api/kb/housing.md` and the
referral rows appended to `api/seed_data/referrals.json`. This assistant is a demo for a
**fictional** City of San Diego; facts below are drawn from real sandiego.gov (and sdhc.org)
pages as of September 2026 but any fee or turnaround time repeated in the KB is labelled an
estimate there, since a fictional city cannot promise a real government's exact numbers.
Sources were reached via WebSearch + WebFetch on 2026-09-05; some fetched pages are AI
summaries of the live page rather than a verbatim scrape, so treat exact dollar figures as
"as reported by the page on this date," not audited.

## Parking

- **Citations — pay/contest.** Pay online at the citation portal (citation number or plate +
  state); the current online payment processor is `dspayments.com/SanDiego`, linked from
  `sandiego.gov/parking/citations`. Contesting uses a separate "Request for Administrative
  Review" portal. Paying is an admission of liability and closes the dispute window — don't pay
  if you intend to contest. Unpaid citations become delinquent, add penalties/interest, and can
  end up as a DMV registration hold. Low-income payment plans exist.
  https://www.sandiego.gov/parking/citations
- **Meters.** Downtown/Uptown/Mid-City/Pacific Beach meter rate raised to $2.50/hour (from
  $1.25) in a Jan 2026 pilot. Standard enforcement Mon–Sat 8am–6pm; Hospitality Zone
  (Downtown) and Hillcrest Commercial Zone run later (to 8pm, with some pilot zones extending
  further and adding Sunday enforcement in commercial areas). Always defer to the posted sign.
  https://www.sandiego.gov/parking/meterops/variedrates
- **Residential parking permits.** Annual permit $11.50; two-week temporary permit $9; max 4
  permits per qualifying address (3 decals + 1 visitor, or 4 decals; Area E allows 5 decals with
  no visitor permit). All fees non-refundable. Apply online; delinquent citations must be paid
  first. Establishing a brand-new permit district takes up to ~18 months and needs signatures
  from ≥50% of resident households in the proposed area.
  https://www.sandiego.gov/parking/permits/respermit ,
  https://www.sandiego.gov/parking/permits/establish
- **Oversized vehicles / RVs.** Neighborhood Parking Protection Ordinance (SDMC §86.0139):
  vehicles over 27 ft long AND 7 ft tall can't park on a public street 2am–6am, or within 50 ft
  of an intersection at any time. Temporary Overnight RV Permit (TORVP) is the legal workaround:
  $1.50 per 24-hour permit, up to 3 consecutive days per permit, max 72 permits per address per
  year; apply online with proof of residency. https://www.sandiego.gov/parking/permits/torvp
- **Street sweeping.** ~90% of swept blocks have no posted "no parking" sign and aren't ticketed
  for sweeping itself; ~9–10% (parts of Downtown, Mission Beach, Ocean Beach, La Jolla, North
  Park) post signs with day/time, and cars there can be ticketed during the posted window. Look
  up the schedule and sign status on the interactive street sweeping map.
  https://www.sandiego.gov/streetsweeping
- **Abandoned vehicles.** Illegal to leave a vehicle (operable or not) parked over 72 consecutive
  hours without moving it at least 1/10 mile. Report online via Get It Done or call SDPD Vehicle
  Abatement at 858-495-7856; the abandoned-vehicles page itself currently warns response can run
  several weeks behind. https://www.sandiego.gov/police/services/abandoned-vehicles
- **Transit parking (referral, not a City function).** MTS (San Diego Metropolitan Transit
  System) runs free park-and-ride lots at several trolley/bus stations (e.g., Iris Ave 192
  spaces, Beyer Blvd 131, 24th St 156); station parking is capped at 24 hours and there's no
  overnight RV/camper parking. MTS is a separate regional public agency, not a City department.
  https://www.sdmts.com/transit-services/transit-station-parking

## Utilities

- **MyWaterSD.** Self-service portal/app for bills, autopay, paperless billing, and usage
  history: `sandiego.gov/public-utilities/customer-support/mywatersd`. Paying from a linked bank
  account is free; card payment carries roughly a 1.59% fee (estimate, already in `general.md`).
- **Start / stop / move.** Start service online at `water.sandiego.gov/s/movein` or call
  619-515-3500 (M–F 7:30am–5pm) — up to 10 business days to process, though existing service
  generally isn't interrupted while a request is pending. Stop/move-out at
  `water.sandiego.gov/s/moveout` — up to 7 business days; final bill uses an estimated read based
  on historical usage. https://www.sandiego.gov/public-utilities/customer-support/start-service ,
  .../stop-service
- **Rates (effective Jan 1, 2026).** Standard 3/4" residential meter base fee $35.53/month, plus
  tiered usage: $8.51/HCF for the first 10 HCF, $9.50/HCF for the next 12 (11–22), $11.89/HCF
  above 22 HCF (1 HCF = 748.05 gallons ≈ 100 cubic ft). Multi-family flat $9.96/HCF. Rates rose
  ~14.7% on Jan 1 2026 as year one of a four-year increase plan (per secondary reporting; treat
  the multi-year trajectory as approximate). Sewer rate wasn't itemized on the fetched rate page.
  https://www.sandiego.gov/public-utilities/customer-support/water-billing-rates
- **Leaks / sewer emergencies.** Single 24/7 Water and Sewer Emergency Line, 619-515-3525, covers
  both a leak on the City's side of the meter (the street-facing side) and a sewer backup/spill;
  already the number `general.md` gives for leaks, utilities.md adds the sewer-backup case.
  https://www.sandiego.gov/sites/default/files/legacy/water/pdf/operations/emergency.pdf
- **Trash fee is not a utilities bill.** Measure B's residential trash fee bills through the
  county property tax bill (as an "SD Solid Waste Mgmt Fee" line item, roughly half the annual
  amount on each of the two installments), not through MyWaterSD — worth stating explicitly since
  residents look for it on the water bill. https://www.sandiego.gov/environmental-services/trash-service-updates/measure-b
- **Gas / electric.** Referred to SDG&E — already a referral row in `referrals.json`.
- **Low-income help.** H2O SD program: up to a $100/year water-bill credit for qualifying
  low-income households, `sandiego.gov/H2Osd` (estimate on amount/duration — City-run credit
  program, distinct from the federally funded LIHWAP that pays overdue balances up to $2,000
  through county-designated providers, which utilities.md treats as a referral-style mention
  rather than a new referral row since it isn't a standing local agency).

## Housing

- **STRO (Short-Term Residential Occupancy) — four tiers**, `sandiego.gov/stro` /
  `sandiego.gov/treasurer/short-term-residential-occupancy`:
  - Tier 1 (part-time, ≤20 days/yr, host need not be on-site): $33 application + $193 license.
  - Tier 2 (home-sharing, host resides on-site, may be away ≤90 days/yr): $33 + $284.
  - Tier 3 (whole-home, >20 days/yr, City-wide excl. Mission Beach, capped at 1% of housing
    stock, 90-day minimum annual use to keep the license, quarterly reports required): $41 +
    $1,129.
  - Tier 4 (whole-home, Mission Beach Community Planning Area only, same terms as Tier 3):
    $41 + $1,129; application window was closed as of the fetched page.
  - 2-night minimum stay for Tier 3/4. One license per host, one dwelling unit at a time, not
    transferable. A Transient Occupancy Tax (TOT) certificate is required; the page didn't state
    the TOT rate itself, so `housing.md` doesn't invent one. Apply via the Accela Citizen Portal.
  - `business.md` already has an Airbnb/STRO FAQ from M1-era research; housing.md's STRO entries
    extend it with the tier/fee detail rather than restating a competing summary.
- **ADU / JADU**, Information Bulletin 400: ADU up to 1,200 sq ft (conversions of an existing
  structure are exempt from that cap), min 150 sq ft; JADU 150–500 sq ft carved out of an
  existing house or attached garage. A Building Permit is always required (no exemption).
  No parking required for most ADUs outside the Coastal Overlay Zone; JADUs never require
  parking. Plan check for a standard ADU is roughly 4–8 weeks (estimate from `permits.md`-style
  general guidance); pre-approved plan sets get an expedited ~30-day track.
  https://www.sandiego.gov/development-services/forms-publications/information-bulletins/400
- **Tenant resources (referral-heavy).** California's statewide rent cap limits most increases
  to 5% + local inflation or 10%, whichever is lower (San Diego's applicable cap was reported
  around 8.8% for the 2025–26 cycle — estimate, state law text controls). Notice requirements:
  30 days for an increase under 10% in 12 months, 90 days for 10%+ . The City doesn't adjudicate
  landlord-tenant disputes; Legal Aid Society of San Diego and the County-listed rental-assistance
  directory are the referral. New referral row added.
- **San Diego Housing Commission (SDHC)** — a separate public agency from the City (own
  referral row): runs the federal Section 8 Housing Choice Voucher program (16,000+ households),
  a Hardship Application for short-term relief, and (as of Feb 16 2026) has discontinued its
  Security Deposit Loan Assistance program as a cost-saving measure — housing.md notes the
  program exists rather than promising a specific still-open benefit. sdhc.org
- **Homelessness outreach.** City-run (not a referral): Homelessness Response Center ("the
  Hub") does system navigation and housing-application help; Coordinated Street Outreach
  (People Assisting the Homeless / PATH) and Bridge Shelter outreach (Alpha Project, Father
  Joe's Villages) are the field teams. SDHC's HOUSING FIRST – SAN DIEGO hotline, 619-578-7768,
  is the number to give a resident asking for help tonight.
  https://www.sandiego.gov/homelessness-strategies-and-solutions/services/outreach

## Referral rows added to `referrals.json`

Reused existing rows (no duplicate added): SDG&E (gas/electric), County Animal Services /
Humane Society (dog licensing), DMV (vehicle registration). New rows: **MTS** (transit station
parking, a regional agency separate from the City), **San Diego Housing Commission** (rental
assistance / Section 8, separate public agency), **Legal Aid Society of San Diego** (tenant
rights / rent-increase / eviction questions, a nonprofit, not a City function).

## What's approximate / not independently verified

- Water rate figures, meter rate figures, and STRO fees came back from an AI page-summary tool
  (WebFetch), not a raw HTML diff against the PDF rate schedule — spot-checked against a second
  independent source where one was found (multi-year rate trajectory), otherwise taken as stated.
- The multi-year water rate trajectory (14.5%/11.5%/11% in 2027–2029) is third-party reporting,
  not a City page; not repeated as a KB fact, only noted here for context.
- Sewer rate was not found on the fetched rate page; `utilities.md` doesn't claim a sewer number.
- TOT rate for STRO wasn't stated on the fetched STRO page; `housing.md` says a certificate is
  required without inventing a percentage.
