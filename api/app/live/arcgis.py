"""Live City of San Diego map lookups: district, sweeping, zoning, permits, agendas.

Registered as tools in app/tools/registry.py and called from the agent profiles;
every function takes the same (args, session) shape as the seed-data tools.
Depends on: app/live/http.py (timeout + 10-minute cache) and app/live/geocode.py
(the one address resolver). Endpoints are the ones verified in
research/05-live-data-sources.md on 2026-09-05.
"""

import logging
import re
from datetime import UTC, date, datetime
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models
from app.live import http
from app.live.geocode import escape_like, geocode, resolve_address

log = logging.getLogger(__name__)

BASE = "https://webmaps.sandiego.gov/arcgis/rest/services"
COUNCIL_LAYER = f"{BASE}/DoIT_Public/DoIT_Public/MapServer/5/query"
SWEEP_LAYER = f"{BASE}/GeoSweep/GeoSweep_Dynamic/MapServer/13/query"
ZONING_LAYER = f"{BASE}/DSD/Zoning_Base/MapServer/0/query"
PERMITS_LAYER = f"{BASE}/DoIT_Public/DSDPermits/MapServer/0/query"
AGENDA_RSS = "https://sandiego.granicus.com/ViewPublisherRSS.php?view_id=3&mode=agendas"

MAX_PERMITS = 5
MAX_SWEEP_SEGMENTS = 4
MAX_AGENDAS = 5

# The suffix spellings residents type -> the abbreviation the City's road layer
# stores in RD20FULL ("ADAMS AV", not "ADAMS AVE" or "ADAMS AVENUE").
STREET_TYPES = {
    "street": "ST",
    "st": "ST",
    "avenue": "AV",
    "ave": "AV",
    "av": "AV",
    "boulevard": "BL",
    "blvd": "BL",
    "bl": "BL",
    "drive": "DR",
    "dr": "DR",
    "road": "RD",
    "rd": "RD",
    "place": "PL",
    "pl": "PL",
    "court": "CT",
    "ct": "CT",
    "lane": "LN",
    "ln": "LN",
    "way": "WY",
    "wy": "WY",
    "circle": "CR",
    "cir": "CR",
    "terrace": "TR",
    "ter": "TR",
    "parkway": "PY",
    "pkwy": "PY",
}
# Words a resident adds that are not part of the street name.
NOISE_WORDS = {"downtown", "san", "diego", "ca", "california", "in", "on", "the", "near"}


class AddressArgs(BaseModel):
    address: str = Field(description="Street address or street name, e.g. '202 C St'")


class CouncilDistrictArgs(BaseModel):
    address: str = Field(description="Street address, e.g. '7890 Girard Ave'")


# ------------------------------------------------------------------ helpers
def _point_params(resolved) -> dict | None:
    """ArcGIS point-query parameters in the geocoder's own spatial reference."""
    if resolved.x is not None and resolved.y is not None:
        return {"geometry": f"{resolved.x},{resolved.y}", "inSR": 3857}
    if resolved.lat is not None and resolved.lon is not None:
        return {"geometry": f"{resolved.lon},{resolved.lat}", "inSR": 4326}
    return None


async def _features(url: str, params: dict) -> list[dict] | None:
    """Attribute dicts from an ArcGIS query; None when the service did not answer.

    None and [] are different answers and the resident hears the difference: []
    means "the City has no record", None means "the City's service is down".
    Conflating them made a timed-out lookup report "no posted sweeping route for
    C ST" and "no permit records" — a confident statement about data we never saw.
    """
    payload = await http.fetch_json(url, params)
    if not isinstance(payload, dict) or "features" not in payload:
        if payload is not None:
            log.warning("arcgis: unexpected payload from %s: %s", url, str(payload)[:200])
        return None
    return [f.get("attributes") or {} for f in payload["features"]]


def _epoch_ms_to_date(value) -> str | None:
    """ArcGIS dates are epoch milliseconds; None and 0 both mean 'no date'."""
    if not value:
        return None
    try:
        return datetime.fromtimestamp(value / 1000, tz=UTC).date().isoformat()
    except (TypeError, ValueError, OSError):
        return None


def street_name_for_sweeping(text: str, candidate: dict | None = None) -> str | None:
    """The RD20FULL street name for `text`, preferring the geocoder's own parse.

    The geocoder hands back StPreDir/StName/StType already in City abbreviations,
    which is exactly what the sweeping layer stores. When it cannot match (a
    street name with no house number, "C St downtown"), fall back to normalising
    what the resident typed.
    """
    attributes = (candidate or {}).get("attributes") or {}
    if attributes.get("StName"):
        parts = [attributes.get("StPreDir"), attributes["StName"], attributes.get("StType")]
        return " ".join(p.strip() for p in parts if p and p.strip()).upper()

    words = [w for w in re.findall(r"[A-Za-z]+", text) if w.lower() not in NOISE_WORDS]
    if not words:
        return None
    if len(words) > 1 and words[-1].lower() in STREET_TYPES:
        words[-1] = STREET_TYPES[words[-1].lower()]
    return " ".join(words).upper()


def _house_number(text: str, candidate: dict | None = None) -> int | None:
    attributes = (candidate or {}).get("attributes") or {}
    number = attributes.get("AddNum") or (re.match(r"\s*(\d+)", text) or [None, None])[1]
    try:
        return int(number)
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------ tools
async def get_council_district(args: CouncilDistrictArgs, session: AsyncSession) -> dict:
    """Councilmember for an address: the live City layer, else the seed table.

    Replaces the seed-only lookup in app/tools/civic.py. A seed address keeps
    its fictional councilmember (that is what the rest of the demo shows); a
    real address geocodes and gets the real district, member, phone and site.
    """
    resolved = await resolve_address(args.address, session)
    if resolved is None:
        message = (
            f"I couldn't find {args.address}. Please double-check the street name and "
            "number, or give a nearby cross street."
        )
        return {"error": message, "summary": message}

    point = _point_params(resolved)
    if point is not None:
        rows = await _features(
            COUNCIL_LAYER,
            {
                **point,
                "geometryType": "esriGeometryPoint",
                "spatialRel": "esriSpatialRelIntersects",
                "outFields": "DISTRICT,NAME,PHONE,WEBSITE",
                "returnGeometry": "false",
                "f": "json",
            },
        )
        if rows:
            row = rows[0]
            return {
                "address": resolved.address,
                "district": row.get("DISTRICT"),
                "councilmember": row.get("NAME"),
                "phone": row.get("PHONE"),
                "website": row.get("WEBSITE"),
                "source": "live",
                "match": resolved.match,
                "summary": (
                    f"According to the City's live map data, {resolved.address} is in Council "
                    f"District {row.get('DISTRICT')}, represented by {row.get('NAME')} "
                    f"({row.get('PHONE')}, {row.get('WEBSITE')})."
                ),
            }

    return await _seed_council_district(resolved, session)


async def _seed_council_district(resolved, session: AsyncSession) -> dict:
    """Fallback: the fictional council_districts table this demo ships with."""
    if resolved.council_district is None:
        message = (
            f"I couldn't work out the council district for {resolved.address} — the City's "
            "map service didn't answer and this address isn't in the demo data."
        )
        return {"error": message, "summary": message}
    district = (
        (
            await session.execute(
                select(models.CouncilDistrict).where(
                    models.CouncilDistrict.district == resolved.council_district
                )
            )
        )
        .scalars()
        .first()
    )
    neighborhoods = district.neighborhoods if district else []
    return {
        "address": resolved.address,
        "district": resolved.council_district,
        "councilmember": district.councilmember if district else None,
        "neighborhoods": neighborhoods,
        "source": "seed",
        "match": resolved.match,
        "summary": (
            f"Based on demo data, {resolved.address} is in Council District "
            f"{resolved.council_district}"
            + (f" ({', '.join(neighborhoods)})" if neighborhoods else "")
            + (f", represented by {district.councilmember}." if district else ".")
        ),
    }


async def get_street_sweeping(args: AddressArgs, session: AsyncSession) -> dict:
    """Posted street-sweeping schedule for a street, narrowed to the block if we can.

    The City publishes sweeping by street name and address range, so this is the
    one "when do I move my car" answer that is real rather than seeded.
    """
    candidate = await geocode(args.address)
    street = street_name_for_sweeping(args.address, candidate)
    if not street:
        message = f"I couldn't work out a street name from '{args.address}'."
        return {"error": message, "summary": message}

    rows = await _features(
        SWEEP_LAYER,
        {
            "where": f"RD20FULL = '{street.replace(chr(39), chr(39) * 2)}'",
            "outFields": "RD20FULL,LOW_ADDR,HIGH_ADDR,SCHEDULE,POSTED,CDCODE,ZIP",
            "returnGeometry": "false",
            "f": "json",
        },
    )
    if rows is None:
        message = (
            f"The City's street-sweeping map didn't answer just now, so I can't tell you the "
            f"posted schedule for {street}. Try again in a minute, or read the signs on your "
            "block."
        )
        return {"error": message, "street": street, "source": "unavailable", "summary": message}
    if not rows:
        message = (
            f"The City's street-sweeping layer has no posted route for {street}. Not every "
            "street is on a posted sweeping schedule; check the signs on your block."
        )
        return {"street": street, "segments": [], "source": "live", "summary": message}

    number = _house_number(args.address, candidate)
    zip_code = ((candidate or {}).get("attributes") or {}).get("Postal")
    # ZIP first, then the address range. A long street crosses ZIPs and reuses
    # block numbers: "202 C St" downtown (92101) sits inside the 0-3849 range of
    # the *other* C St segment in 92102, so filtering on the number alone
    # confidently returns the wrong neighbourhood's schedule.
    scoped = [r for r in rows if str(r.get("ZIP")) == str(zip_code)] if zip_code else []
    scoped = scoped or rows
    exact = [
        r
        for r in scoped
        if number is not None and (r.get("LOW_ADDR") or 0) <= number <= (r.get("HIGH_ADDR") or 0)
    ]
    chosen = (exact or scoped)[:MAX_SWEEP_SEGMENTS]

    segments = [
        {
            "street": r.get("RD20FULL"),
            "block": f"{r.get('LOW_ADDR')}-{r.get('HIGH_ADDR')}",
            "schedule": r.get("SCHEDULE"),
            "posted": r.get("POSTED") == "P",
            "zip": str(r.get("ZIP")) if r.get("ZIP") else None,
            "council_district": r.get("CDCODE"),
        }
        for r in chosen
    ]
    scope = "that block" if exact and number is not None else f"{street} (all matching blocks)"
    lines = "; ".join(f"{s['block']}: {s['schedule']}" for s in segments)
    return {
        "street": street,
        "segments": segments,
        "matched_block": bool(exact and number is not None),
        "source": "live",
        "summary": (
            f"According to the City's live map data, street sweeping for {scope} is — {lines}. "
            "NS is the north side, SS the south side; 'Not Posted' means no signs are posted "
            "and no ticket is issued for the sweep."
        ),
    }


async def get_zoning(args: AddressArgs, session: AsyncSession) -> dict:
    """Zone code at an address from the City's Zoning_Base layer."""
    resolved = await resolve_address(args.address, session)
    point = _point_params(resolved) if resolved else None
    if point is None:
        message = (
            f"I couldn't place {args.address} on the City's map, so I can't read its zoning. "
            "Give me the full street address including the number."
        )
        return {"error": message, "summary": message}

    rows = await _features(
        ZONING_LAYER,
        {
            **point,
            "geometryType": "esriGeometryPoint",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "*",
            "returnGeometry": "false",
            "f": "json",
        },
    )
    if rows is None:
        message = (
            f"The City's zoning map didn't answer just now, so I can't read the zoning for "
            f"{resolved.address}. Try again in a minute."
        )
        return {"error": message, "source": "unavailable", "summary": message}
    if not rows:
        message = (
            f"The City's zoning layer has no polygon covering {resolved.address}, so it sits "
            "outside the City's zoning jurisdiction."
        )
        return {"error": message, "source": "live", "summary": message}

    row = rows[0]
    zone = row.get("ZONE_NAME")
    # The layer carries no plain-English description, only the code and the
    # adopting ordinance, so say the code and stop rather than inventing a reading.
    return {
        "address": resolved.address,
        "zone": zone,
        "ordinance": row.get("ORDNUM"),
        "source": "live",
        "match": resolved.match,
        "summary": (
            f"According to the City's live map data, {resolved.address} is zoned {zone} "
            f"(adopting ordinance {row.get('ORDNUM')}). The zoning layer publishes the code "
            "only; what that code permits is in the Municipal Code, "
            "sandiego.gov/development-services/zoning."
        ),
    }


async def search_city_permits(args: AddressArgs, session: AsyncSession) -> dict:
    """Real City permit records at an address (Accela-sourced PMT-* numbers)."""
    resolved = await resolve_address(args.address, session)
    where_value = (resolved.address if resolved else args.address).split(",")[0].strip()
    # Quotes are doubled so the literal cannot be closed, and the LIKE
    # metacharacters are escaped so an address of "%" cannot dump every row of
    # the City's live permit layer. escape_like is the same helper the database
    # queries use; the ESCAPE clause below tells the layer's SQL about it.
    # where_value itself stays readable, because it is quoted back to residents.
    like_value = escape_like(where_value).replace("'", "''")
    rows = await _features(
        PERMITS_LAYER,
        {
            # UPPER on both sides: this layer's LIKE is case-sensitive, and the
            # geocoder hands back "202 C ST" while the layer stores "202 C St",
            # so a raw LIKE finds nothing for an address that has 18 records.
            "where": f"UPPER(GIS_ADDRESS) LIKE UPPER('%{like_value}%') ESCAPE '\\'",
            "outFields": (
                "APPROVAL_ID,APPROVAL_TYPE,APPROVAL_STATUS,APPROVAL_CREATE_DATE,"
                "APPROVAL_ISSUE_DATE,GIS_ADDRESS,APPROVAL_SCOPE"
            ),
            "orderByFields": "APPROVAL_CREATE_DATE DESC",
            "resultRecordCount": MAX_PERMITS,
            "returnGeometry": "false",
            "f": "json",
        },
    )
    if rows is None:
        message = (
            f"The City's permit map didn't answer just now, so I can't say what is on file for "
            f"{where_value}. Try again in a minute, or search aca.accela.com/SANDIEGO directly."
        )
        return {
            "error": message,
            "address": where_value,
            "source": "unavailable",
            "summary": message,
        }
    if not rows:
        message = (
            f"The City's permit layer has no records matching {where_value}. That layer only "
            "covers Development Services approvals, so an address can be real and still have "
            "none on file."
        )
        return {"address": where_value, "permits": [], "source": "live", "summary": message}

    permits = [
        {
            "number": r.get("APPROVAL_ID"),
            "type": r.get("APPROVAL_TYPE"),
            "status": r.get("APPROVAL_STATUS"),
            "created": _epoch_ms_to_date(r.get("APPROVAL_CREATE_DATE")),
            "issued": _epoch_ms_to_date(r.get("APPROVAL_ISSUE_DATE")),
            "address": r.get("GIS_ADDRESS"),
        }
        for r in rows[:MAX_PERMITS]
    ]
    lines = "; ".join(
        f"{p['number']} {p['type']} — {p['status']}" + (f", created {p['created']}" if p["created"] else "")
        for p in permits
    )
    return {
        "address": where_value,
        "permits": permits,
        "source": "live",
        "summary": (
            f"According to the City's live map data, {len(permits)} permit record(s) on file "
            f"for {where_value}: {lines}. These are real City records (PMT- numbers); the "
            "PRM-2026- numbers this assistant issues are demo applications."
        ),
    }


# ------------------------------------------------------------------ agendas
async def council_agendas(limit: int = MAX_AGENDAS) -> list[dict]:
    """Upcoming/recent council meeting agendas from the Granicus RSS feed.

    Merged into search_events so "when is the next council meeting" answers from
    the real calendar instead of the fictional seed rows.
    """
    xml = await http.fetch_text(AGENDA_RSS)
    if not xml:
        return []
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as exc:
        log.warning("arcgis: council agenda RSS did not parse: %s", exc)
        return []

    items: list[dict] = []
    for item in root.iterfind(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        published = item.findtext("pubDate")
        when: date | None = None
        if published:
            try:
                when = parsedate_to_datetime(published).date()
            except (TypeError, ValueError):
                when = None
        items.append(
            {
                "title": title,
                "date": when.isoformat() if when else None,
                "start_time": None,
                "end_time": None,
                "location": "Council Chambers, 202 C St",
                "department": "City Council",
                "cost": "free",
                "url": link,
                "source": "live",
            }
        )
    items.sort(key=lambda i: i["date"] or "", reverse=True)
    return items[:limit]
