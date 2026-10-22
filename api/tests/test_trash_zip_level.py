"""The M8 defect: a real address or a bare ZIP must still get a collection day.

Drives app.tools.trash against the FakeSession from test_live_geocode and a
mocked geocoder, so it covers the whole path (resolver -> ZIP -> zone -> date)
without a database. Depends on: app.tools.trash and app.live.geocode.
"""

from datetime import date

import httpx

from app.db import models
from app.live import http
from app.tools import trash as trash_tool
from app.tools.trash import (
    NextPickupArgs,
    TrashScheduleArgs,
    get_next_pickup,
    get_trash_schedule,
)
from tests.test_live_geocode import GEOCODER_OK, FakeSession

Z12 = models.TrashZone(
    zone_id="Z12",
    name="Rancho Bernardo / Rancho Peñasquitos",
    trash_day="Tuesday",
    recycling_week="B",
    zips=["92130", "92131"],
    notes="Trash and organics every week on Tuesday.",
)
Z06 = models.TrashZone(
    zone_id="Z06",
    name="Normal Heights / Kensington",
    trash_day="Wednesday",
    recycling_week="B",
    zips=["92116"],
    notes="",
)
# The seeded North Park zone: Wednesday, recycling on week A. 2026-09-09 is an
# ISO-odd (week A) Wednesday inside Labor Day week, so this is the one zone the
# 2026-09-07 verification could reproduce issue 1 with.
Z05 = models.TrashZone(
    zone_id="Z05",
    name="North Park / University Heights",
    trash_day="Wednesday",
    recycling_week="A",
    zips=["92104"],
    notes="",
)


def _session(address_row=None, zones=(Z12,)):
    """FakeSession cannot evaluate a WHERE clause, so `zones` is what
    `_zone(zone_id)` will return — pass only the zone the test expects."""
    return FakeSession(address_rows=[[address_row] if address_row else [], []], zones=list(zones))


def _geocoder(payload):
    http.set_transport(httpx.MockTransport(lambda r: httpx.Response(200, json=payload)))


async def test_a_real_address_outside_the_seed_answers_at_zip_level(live_on):
    # This is the 2026-09-05 defect: a Carmel Valley resident got "not found".
    _geocoder(GEOCODER_OK)
    result = await get_trash_schedule(TrashScheduleArgs(address="10615 Calle Mar de Mariposa"), _session())
    assert "error" not in result
    assert result["zone_id"] == "Z12"
    assert result["trash_day"] == "Tuesday"
    assert result["confidence"] == "zip-level"
    assert result["match"] == "geocoded"
    assert "CollectionMapLookup" in result["summary"]


async def test_a_bare_zip_answers_too(live_on):
    _geocoder({"candidates": []})  # the City locator has no candidate for a ZIP
    result = await get_trash_schedule(TrashScheduleArgs(address="92130"), _session())
    assert result["zone_id"] == "Z12"
    assert result["confidence"] == "zip-level"
    assert result["match"] == "zip"


async def test_next_pickup_carries_the_same_caveat(live_on):
    _geocoder({"candidates": []})
    result = await get_next_pickup(NextPickupArgs(address="92130", date="2026-09-01"), _session())
    assert result["pickup_date"] == "2026-09-01"
    assert result["confidence"] == "zip-level"
    assert "CollectionMapLookup" in result["summary"]


async def test_a_seed_address_stays_address_level():
    # Live is off (autouse fixture); the seed row is enough and carries no caveat.
    row = models.Address(address="4521 Adams Ave", zip="92116", zone_id="Z06", council_district=9)
    session = _session(row, zones=[Z06])
    result = await get_trash_schedule(TrashScheduleArgs(address="4521 Adams Ave"), session)
    assert result["confidence"] == "address"
    assert result["zone_id"] == "Z06"
    assert "CollectionMapLookup" not in result["summary"]
    assert "ISO" not in result["summary"]


async def test_an_unresolvable_address_still_asks_for_a_zip():
    result = await get_trash_schedule(TrashScheduleArgs(address="nowhere at all"), _session())
    assert "give me your ZIP code" in result["error"]


async def test_a_zip_with_no_zone_is_not_invented(live_on):
    _geocoder({"candidates": []})
    result = await get_trash_schedule(TrashScheduleArgs(address="90210"), _session(zones=[]))
    assert "error" in result


async def test_next_pickup_rejects_a_date_the_calendar_cannot_reach(live_on):
    """date.max + a week raised OverflowError and leaked the exception text."""
    _geocoder(GEOCODER_OK)
    result = await get_next_pickup(
        NextPickupArgs(address="10615 Calle Mar de Mariposa", date="9999-12-31"), _session()
    )
    assert "error" in result
    assert "calendar" in result["error"]
    assert "failed" not in result["error"]


async def test_the_schedule_summary_names_the_weekday_of_the_shifted_date(monkeypatch):
    """Issue 1 (2026-09-07): the summary paired a shifted date with the unshifted
    weekday, and the model wrote "Wednesday, September 10" for a Thursday.

    Labor Day 2026 is pinned through app/clock.py, which is the one place the
    tool reads the date from since M26a — get_trash_schedule takes no date."""
    monkeypatch.setattr(trash_tool.clock, "today", lambda: date(2026, 9, 7))
    row = models.Address(address="3355 University Ave", zip="92104", zone_id="Z05", council_district=3)
    result = await get_trash_schedule(
        TrashScheduleArgs(address="3355 University Ave"), _session(row, zones=[Z05])
    )
    assert result["next_recycling_date"] == "2026-09-10"
    assert result["next_recycling_weekday"] == "Thursday"
    assert "Thursday 2026-09-10" in result["summary"]
    assert "Wednesday 2026-09-10" not in result["summary"]
    assert "moved a day later because of Labor Day" in result["summary"]
