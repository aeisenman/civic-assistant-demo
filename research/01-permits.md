# City of San Diego — Building Permits & Permit Status Inquiries

Research notes on how the City of San Diego's Development Services Department (DSD) handles
building permits and permit status inquiries. Sourced from sandiego.gov where possible; gaps are
filled with clearly labeled best-guess estimates realistic for a mid-size US city permitting agency.

---

## 1. Department overview and entry points

The **Development Services Department (DSD)** is San Diego's permitting, plan check, inspection,
and code-enforcement agency — the local equivalent of a "building department." It handles
building, electrical, plumbing, mechanical, grading, sign, demolition, and land-development
approvals for private property citywide.

Key resident/business-facing entry points:

- **Development Services home** — https://www.sandiego.gov/development-services — main landing
  page with links to permits, forms, bulletins, zoning, and records.
- **Permits and Approvals** — https://www.sandiego.gov/development-services/permits — permit-type
  directory (building, demo, grading, electrical, mechanical, plumbing/gas, fire, sign, solar,
  ROW, temporary-use, noise).
- **Permits, Approvals & Inspections hub** — https://www.sandiego.gov/development-services/permits-inspections
- **Permit Processing Timeline** — https://www.sandiego.gov/development-services/permits/timeline —
  weekly-updated queue/review/issuance estimates by permit type.
- **Permitting Center Dashboard** — https://www.sandiego.gov/development-services/permits-inspections/dashboard —
  applications received, permits issued, inspections/day, code-enforcement case counts, by
  permit category (Overall / Construction / Residential / ADU-JADU).
- **Online Permits portal (Accela Citizen Access)** — https://aca.accela.com/SANDIEGO/ (also
  aca-prod.accela.com/SANDIEGO) — where applicants create an account, submit applications,
  upload plans, pay fees, message reviewers, and check status. All *new* permits/approvals must
  be submitted here.
- **OpenDSD** — https://opendsd.sandiego.gov/web/approvals/ — public permit/approval search and
  open-data portal; covers legacy "PTS" projects submitted 2003–Jan 16 2018 (post-2018 records
  live in Accela). Backed by the city's Open Data Portal for bulk/filterable permit activity data.
- **Permit Activity Reports** — https://www.sandiego.gov/development-services/records/permit-activity-reports
- **Forms, Publications & Information Bulletins ("IB" series)** — the authoritative how-to/rules
  library, e.g. IB-203 (No-Plan Building Permit), IB-501 (Fee Schedule), IB-101 (Building
  Valuation), IB-111 (Signs), IB-140 (Residential additions), IB-142 (Garage conversions),
  IB-150 (Office TI professional certification), IB-211 (Decks), IB-301 (Solar PV), IB-580
  (Historical resource review), IB-610 (Project Issue Resolution).
- **Permits FAQs** — https://www.sandiego.gov/development-services/permits/faqs
- **Support line** — 619-446-5000 (account/upload help); Building & Land Use Code Enforcement —
  619-236-5500.

**Best guess (unverified):** a "Project Status Request" web form exists for cases where a
customer cannot find their project in the portal and needs staff to manually look it up — this
is common practice at comparable agencies (referenced obliquely in search results but the live
form URL could not be confirmed).

---

## 2. Permit types that matter most to residents/small businesses

| Permit type | What it covers | Plan review? | Typical fee (residential/small scale) | Typical turnaround |
|---|---|---|---|---|
| **Simple Permit** (IB/portal: "Simple MEP") | Minor residential mechanical/electrical/plumbing: forced-air/AC swap, exhaust fan, furnace replacement, meter reset, circuit addition, EV charger in a private garage, water-heater swap (non-tankless), gas-line/drain repair | No plan review | Low (roughly $100–$300 per trade; combo jobs bundle) | Licensed contractor: instant on payment. Owner-builder: ~2 business days (after signed DS-3042) |
| **No-Plan Building Permit** | Like-for-like repair/replacement on a legally-permitted, already-finaled structure: door/window replacement (same size/type), kitchen/bath remodel with no structural change, re-stucco, siding, drywall repair, damage repair-in-kind | No formal plan review, but may require a pre-construction/historic inspection | Combo (plumb+mech+elec) IB-203 job ≈ **$411.02**; single-trade permits ~$115–$165 each (plumbing $115, electrical/mechanical $165, per search-result estimates) | Historic/eligibility review ~10 business days, then issuance |
| **Building Permit — with plans** | Additions, remodels, ADUs, new structures, structural work | Full plan check | Fee = valuation-based (see §3) + plan-check (~65–85% of permit fee depending on project type) | Building permit issuance queue ~1 business day once approved; full plan-check cycle 4–8+ weeks depending on complexity and revision cycles |
| **ADU (Accessory Dwelling Unit)** | Detached/attached ADU or JADU | Standard plans (pre-approved) get ministerial ~30-day target review; custom plans 60–90 days | Total permit + impact fees commonly **$6,000–$20,000** (avg ~$10k–$15k); units **under 750 sq ft are exempt from development impact fees**; plan-check fee ≈ 65% of building permit fee | End-to-end (submit → final inspection) commonly **3–5 months** for standard-plan ADUs, up to 6–12 months for custom detached units *(best-guess range synthesized from multiple secondary sources; not confirmed on sandiego.gov directly)* |
| **Solar Photovoltaic (residential)** | Rooftop PV ≤ 38.4 kW AC on single-family/duplex, no fire or structural review needed | **SolarApp+** instant/automated self-certification pathway (adopted 2022) for qualifying systems; manual plan check otherwise | ~$150–$500 *(best-guess range from secondary sources)* | Qualifying systems: **1–5 business days** via SolarApp+; non-qualifying manual review: **10–21 business days** |
| **Tenant Improvement (commercial interior)** | Non-structural interior alteration to existing commercial/industrial space | Building Permit with Plans; standard commercial plan review | Valuation-based, per IB-501 | Standard: **4–8 weeks**. Qualifying **Office TI Professional Certification** (IB-150) — buildings <20,000 sq ft, no changes to plumbing fixtures/openings/stairs/occupancy, design professional self-certifies — issuance in **as little as 7 days, often same-day** |
| **Sign Permit** | Installation/alteration of signs on private property | Review of vicinity map, dimensions, setbacks, ROW distance; electrical/high-rise/freeway signs also need inspection | Varies by sign type (IB-501/IB-111); not itemized in public search results | Listed on the Timeline dashboard at ~2 business days for issuance queue |
| **Grading Permit** | Earthwork/topography changes | Plan review | Valuation/quantity based | ~2 business days issuance queue (per Timeline dashboard) |
| **Demolition/Removal** | Full structure demolition (partial demo needs a Building Permit with plans) | Limited review | Modest flat/valuation fee | ~3 business days issuance queue |

Sources: https://www.sandiego.gov/development-services/permits ,
https://www.sandiego.gov/development-services/forms-publications/information-bulletins/203 ,
https://www.sandiego.gov/development-services/permits/simple-permits ,
https://www.sandiego.gov/development-services/permits/timeline ,
https://www.sandiego.gov/development-services/news-programs/sbep ,
https://www.sandiego.gov/development-services/forms-publications/information-bulletins/301 ,
https://www.sandiego.gov/development-services/forms-publications/information-bulletin/150 ,
https://www.sandiego.gov/development-services/forms-publications/information-bulletins/501 ,
https://www.insidesandiego.org/city-san-diego-initiates-new-instant-permit-program-residential-solar

---

## 3. End-to-end workflow (numbered)

1. **Determine if a permit is required / select permit type.** Applicant reviews "When is a
   Permit Required" guidance and picks a track: Simple Permit, No-Plan Permit, or Building Permit
   with Plans (incl. ADU, TI, solar, sign, grading, demo). *Owner: applicant.*
2. **Create/log in to an Online Permits (Accela Citizen Access) account.** Required for essentially
   all new submittals since the portal went cloud-based. *Owner: applicant; System: Accela ACA.*
3. **Complete and attach the General Application, Form DS-3032**, plus any supplemental forms
   for the specific track (see §4 for exact fields). Common companions:
   - **DS-345** — Project/Contacts form (identifies all parties: owner, applicant, contractor,
     design professional, agent).
   - **DS-3042** — Owner-Builder Verification form (required whenever an owner self-certifies as
     exempt from contractor licensing, e.g., Simple/No-Plan permits for homeowners).
   - **DS-6005** — No-Plan Building Permit Supplemental Application.
   - **DS-117** — Permit extension request (used later, before a permit's 1/3/4-year expiration).
   *Owner: applicant.*
4. **Upload plans/drawings and supporting documents** (site plan, structural calcs, Title-24
   energy compliance, elevations, historical-resource info if the structure is 45+ years old,
   etc., depending on scope). *Owner: applicant.*
5. **Intake / pre-screen.** DSD staff check the submittal package for completeness (correct
   forms, signatures, required attachments, fee deposit) before it enters the review queue.
   Portal status: **Submitted** → **In Review** (intake). Incomplete packages are kicked back
   before formal review starts. *Owner: DSD intake staff.*
6. **Plan check / review cycle(s).** Multiple disciplines (structural, fire, electrical,
   mechanical, plumbing, planning/zoning, landscape, MHPA/environmental as applicable) review in
   parallel; each discipline issues a "cycle issues report." The applicant cannot resubmit until
   **all** disciplines finish that cycle. Portal status while active: **In Review**; when
   corrections are required: **Issues Identified** (a "Project Issue Resolution" process,
   IB-610, governs how issues get logged and resolved — https://www.sandiego.gov/development-services/forms-publications/information-bulletins/610).
   *Owner: DSD plan reviewers (per discipline).*
7. **Applicant responds to comments.** Applicant revises plans/documents and re-uploads a
   response-to-comments package addressing every open issue; this restarts the review cycle for
   affected disciplines (each additional cycle commonly adds ~2–4 weeks). Repeats until all
   disciplines clear. *Owner: applicant / design professional.*
8. **Approved.** All disciplines sign off; project is cleared for permit issuance pending fees.
   Portal status: **Approved** (sometimes shown as "Ready to Issue"). *Owner: DSD reviewers → system.*
9. **Fee payment / invoice.** Final building permit fee, plan-check fee true-up, and any impact
   fees (e.g., development impact fees, school fees, water/sewer capacity fees — waived under
   750 sq ft for ADUs) are invoiced; applicant pays online through the portal. *Owner: applicant;
   System: Accela payment module / cashier.*
10. **Permit issuance.** Once paid and all conditions are satisfied, the permit is issued and
    becomes the authorization to begin work; a PDF permit card/record is available in the portal.
    Portal status: **Issued**. *Owner: DSD permit-issuance staff → system.*
11. **Construction / inspections.** Applicant/contractor schedules required inspections (footing,
    framing, rough electrical/plumbing/mechanical, etc., depending on scope) through the portal or
    by phone; a City inspector visits the site and records pass/fail per inspection type. A
    pre-construction inspection is also required for some No-Plan/TI-certification permits before
    work starts. Portal status: **Inspections** (with per-inspection sub-results such as
    "Passed," "Failed," "Partial," "Corrections Required"). Work must start within one year and
    inspections must occur at least every 180 days, or the permit lapses. *Owner: applicant
    schedules; City inspector performs and records.*
12. **Final inspection / Finaled.** Once all required inspections pass, including the final,
    the permit closes out. Portal status: **Finaled** (a.k.a. "Closed"/"Complete"). Only
    finaled, legally-permitted structures are eligible for future No-Plan permits — this is a
    call-back into step 1 for future work on the same structure. *Owner: City inspector /
    system.*
13. **(If needed) Extension.** If work stalls, applicant files Form DS-117 at least one month
    before the 1-year work-start deadline or the 3-year (single-family/duplex) / 4-year (all
    other) issuance-to-expiration deadline. *Owner: applicant.*

**Status vocabulary observed/inferred for the portal** (Accela-based systems typically expose a
constrained set of human-readable statuses mapped from internal workflow tasks):
`Submitted` → `In Review` (intake / plan check) → `Issues Identified` (corrections needed,
loops back to `In Review` after resubmittal) → `Approved` / `Ready to Issue` → `Issued` →
`Inspections` (with pass/fail per inspection) → `Finaled` / `Closed`. Additional terminal/side
statuses likely include `Void`, `Withdrawn`, `Expired`, and `On Hold`. **Best guess:** exact
on-screen strings were not directly confirmed from a live Accela DSD screenshot in this research
pass (the ministerial-permit user-guide PDF could not be parsed as text) — the sequence above is
reconstructed from the DSD Timeline page's three-phase model (Intake → Review → Permit Issuance),
the IB-610 Project Issue Resolution bulletin, and standard Accela Citizen Access status
terminology used by other California AHJs.

Sources: https://www.sandiego.gov/development-services/permits/timeline ,
https://www.sandiego.gov/development-services/forms-publications/information-bulletins/610 ,
https://www.sandiego.gov/development-services/permits/faqs ,
https://www.sandiego.gov/development-services/forms-publications/information-bulletins/203 ,
https://aca.accela.com/SANDIEGO/

---

## 4. Exact fields collected — Form DS-3032, "General Application"

Confirmed directly from the official PDF
(https://www.sandiego.gov/sites/default/files/legacy/development-services/pdf/industry/forms/ds3032.pdf).
This is the universal cover-sheet form DSD uses across almost all permit/approval types; it has
two parts.

**Part I — required for all permits/approvals:**

1. **Approval Type** (checkboxes): Electrical/Plumbing/Mechanical, Sign, Building, Grading,
   Public Right-of-Way, Public Right-of-Way Small Cell Wireless Facility, Subdivision,
   Demolition/Removal, Development Approval, Vesting Tentative Map, Tentative Map, Map Waiver,
   Other (free text).
2. **Project Address/Location** (incl. building/suite no.), **Project Title**, **Project No.**
   (city-assigned, for city use only), **Legal Description** (lot/block/subdivision name/map
   number), **Assessor's Parcel Number (APN)**.
3. **Existing Use** and **Proposed Use** (checkboxes): House/Duplex/Townhouse,
   Condominium/Apartment, Commercial/Non-Residential, Vacant Land.
4. **Project Description** (free text).
5. **Property Owner**: Name, Telephone, Address, City, State, Zip, Email.
6. **Permit Holder** (may differ from owner — the party responsible for scheduling inspections,
   receiving failed-inspection/expiration/revocation notices, and who can cancel the approval):
   Name, Telephone, Address, City, State, Zip, Email.
7. **Licensed Design Professional** (if required): Architect or Engineer checkbox, License No.,
   Name, Telephone, Address, City, State, Zip, Email.
8. **Historical Resource Information**: (a) Is there a designated historic resource on-site or in
   a historic district — Yes/No; (b) year constructed for all structures on site (triggers
   supplemental review if any structure is 45+ years old).
9. **Active Code Enforcement Case**: Yes/No; if yes — is this application related to the
   violation (Yes/No), and will it resolve the violation (Yes/No).
10. **Applicant**: role checkbox (Property Owner / Authorized Agent of Property Owner / Other
    Person), Name, Telephone, Address, City, State, Zip, Email, **signature and date** (perjury
    / certification statement, authorization for City to enter property for inspection).

**Part II — required for all Construction Permits except Grading and Public Right-of-Way:**

11. **Contractor**: Name, Telephone, Address, City, State, Zip, Email, **State License No.**,
    **License Class**, Licensed Contractor's Declaration (perjury statement of active license),
    print name/signature/date.
12. **Worker's Compensation Declaration** (perjury statement, pick one): (a) certificate of
    self-insurance, (b) has workers' comp insurance — Insurance Carrier, Policy No., Expiration
    Date, Agent Name, Agent Phone; (c) certifies no employees subject to workers' comp law.
    Print name/signature/date.
13. **Owner-Builder Declaration** (perjury statement, pick basis of exemption from contractor
    licensing): (a) owner or owner's employees will do all/portion of work, not for sale;
    (b) owner exclusively contracting with licensed contractors; (c) other stated exemption
    reason (free text). Print name/signature/date. Notes a **separate Owner-Builder Verification
    form DS-3042** must also be signed.
14. **Construction Lending Agency**: Lender's Name, Lender's Address (per Civil Code §3097).

**Best-guess additional fields likely captured elsewhere in the full submittal package** (not on
DS-3032 itself, but standard for a valuation-based building permit and useful for an extraction
schema): **Project valuation / estimated cost of construction** (drives the permit fee per
IB-501/IB-101 building-valuation tables), **square footage** (existing / proposed / addition),
**number of stories**, **occupancy type / construction type** (building-code classifications),
**number of dwelling units added/removed**, **zoning designation**, **flood zone / coastal zone
overlay flags**, **scope-of-work checklist** (structural / electrical / mechanical / plumbing /
grading / demo — mirrors the DS-3032 approval-type checkboxes but at line-item detail),
**plan sheet count / drawing index**, **Title-24 energy compliance documentation reference**.
These are inferred from the fee-schedule and valuation-bulletin structure (IB-501, IB-101) and
from what any Accela-based AHJ typically collects, not lifted verbatim from a second source PDF.

Related supplemental forms (name + purpose, useful for the extraction schema's "form type"
field): **DS-3032** General Application (cover sheet), **DS-345** Project Contacts, **DS-3042**
Owner-Builder Verification, **DS-6005** No-Plan Building Permit Supplemental Application,
**DS-117** Permit Extension Request.

Sources: DS-3032 PDF (fetched and parsed directly) —
https://www.sandiego.gov/sites/default/files/legacy/development-services/pdf/industry/forms/ds3032.pdf ,
https://www.sandiego.gov/development-services/forms-publications/information-bulletins/203 ,
https://www.sandiego.gov/development-services/forms-publications/information-bulletins/501 ,
https://www.sandiego.gov/development-services/forms-publications/information-bulletins/101

---

## 5. Top 15 resident FAQs (for a RAG knowledge base)

1. **Q: Do I need a permit to remodel my kitchen or bathroom?**
   A: If you're not changing structural framing, you likely qualify for a **No-Plan Building
   Permit** (no formal plan review). If you're moving walls, adding square footage, or changing
   plumbing/electrical layout significantly, you'll need a **Building Permit with Plans**.
   (IB-203)

2. **Q: How do I check the status of my permit application?**
   A: Log in to the DSD **Online Permits (Accela Citizen Access)** portal at
   aca.accela.com/SANDIEGO with your record number. Permits submitted before Jan 16, 2018 are
   searchable in **OpenDSD** (opendsd.sandiego.gov) instead. Status will show as Submitted, In
   Review, Issues Identified, Approved, Issued, Inspections, or Finaled depending on stage.

3. **Q: What does "Issues Identified" mean on my permit status?**
   A: It means one or more plan-review disciplines (structural, fire, electrical, etc.) found
   corrections needed. You'll receive a cycle issues report; you must address **all** open items
   across every discipline before you can resubmit revised plans. See IB-610 (Project Issue
   Resolution).

4. **Q: How long does it take to get a building permit in San Diego?**
   A: It depends heavily on permit type and completeness of your submittal. Simple/No-Plan
   permits: days. Solar (qualifying, via SolarApp+): 1–5 business days. Office TI with
   professional certification: as fast as same-day, typically within 7 days. Standard building
   permits with plans: commonly 4–8+ weeks for commercial TI, and 3–5 months (or longer for
   custom designs) for ADUs. Check the live **Permit Processing Timeline** dashboard for current
   queue estimates by type.

5. **Q: What is the fee for a building permit?**
   A: Fees are largely valuation-based (roughly $4 per $100,000 of construction value for
   inspection fees, per IB-501, plus a plan-check fee that is a percentage of the permit fee —
   commonly around 65% for many project types) and vary by permit type. See IB-501 (Fee Schedule
   for Construction Permits) and IB-101 (Building Valuation) for the current tables.

6. **Q: Can I pull my own permit as a homeowner instead of hiring a licensed contractor?**
   A: Yes, as an "Owner-Builder." You must sign the Owner-Builder Declaration on the DS-3032 and
   complete a separate **Owner-Builder Verification Form (DS-3042)**. Be aware you generally
   cannot sell a structure you built yourself as an owner-builder within one year unless it was
   your primary residence.

7. **Q: How long is a building permit valid, and can I extend it?**
   A: Permits expire 3 years after issuance for single-family homes/duplexes, 4 years for
   everything else; work must start within 1 year and pass an inspection at least every 180
   days. To extend, submit **Form DS-117** at least one month before expiration.

8. **Q: Do I need a permit for solar panels?**
   A: Yes, but qualifying residential systems (≤38.4 kW AC on a single-family home/duplex, no
   fire or structural review needed) can use **SolarApp+**, an instant self-certification
   pathway that can issue a permit in 1–5 business days instead of the standard 10–21 day manual
   review.

9. **Q: What's the difference between a "Simple Permit" and a "No-Plan Permit"?**
   A: Simple Permits cover minor, single-trade MEP work (e.g., water heater swap, circuit
   addition, AC unit replacement) with no plan review at all — often issued instantly to
   licensed contractors. No-Plan Building Permits cover like-for-like repair/replacement work on
   an already-finaled structure (e.g., re-stucco, in-kind drywall repair) and can require a
   historic/pre-construction check (~10 business days).

10. **Q: My house/building is more than 45 years old — does that affect my permit?**
    A: It may. Structures 45 years or older can trigger a **Potential Historical Resource
    Review** (IB-580) and additional supplemental submittal requirements, so you'll need to
    answer the historical-resource questions on the DS-3032 accurately.

11. **Q: I'm building an ADU — how much does it cost and how long does it take?**
    A: Total permit and impact fees commonly run **$6,000–$20,000** depending on size/location;
    ADUs under 750 sq ft are exempt from development impact fees. End-to-end timelines are
    commonly **3–5 months** for standard, pre-approved plan designs and can extend to 6–12
    months for custom detached ADUs.

12. **Q: Do I need a permit to put up a sign for my business?**
    A: Yes, a **Sign Permit** is required for installing or altering most signs on private
    property. You'll need a vicinity map, sign/property dimensions, and setback distances.
    Electrical, high-rise, and freeway signs also require an inspection.

13. **Q: What happens after my permit is "Issued" — do I need more inspections?**
    A: Yes. You (or your contractor) schedule required inspections through the portal as
    construction proceeds (e.g., footing, framing, rough MEP). Each inspection is recorded
    pass/fail. Once all required inspections — including the final — pass, the permit status
    becomes **Finaled**.

14. **Q: I have an active code enforcement case on my property — can I still get a permit?**
    A: Yes, you can still apply; the DS-3032 requires you to disclose the case and state whether
    your application relates to, or will resolve, the violation. Contact Code Enforcement at
    619-236-5500 with case-specific questions.

15. **Q: Who do I contact if I can't find my project in the portal or need help?**
    A: Call DSD's general support line at **619-446-5000** for account and document-upload
    help, or use the appropriate **Project Status Request** channel referenced on the Permits
    FAQ page for staff to manually look up your project. *(Exact self-service form URL not
    independently confirmed in this research pass — best guess based on secondary references.)*

Sources: https://www.sandiego.gov/development-services/permits/faqs ,
https://www.sandiego.gov/development-services/forms-publications/information-bulletins/203 ,
https://www.sandiego.gov/development-services/forms-publications/information-bulletins/610 ,
https://www.sandiego.gov/development-services/permits/timeline ,
https://www.sandiego.gov/development-services/news-programs/sbep ,
https://www.sandiego.gov/development-services/forms-publications/information-bulletin/150

---

## 6. Backend automation opportunities (document intake + LLM workflow)

- **Form/field extraction from uploaded PDFs.** Auto-extract every DS-3032 field (approval
  type, project address, APN, legal description, existing/proposed use, project description,
  owner/permit-holder/contractor/design-professional contact blocks, license numbers, historic
  and code-enforcement disclosure answers) plus valuation and square footage from attached plans
  — replacing manual data entry at intake.
- **Completeness / pre-screen check.** Before a submittal enters the human review queue, an LLM
  workflow can validate that required fields are non-empty, that the right supplemental forms
  are attached for the selected approval type (e.g., DS-3042 present when Owner-Builder is
  checked, DS-6005 present for No-Plan Building Permits), that signatures/dates are present, and
  that a contractor license number is provided when a licensed-contractor declaration is
  checked — flagging missing items back to the applicant instead of consuming reviewer queue
  time. This directly automates the "Intake / pre-screen" step (§3, step 5).
- **Routing to the correct reviewer/discipline.** Based on extracted approval type and scope-of-
  work checkboxes, auto-route the submittal to the applicable review disciplines (structural,
  fire, electrical, mechanical, plumbing, planning/zoning, historical resources) and flag
  cross-discipline dependencies (e.g., historic-district flag → route to historical resource
  review; active code-enforcement flag → notify Code Enforcement liaison).
- **Fee estimation.** Using extracted valuation, permit type, and square footage against the
  IB-501/IB-101 fee tables, generate an instant fee estimate for the applicant at submission
  time, rather than waiting for a manual invoice — reducing surprise costs and payment-stage
  delays (§3, step 9).
- **Eligibility triage for expedited pathways.** Auto-detect whether a project qualifies for
  SolarApp+ (solar), Simple Permit, No-Plan Permit, or Office TI Professional Certification
  based on extracted scope/size/occupancy data, and route qualifying projects to the fast track
  automatically instead of the standard queue.
- **Issues-identified summarization and applicant-facing plain-language comments.** When
  reviewers log corrections, an LLM can consolidate multi-discipline cycle-issue reports into a
  single, plain-language checklist for the applicant (what changed is required, which
  form/sheet it applies to), reducing back-and-forth cycles (§3, step 6–7).
- **Status-change notifications.** Automated emails/SMS/portal notices triggered on each status
  transition (Submitted → In Review → Issues Identified → Approved → Issued → Inspections →
  Finaled), including reminders ahead of the 180-day inspection requirement and the 1-year
  work-start / 3–4 year expiration deadlines (tie-in to Form DS-117 extension nudges).
- **Inspection scheduling assistant.** Given permit type and current construction stage, suggest
  which inspection to schedule next and surface any prerequisite inspections that must pass
  first.
- **FAQ/RAG chatbot.** Use the top-15 FAQ set (§5) plus the Information Bulletins as a grounded
  knowledge base to answer resident questions about permit requirements, fees, and timelines
  before they call 619-446-5000, deflecting routine inquiries from staff.
- **Anomaly/fraud flags.** Cross-check contractor license numbers and workers'-comp declarations
  against state license lookups, and flag inconsistent owner-builder claims (e.g., "not intended
  for sale" declared on a property with a recent sale-listing history) for staff review.

Sources synthesized from process steps documented above; automation framing is original analysis,
not sourced from a specific sandiego.gov automation roadmap document (none found publicly).

---

*Research compiled 2026-09-02. Where a claim could not be verified against an official
sandiego.gov / Accela page directly (e.g., exact on-screen Accela status strings, some fee
figures, ADU end-to-end timeline ranges), it is marked "best guess" inline and drawn from
secondary sources (permit-consulting sites, ADU-industry blogs) rather than the City itself.*
