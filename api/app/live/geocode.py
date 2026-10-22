"""The one address resolver: seed row -> City geocoder -> bare ZIP.

Called by every address-taking tool (app/tools/trash.py, app/tools/civic.py,
app/live/arcgis.py) so a resident who types a real address that is not one of
the 40 fictional seed rows still gets an answer. Depends on: the addresses and
trash_zones tables, app/live/http.py and the City's ArcGIS geocoder.
"""

import logging
import math
import re
from dataclasses import asdict, dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models
from app.live import http

log = logging.getLogger(__name__)

GEOCODER_URL = (
    "https://webmaps.sandiego.gov/arcgis/rest/services/Locators/StreetAddress"
    "/GeocodeServer/findAddressCandidates"
)
MIN_SCORE = 80  # below this the candidate is a guess, not a match
ZIP_RE = re.compile(r"\b(9[0-2]\d{3})\b")
EARTH_HALF_CIRCUMFERENCE_M = 20037508.342789244

COLLECTION_MAP_URL = "https://getitdone.sandiego.gov/CollectionMapLookup"
ZIP_LEVEL_CAVEAT = (
    "That is a ZIP-code-level answer from this demo's fictional zone map, not a "
    f"per-address lookup — confirm your street's real day at {COLLECTION_MAP_URL}."
)


@dataclass
class Resolved:
    """What every address-taking tool needs, however the address was matched.

    `match` says how much to trust it: "seed" is an exact demo row, "geocoded"
    is a real City address whose zone came from its ZIP, "zip" is a bare ZIP.
    `x`/`y` are Web Mercator (EPSG:3857), the geocoder's native output and what
    the ArcGIS point queries are fed, so nothing is reprojected twice.
    """

    address: str
    zip: str | None = None
    lat: float | None = None
    lon: float | None = None
    council_district: int | None = None
    zone_id: str | None = None
    match: str = "seed"
    x: float | None = None
    y: float | None = None

    @property
    def zip_level(self) -> bool:
        """True when the collection zone came from the ZIP, not the address."""
        return self.match in ("geocoded", "zip")

    def as_dict(self) -> dict:
        """Plain dict for a tool result, which has to be JSON the model can read."""
        return asdict(self)


def _to_lat_lon(x: float, y: float) -> tuple[float, float]:
    """Web Mercator metres -> WGS84 degrees, for display and for lat/lon queries."""
    lon = x / EARTH_HALF_CIRCUMFERENCE_M * 180.0
    lat = math.degrees(2 * math.atan(math.exp(y / EARTH_HALF_CIRCUMFERENCE_M * math.pi)) - math.pi / 2)
    return round(lat, 6), round(lon, 6)


def escape_like(text: str) -> str:
    r"""Escape the LIKE metacharacters so a typed "%" matches a literal percent.

    Without this, `resolve_address("%")` matched the first row in `addresses` and
    the assistant answered a collection schedule for an address the resident
    never gave. `\` is the escape character passed to ILIKE below.
    """
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def _seed_match(session: AsyncSession, text: str) -> models.Address | None:
    """Exact match first, then a case-insensitive contains — residents type loosely."""
    cleaned = text.strip()
    stmt = select(models.Address).where(models.Address.address == cleaned)
    row = (await session.execute(stmt)).scalars().first()
    if row is None:
        pattern = f"%{escape_like(cleaned)}%"
        stmt = select(models.Address).where(models.Address.address.ilike(pattern, escape="\\"))
        row = (await session.execute(stmt)).scalars().first()
    return row


async def zone_for_zip(session: AsyncSession, zip_code: str | None) -> str | None:
    """The fictional collection zone whose `zips` list covers this ZIP."""
    if not zip_code:
        return None
    rows = (await session.execute(select(models.TrashZone))).scalars().all()
    for zone in rows:
        if zip_code in (zone.zips or []):
            return zone.zone_id
    return None


async def _candidates(text: str) -> list[dict]:
    payload = await http.fetch_json(GEOCODER_URL, {"Address": text, "outFields": "*", "f": "json"})
    return (payload or {}).get("candidates") or []


async def geocode(text: str) -> dict | None:
    """Best City geocoder candidate for `text`, or None below MIN_SCORE.

    `Address=` beats `SingleLine=` on this locator (research/05, 2026-09-05):
    SingleLine scored "202 C St" in the sixties, Address scores it 100. The
    locator also wants the street line *only*: "202 C St, San Diego, CA" scores
    58 and matches W California St, so a comma-tailed address is retried on the
    part before the first comma. Residents and the model both type the tail.
    """
    attempts = [text.strip()]
    head = attempts[0].split(",")[0].strip()
    if head and head != attempts[0]:
        attempts.append(head)

    typed_zip = ZIP_RE.search(text)
    for attempt in attempts:
        candidates = await _candidates(attempt)
        if not candidates:
            continue
        best = max(candidates, key=lambda c: c.get("score") or 0)
        if (best.get("score") or 0) < MIN_SCORE:
            log.info("geocode: best score %s below %s for %r", best.get("score"), MIN_SCORE, attempt)
            continue
        # The locator only ever searches City streets, so "276 Fourth Ave, Chula
        # Vista, CA 91910" scored 100 against a *downtown San Diego* address and
        # the resident was told their Chula Vista trash day. If the resident gave
        # a ZIP and the candidate is in a different one, it is a different place.
        found_zip = ((best.get("attributes") or {}).get("Postal") or "").strip()
        if typed_zip and found_zip and found_zip != typed_zip.group(1):
            log.info(
                "geocode: candidate ZIP %s != typed ZIP %s for %r; rejecting",
                found_zip,
                typed_zip.group(1),
                attempt,
            )
            continue
        return best
    return None


async def resolve_address(text: str, session: AsyncSession) -> Resolved | None:
    """Seed row, else the City geocoder, else a bare ZIP in the text. None if all fail."""
    if not text or not text.strip():
        return None

    row = await _seed_match(session, text)
    if row is not None:
        return Resolved(
            address=row.address,
            zip=row.zip,
            council_district=row.council_district,
            zone_id=row.zone_id,
            match="seed",
        )

    candidate = await geocode(text)
    if candidate is not None:
        location = candidate.get("location") or {}
        x, y = location.get("x"), location.get("y")
        lat, lon = _to_lat_lon(x, y) if x is not None and y is not None else (None, None)
        zip_code = (candidate.get("attributes") or {}).get("Postal") or None
        return Resolved(
            address=candidate.get("address") or text.strip(),
            zip=zip_code,
            lat=lat,
            lon=lon,
            zone_id=await zone_for_zip(session, zip_code),
            match="geocoded",
            x=x,
            y=y,
        )

    found = ZIP_RE.search(text)
    if found:
        zip_code = found.group(1)
        return Resolved(
            address=f"ZIP {zip_code}",
            zip=zip_code,
            zone_id=await zone_for_zip(session, zip_code),
            match="zip",
        )
    return None
