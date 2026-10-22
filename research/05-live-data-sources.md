# Live Data Sources — Real San Diego Government Data for Tool Calls
Researched 2026-09-05. All requests below were run live with `curl -m 20`. VERIFIED = got a real JSON/CSV response (sample pasted). DEAD = confirmed no public unauthenticated access. UNVERIFIED = endpoint is alive but I could not get a working query in the time available.

## Summary Table
| Source | What it answers | Protocol | Auth | Freshness | Verified? | Example URL |
|---|---|---|---|---|---|---|
| City ArcGIS — Council Districts (`DoIT_Public/DoIT_Public` layer 5) | Council district boundary, member name/phone/site | REST/JSON (ArcGIS FeatureServer query) | None | Static (redistricting cadence) | VERIFIED | `.../DoIT_Public/DoIT_Public/MapServer/5/query?where=1=1&outFields=DISTRICT,NAME,PHONE,WEBSITE&f=json` |
| City ArcGIS — Street Sweeping Route (`GeoSweep/GeoSweep_Dynamic` layer 13) | Sweeping day/schedule by street + address range | REST/JSON | None | Live (city ops layer) | VERIFIED | `.../GeoSweep_Dynamic/MapServer/13/query?where=RD20FULL='C ST'&outFields=*&f=json` |
| City ArcGIS — Zoning (`DSD/Zoning_Base` layer 0) | Zone (e.g. CCPD-CORE) at a point/address | REST/JSON | None | Static-ish (ordinance-driven) | VERIFIED | `.../Zoning_Base/MapServer/0/query?geometry=x,y&geometryType=esriGeometryPoint&f=json` |
| City ArcGIS — Permit Approvals (`DoIT_Public/DSDPermits` layer 0) | Real permit status by address (Accela-sourced) | REST/JSON | None | Live | VERIFIED | `.../DSDPermits/MapServer/0/query?where=GIS_ADDRESS LIKE '%X%'&outFields=*&f=json` |
| City ArcGIS — Geocoder (`Locators/StreetAddress`) | Address → lat/lng, score 100 on exact match | REST/JSON | None | Static | VERIFIED | `.../Locators/StreetAddress/GeocodeServer/findAddressCandidates?Address=202 C ST&f=json` |
| City ArcGIS — STRO Active Licenses (`Treasurer/STRO_ACTIVE_LICENSES`) | Active short-term rental licenses by address | REST/JSON | None | Live | VERIFIED | `.../STRO_ACTIVE_LICENSES/MapServer/0/query?where=1=1&outFields=*&f=json` |
| data.sandiego.gov / seshat — Get It Done Reports | Bulk export of all 311-style service requests incl. status | CSV bulk (daily) | None | Daily | VERIFIED | `https://seshat.datasd.org/get_it_done_reports/get_it_done_requests_open_datasd.csv` |
| data.sandiego.gov / seshat — Development Permits | Bulk export of DSD project/approval records | CSV bulk (daily) | None | Daily | VERIFIED | `https://seshat.datasd.org/development_permits/approvals_active_datasd.csv` |
| data.sandiego.gov / seshat — Business Tax Certificates | Active/inactive business registry by address | CSV bulk (daily) | None | Daily | VERIFIED | `https://seshat.datasd.org/business_tax_certificates/sd_businesses_active_datasd.csv` |
| data.sandiego.gov / seshat — Special Events | Citywide events list (farmers markets, festivals) | CSV bulk | None | **STALE** (last-modified 2023, rows dated 2021) | VERIFIED but stale | `https://seshat.datasd.org/special_events/special_events_list_datasd.csv` |
| data.sandiego.gov / seshat — Street Sweeping Schedule | Same data as ArcGIS GeoSweep, as flat CSV/GeoJSON | CSV/GeoJSON bulk | None | Daily-ish | VERIFIED | `https://seshat.datasd.org/gis_street_sweeping/street_sweeping_datasd.csv` |
| data.sandiego.gov / seshat — Parking Meters & Citations | Meter locations/rates, citation history | CSV bulk | None | Periodic | VERIFIED | `https://seshat.datasd.org/parking_meters_locations/treas_parking_meters_loc_datasd.csv` |
| SANDAG regional GIS — Council Districts / Library Locations / Address Points | Region-wide (multi-jurisdiction) copies of same layers | REST/JSON (FeatureServer) + CSV/GeoJSON | None | Periodic | VERIFIED | `https://geo.sandag.org/server/rest/services/Hosted/Library/FeatureServer/0/query?where=district='San Diego Public (City)'&f=json` |
| OpenDSD API | Legacy PTS permit/approval/invoice/code-enforcement records by numeric ID | REST/JSON or XML | None (IP rate-limited: 20 req/200ms) | Static/historical (pre-Accela) | VERIFIED | `https://opendsd.sandiego.gov/api/project/294761` (send `Accept: application/json`, follow redirect) |
| Granicus (Council meeting agendas) | Upcoming/past council meeting agendas | RSS/XML | None | Live | VERIFIED | `https://sandiego.granicus.com/ViewPublisherRSS.php?view_id=3&mode=agendas` |
| sandiego.gov trash holiday schedule page | 2026 no-collection holidays + shift rule | HTML (scrape, not an API) | None | Annual | VERIFIED | `https://www.sandiego.gov/environmental-services/collection/schedule` |
| Accela Citizen Access (ACA) | Live permit/case status lookup UI | — | Session/UI only | — | DEAD (no public JSON) | `https://aca-prod.accela.com/SANDIEGO/` |
| County SanGIS — ADDRAPN Geocoder | County-wide address→APN geocoding | REST/JSON | None | — | UNVERIFIED (endpoint live, 0 candidates for both incorporated-SD and unincorporated test addresses in my session) | `https://gis-public.sandiegocounty.gov/arcgis/rest/services/ADDRAPN/GeocodeServer` |
| County SanGIS — DEH beach water quality | Beach closures/water quality advisories | — | — | — | DEAD in this pass (DEH folder exposes only an empty `SiteMapStoredReports` MapServer; no beach-water-quality service found under DEH/PDS/rov) | `https://gis-public.sandiegocounty.gov/arcgis/rest/services/DEH` |
| SANDAG opendata hub item `82495eb2e74348f9a1ff104d5d545c12` ("Trash Collection Routes") | — | — | — | — | DEAD / mislabeled — this item resolves to **Santa Monica's** `gis.santamonica.gov` trash service, not San Diego. Use the seshat/ArcGIS street-sweeping sources above instead. | `https://www.arcgis.com/sharing/rest/content/items/82495eb2e74348f9a1ff104d5d545c12` |
| Get It Done live submission/case-status API | Submitting or looking up a single case in real time | — | — | — | No public API found (site is a JS app shell; only the daily bulk CSV export is public) | `https://getitdone.sandiego.gov/` |

## City ArcGIS server — details

### Council districts
`GET https://webmaps.sandiego.gov/arcgis/rest/services/DoIT_Public/DoIT_Public/MapServer/5/query?where=1=1&outFields=DISTRICT,NAME,PHONE,WEBSITE&returnGeometry=false&f=json`
```json
{"attributes":{"DISTRICT":2,"NAME":"Jennifer Campbell","PHONE":"(619) 236-6622","WEBSITE":"http://www.sandiego.gov/citycouncil/cd2"}}
{"attributes":{"DISTRICT":1,"NAME":"Joe LaCava","PHONE":"(619) 236-6611","WEBSITE":"http://www.sandiego.gov/citycouncil/cd1"}}
```
To resolve an address to a district, geocode it (below) then run a point-in-polygon query against layer 5 with `geometry=x,y&geometryType=esriGeometryPoint`. Note: layer 5's boundaries return polygons, so a point query is the pattern; `GIS_COUNCILDISTRICT` is also pre-joined onto the permits layer and `CDCODE` onto the street-sweeping layer, so many address lookups don't need a separate district query at all.

### Street sweeping (real schedule text, not synthetic)
`GET .../GeoSweep/GeoSweep_Dynamic/MapServer/13/query?where=RD20FULL='C ST'&outFields=RD20FULL,LOW_ADDR,HIGH_ADDR,SCHEDULE,POSTED,CDCODE,ZIP&returnGeometry=false&f=json`
```json
{"RD20FULL":"C ST","LOW_ADDR":3940,"HIGH_ADDR":3949,"SCHEDULE":"Not Posted, Both Sides 1st Mon","POSTED":"NP","CDCODE":9,"ZIP":92102}
```
Query by `RD20FULL` (street name) and filter client-side on `LOW_ADDR <= N <= HIGH_ADDR` for a specific address.

### Geocoding (working pattern)
`SingleLine=` on both `DSD/Accela_Locator` and `Locators/StreetAddress` gave wrong/low-score matches for "202 C St, San Diego, CA". The `Address=` field param on `Locators/StreetAddress` gave a perfect match:
`GET .../Locators/StreetAddress/GeocodeServer/findAddressCandidates?Address=202 C ST&outFields=*&f=json`
```json
{"address":"202 C ST, 92101","location":{"x":-13042511.4,"y":3857768.1},"score":100,"attributes":{"Addr_type":"StreetAddress"}}
```
(Note: output spatial ref is Web Mercator/3857 — reproject before feeding into Zoning/Council-District point queries which expect matching `inSR`.)

### Zoning by address (point query with the geocoded coordinates)
`GET .../DSD/Zoning_Base/MapServer/0/query?geometry=-13042511.4,3857768.1&geometryType=esriGeometryPoint&inSR=3857&spatialRel=esriSpatialRelIntersects&outFields=*&returnGeometry=false&f=json`
```json
{"ZONE_NAME":"CCPD-CORE","IMP_DATE":1146639600000,"ORDNUM":"O-19471 NS"}
```
(202 C St is City Hall — CCPD-CORE = Centre City Planned District Core, correct.)

### Permit status by address (real, live Accela/PTS data)
`GET .../DoIT_Public/DSDPermits/MapServer/0/query?where=GIS_ADDRESS LIKE '%540 University%'&outFields=*&returnGeometry=false&f=json`
```json
{"APPROVAL_ID":"PMT-3361573","APPROVAL_TYPE":"Traffic Control Permit","APPROVAL_STATUS":"Issued","GIS_ADDRESS":"540 University Av, San Diego, CA","GIS_COUNCILDISTRICT":"3"}
{"APPROVAL_ID":"PMT-3345974","APPROVAL_TYPE":"Plumbing Pmt","APPROVAL_STATUS":"Opened","GIS_ADDRESS":"3432 Park Bl, San Diego, CA","GIS_COUNCILDISTRICT":"3"}
```
`APPROVAL_STATUS` values seen: Issued, Opened (maps loosely onto our `PermitApplication.status` enum but is not identical — needs a mapping table, not a 1:1 match).

### STRO (short-term rental) active licenses
`GET .../Treasurer/STRO_ACTIVE_LICENSES/MapServer/0/query?where=1=1&outFields=*&returnGeometry=false&f=json`
```json
{"LICENSE_ID":"STR-02934L","ADDRESS":"431 San Antonio Av, San Diego, CA 92106","TIER":"Tier 3","COMMUNITY_PLANNING_AREA":"PENINSULA","COUNCIL_DISTRICT":2}
```

## data.sandiego.gov / seshat — details
The dataset catalogue isn't served by data.sandiego.gov itself in a scraped-JS-friendly way; the working list is the City's own inventory JSON on GitHub: `https://raw.githubusercontent.com/COSD-PANDA/data-inventory/refs/heads/master/data.json` (122 datasets, each with `distribution[].downloadURL` pointing at seshat.datasd.org). All URLs below were confirmed with `curl -sI` (200, real `content-length`/`last-modified`) and a header-row sample.

- **Get It Done reports** — `get_it_done_reports/get_it_done_requests_open_datasd.csv` (30MB, updated same-day) — columns: `service_request_id, ..., status, lat, lng, street_address, council_district, comm_plan_name, ...`. Per-council-district files and per-year closed files also exist.
- **Development permits** — `development_permits/approvals_active_datasd.csv` (284MB active file; smaller yearly `approvals_created_2026`/`issued_2026`/`closed_2026` files exist) — columns include `GIS_ADDRESS, APPROVAL_TYPE, APPROVAL_STATUS, APPROVAL_ISSUE_DATE, APPROVAL_VALUATION`.
- **Business Tax Certificates** — `business_tax_certificates/sd_businesses_active_datasd.csv` (19MB) — columns: `account_key, account_status, dba_name, naics_description, address_no...address_zip, council_district, lat, lng`.
- **Street sweeping** — `gis_street_sweeping/street_sweeping_datasd.csv` — same fields as the ArcGIS layer, plus GeoJSON/TopoJSON/shapefile variants.
- **Special events** — `special_events/special_events_list_datasd.csv` — columns `event_title, event_type, date_event_start, date_event_end, address_full, lat, lng`. **Caveat: stale** (2023 last-modified, sample rows dated Dec 2021) — not reliable as a live "what's happening" source without checking freshness first.
- **Parking meters/citations** — `parking_meters_locations/treas_parking_meters_loc_datasd.csv` (rates/zones) and `parking_citations/parking_citations_2026_part{1,2}_datasd.csv`.

## SANDAG regional GIS hub (geo.sandag.org)
Region-wide layers, filterable to City of San Diego via a `where` clause. Useful mainly for **library locations** (address/phone only, no hours) since the City doesn't otherwise publish a machine-readable library dataset:
`GET https://geo.sandag.org/server/rest/services/Hosted/Library/FeatureServer/0/query?where=district='San Diego Public (City)'&outFields=name,address,phone,website&f=json`
```json
{"name":"Balboa","address":"4255 Mt. Abernathy Avenue","phone":"(858) 573-1390","website":"http://www.sandiego.gov/public-library/"}
```
The `82495eb2e74348f9a1ff104d5d545c12` "Trash Collection Routes" item from the original lead list is **not San Diego data** — it resolves to a Santa Monica Public Works feature service. Use the seshat/ArcGIS street-sweeping sources instead.

## OpenDSD API
Base `https://opendsd.sandiego.gov/api/`. Requires `https://` (plain `http://` times out) and `-L` to follow a 302; send `Accept: application/json` or you get XML. Four ID-based endpoints, confirmed live:
- `GET /api/project/294761` → `{"ProjectId":294761,"Title":"CE 294761",...}`
- `GET /api/approval/1033006` → `{"ApprovalId":1033006,"Project":{"Title":"Mechanical Permit E- 10736",...}}`
- `GET /api/invoice/12256` → `{"InvoiceId":12256,"Status":"Paid","TotalAmount":270.0,...}`
- `GET /api/codeenforcement/122556` → `{"CaseId":122556,"OpenDate":"2006-07-10T00:00:00","CloseDate":"2012-08-15T10:50:32",...}`

No address-search or free-text endpoint — only numeric-ID lookup (`/project/:id`, `/approval/:id`, `/invoice/:id`, `/codeenforcement/:id`). Rate limit per the spec PDF: 20 requests / 200ms per IP, then a 200ms ban. IDs I tested cap out well under 1,000,000 (`/project/1000000` → `ErrorMessage: "...could not be found"`), and sample records date from 2003–2012; this looks like the **legacy PTS system**, not current Accela records — the newer `PMT-XXXXXXX` records visible in the City ArcGIS `DSDPermits` layer are the better source for anything post-2018.

## Accela Citizen Access
`https://aca-prod.accela.com/SANDIEGO/` returns a 302 redirect and no discoverable JSON/AJAX endpoint in the page source — it's a session-based ASP.NET UI. No public unauthenticated API found.

## Council meetings (Granicus)
`GET https://sandiego.granicus.com/ViewPublisherRSS.php?view_id=3&mode=agendas` — live RSS, confirmed:
```xml
<item><title>Tuesday Agenda Revised Added S500-S504 - Sep 01, 2026</title>
<pubDate>Tue, 01 Sep 2026 10:00:00 -0800</pubDate>
<link>https://sandiego.granicus.com/AgendaViewer.php?view_id=3&clip_id=9484</link></item>
```
`www.sandiego.gov/events` and `/specialevents-filming/calendar` were checked for an `.ics`/RSS/JSON feed in page source — none found (grep for `ics|rss|json|feed` came up empty); those pages appear to be JS-rendered with no static feed link.

## Trash holiday schedule (2026)
Scraped from `https://www.sandiego.gov/environmental-services/collection/schedule` (not an API — HTML page, would need periodic re-scrape or manual annual update):
Jan 1 (New Year's), May 25 (Memorial Day), Sept 7 (Labor Day), Nov 26 (Thanksgiving), Dec 25 (Christmas). Shift rule confirmed verbatim: collection shifts one day later for the rest of that week starting the holiday.

---

## Recommended tool mapping
| Existing bot tool | Real source(s) that could back it | Notes |
|---|---|---|
| `get_trash_schedule` / `get_next_pickup` | **No real per-address trash/recycling *day* source found.** City ArcGIS `GeoSweep_Dynamic` and seshat `gis_street_sweeping` cover **street sweeping only** (posted parking-sweep schedule), not curbside trash/recycling/organics pickup days — the synthetic 12-zone table in `00-synthesis.md` has no real public counterpart I could locate. Keep the seed-data zones for trash-day answers; swap in the real street-sweeping data if/when a "when do I need to move my car" feature is added. Real 2026 holiday shift list (`sandiego.gov/environmental-services/collection/schedule`) can replace the fictional holiday note. |
| `get_council_district` | City ArcGIS `DoIT_Public/DoIT_Public` layer 5 (council district polygon + member info) + `Locators/StreetAddress` geocoder for address→point | Fully real, live, and free. Best-verified source in this whole pass. |
| `get_permit_status` | City ArcGIS `DoIT_Public/DSDPermits` layer 0 (live Accela/PTS-sourced permits, queryable by address) for current records; **OpenDSD API** (`/api/project/:id`, `/api/approval/:id`) for pre-2018 legacy PTS records by numeric ID | `APPROVAL_STATUS` values (Issued/Opened/etc.) don't map 1:1 onto the synthesized status enum — needs a translation table. No free-text/address search on OpenDSD, ID lookup only. |
| `search_events` | seshat `special_events/special_events_list_datasd.csv` (real event data) + Granicus RSS (real, live council meeting agendas) | Special events CSV is **stale** (2021 data, not updated since 2023) — usable for market/venue metadata but not for "what's happening this week." Council meetings via Granicus RSS are genuinely live and could fully replace the fictional council-meeting seed rows. |
| `get_referral` (business tax / zoning / STRO lookups) | seshat `business_tax_certificates` CSV (active businesses by address), City ArcGIS `DSD/Zoning_Base` (zone by point), City ArcGIS `Treasurer/STRO_ACTIVE_LICENSES` (active short-term rental licenses) | All three are real and live; good fit for "is this business licensed / what's this parcel zoned / is this address a licensed STR." |
| `create_service_request` | **No public write/submission API.** `getitdone.sandiego.gov` is a JS app with no discoverable public endpoint; the only public surface is the read-only daily bulk CSV (`get_it_done_reports/*`), which *does* include `service_request_id`/`status` and so could back a **read-only "look up my case" tool** (rebuild a local index from the daily CSV) even though it can't submit new requests. | This is the clearest case of "still fictional" — submission must stay simulated/seed-data unless a real Get It Done write API surfaces. |
| Residents questions with **no public API at all** | Accela Citizen Access record-status lookup (session/UI only, confirmed dead); Get It Done live submission or single-case real-time status; live/real-time curbside trash-recycling-organics pickup day by address (only street sweeping is public); beach water quality/advisories (no County DEH service found in the folders checked) | Worth stating explicitly in the demo/PLAN docs as known gaps rather than papering over with fictional data. |
