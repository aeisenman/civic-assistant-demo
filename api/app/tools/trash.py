"""Trash tools: schedule by address, next pickup for that zone, holiday calendar.

Called through app/tools/registry.py by the trash and general agent profiles.
Depends on: app/live/geocode.py (the one address resolver, which falls back to
the City geocoder and then to a bare ZIP), the trash_zones seed table and the
pure date math in app/tools/trash_calendar.py.
"""

from datetime import date

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import clock
from app.db import models
from app.live.geocode import ZIP_LEVEL_CAVEAT, Resolved, resolve_address
from app.tools import trash_calendar

NOT_FOUND = (
    "I couldn't find {address} in the collection map. Please double-check the street "
    "name and number (for example '4521 Adams Ave'), or give me your ZIP code."
)

SHIFT_RULE = (
    "There is no collection on a City holiday: that day's route and every remaining route "
    "that week run one day later, so a Friday route can move to Saturday."
)


class TrashScheduleArgs(BaseModel):
    address: str = Field(description="Street address or ZIP code, e.g. '4521 Adams Ave'")


class NextPickupArgs(BaseModel):
    address: str = Field(description="Street address or ZIP code, e.g. '4521 Adams Ave'")
    date: str | None = Field(default=None, description="ISO date to search from; defaults to today")


class HolidayScheduleArgs(BaseModel):
    date: str | None = Field(default=None, description="ISO date to list holidays from; defaults to today")


# The collection calendar is anchored on the seeded 2026 holidays; outside
# this window an answer would be invented rather than looked up.
MIN_YEAR = 2000
MAX_YEAR = 2100


async def _zone(session: AsyncSession, zone_id: str | None) -> models.TrashZone | None:
    if not zone_id:
        return None
    return (
        (await session.execute(select(models.TrashZone).where(models.TrashZone.zone_id == zone_id)))
        .scalars()
        .first()
    )


def _shift_note(holiday: str | None) -> str:
    """The parenthetical that explains why a date is not on the usual weekday."""
    return f" (moved a day later because of {holiday})" if holiday else ""


def _confidence(found: Resolved) -> dict:
    """How the zone was reached, and the caveat a ZIP-level answer has to carry."""
    if not found.zip_level:
        return {"confidence": "address", "match": found.match}
    return {"confidence": "zip-level", "match": found.match, "caveat": ZIP_LEVEL_CAVEAT}


async def get_trash_schedule(args: TrashScheduleArgs, session: AsyncSession) -> dict:
    """Collection day for an address, plus a real date for the next recycling run.

    A resident cannot act on "Week B", so the alternating recycling cadence is
    resolved here into a date. `organics_week` is deliberately not returned:
    organics go out weekly with trash, so the letter would only mislead.
    """
    found = await resolve_address(args.address, session)
    zone = await _zone(session, found.zone_id) if found else None
    if zone is None:
        message = NOT_FOUND.format(address=args.address)
        return {"error": message, "summary": message}

    recycling = trash_calendar.next_recycling(zone.trash_day, zone.recycling_week, clock.today())
    # Not "next on <date>": during a holiday week that date is a day later than
    # the zone's trash day, and the weekday has to move with it (issue 1).
    when = (
        f"next recycling pickup is {recycling['next_recycling_weekday']} "
        f"{recycling['next_recycling_date']}"
        f"{_shift_note(recycling['next_recycling_holiday_shift'])}"
        if recycling["next_recycling_date"]
        else "check your address on the collection map for the next date"
    )
    confidence = _confidence(found)
    return {
        "address": found.address,
        "zip": found.zip,
        "zone_id": zone.zone_id,
        "zone_name": zone.name,
        "trash_day": zone.trash_day,
        "recycling_week": zone.recycling_week,
        **recycling,
        **confidence,
        "notes": zone.notes,
        "summary": (
            f"{found.address} is in zone {zone.zone_id} ({zone.name}): trash and organics "
            f"every {zone.trash_day}; recycling every other {zone.trash_day}, {when}."
            + (f" {confidence['caveat']}" if "caveat" in confidence else "")
        ),
    }


async def get_next_pickup(args: NextPickupArgs, session: AsyncSession) -> dict:
    """Next collection date for an address, with the holiday shift applied."""
    found = await resolve_address(args.address, session)
    zone = await _zone(session, found.zone_id) if found else None
    if zone is None:
        message = NOT_FOUND.format(address=args.address)
        return {"error": message, "summary": message}

    try:
        start = date.fromisoformat(args.date) if args.date else clock.today()
    except ValueError:
        message = f"'{args.date}' is not a date I can read; use YYYY-MM-DD."
        return {"error": message, "summary": message}
    # date.max + a week overflows, and the tool reported "get_next_pickup failed:
    # date value out of range" — an internal error message shown to a resident.
    if not MIN_YEAR <= start.year <= MAX_YEAR:
        message = (
            f"{start.isoformat()} is outside the years I have a calendar for "
            f"({MIN_YEAR}-{MAX_YEAR}). Give me a date near today."
        )
        return {"error": message, "summary": message}

    result = trash_calendar.next_pickup(zone.trash_day, zone.recycling_week, start)
    bins = ["trash", "organics"]  # both go out every week
    if result["recycling_this_week"]:
        bins.append("recycling")
    shift = _shift_note(result["holiday_shift"])
    confidence = _confidence(found)
    return {
        "address": found.address,
        "zip": found.zip,
        "zone_id": zone.zone_id,
        "zone_name": zone.name,
        **result,
        **confidence,
        "bins_out": bins,
        "summary": (
            f"Next collection for {found.address} (zone {zone.zone_id}) is "
            f"{result['weekday']} {result['pickup_date']}{shift}. Put out: "
            f"{', '.join(bins)}." + (f" {confidence['caveat']}" if "caveat" in confidence else "")
        ),
    }


async def get_holiday_schedule(args: HolidayScheduleArgs, session: AsyncSession) -> dict:
    """The remaining City collection holidays and the one-day shift rule.

    Exists because a holiday question needs no address: without this tool the
    assistant either stalls asking for one or answers from memory.
    """
    try:
        start = date.fromisoformat(args.date) if args.date else clock.today()
    except ValueError:
        message = f"'{args.date}' is not a date I can read; use YYYY-MM-DD."
        return {"error": message, "summary": message}
    if not MIN_YEAR <= start.year <= MAX_YEAR:
        message = (
            f"{start.isoformat()} is outside the years I have a calendar for "
            f"({MIN_YEAR}-{MAX_YEAR}). Give me a date near today."
        )
        return {"error": message, "summary": message}

    holidays = trash_calendar.remaining_holidays(start)
    listed = "; ".join(f"{h['name']} {h['weekday']} {h['date']}" for h in holidays)
    return {
        "from_date": start.isoformat(),
        "holidays": holidays,
        "shift_rule": SHIFT_RULE,
        "summary": (
            f"Collection holidays on or after {start.isoformat()}: "
            f"{listed or 'none left on the published calendar'}. "
            f"{SHIFT_RULE}"
        ),
    }
