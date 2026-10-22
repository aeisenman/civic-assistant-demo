# seed_data — formats (fixed by PLAN.md §13)

Every file is a JSON **array of objects**. `app/seed/loader.py` truncates the
target table and re-inserts on startup when `SEED_ON_STARTUP=true`; files that
are absent are skipped, and keys that are not columns are ignored. Editing a
file and restarting the API is the entire update workflow.

`trash_zones.json` and `addresses.json` currently hold two/three placeholder
rows so the loader can be exercised; the content task replaces them.

| File | Table | Object shape |
|---|---|---|
| `trash_zones.json` | `trash_zones` | `{zone_id:"Z01", name:"North Park A", trash_day:"Monday", recycling_week:"A"\|"B", organics_week:"A"\|"B", zips:["92116", ...], notes}` |
| `addresses.json` | `addresses` | `{address:"4521 Adams Ave", zip:"92116", zone_id:"Z01", council_district:3}` (~40 rows) |
| `events.json` | `events` | `{title, date:"2026-09-12", start_time:"09:00", end_time:"12:00", location, department, cost:"Free", description, url}` (25 rows) |
| `permit_types.json` | `permit_types` | `{code:"NOPLAN", name, description, base_fee_cents, per_1000_valuation_cents, typical_turnaround_days, requires_plans_over_valuation_cents}` |
| `service_categories.json` | `service_categories` | `{category:"missed_pickup", label, department, sla_days, description}` |
| `referrals.json` | `referrals` | `{topic, agency, url, note}` |
| `council_districts.json` | `council_districts` | `{district:1, councilmember:"(fictional) ...", neighborhoods:["La Jolla", ...]}` |
| `sample_applications.json` | `applications` | `{tracking_number:"PRM-2026-000123", type, status, fields:{...}, department, fee_cents}` — pre-existing applications so `get_permit_status` finds something on day one. `status` must be one of the six **manual** states (`needs_info`, `in_review`, `approved`, `issued`, `rejected`, `closed`): the worker auto-advances `submitted`, `validating` and `routed`, so a fixture in one of those is rewritten on every restart |

Notes
- Trash and organics are collected every week; only recycling alternates: week **A** = odd ISO
  weeks, week **B** = even. `organics_week` is legacy since M6 and is no longer read by any tool.
- `date` is parsed to a real `DATE`; `start_time`/`end_time` stay text (`"09:00"`).
- `zips` (added by migration `004_m8_live.sql`) is the ZIP -> zone fallback the M8 address
  resolver uses when a real address geocodes to a ZIP no seed row covers. The 37 City ZIPs are
  split across the 12 zones by rough geography; **the mapping is fictional**, which is why every
  ZIP-level answer carries a link to the City's real collection map. Keep the lists disjoint.
- `fields` and `neighborhoods` are JSONB — pass real JSON objects/arrays, not strings.
