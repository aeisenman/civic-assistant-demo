"""resolve_address: seed row -> City geocoder -> bare ZIP, with no real network.

Runs against fake AsyncSession objects and a mocked httpx transport, so it proves
the fallback order without a database or webmaps.sandiego.gov. The geocoder JSON
below is trimmed from the real response recorded in research/05-live-data-sources.md.
"""

import httpx
import pytest

from app.db import models
from app.live import http
from app.live.geocode import Resolved, _to_lat_lon, geocode, resolve_address, zone_for_zip

# Real shape, trimmed: the fields resolve_address actually reads.
GEOCODER_OK = {
    "candidates": [
        {
            "address": "10615 CALLE MAR DE MARIPOSA, 92130",
            "location": {"x": -13049732.53, "y": 3883824.30},
            "score": 100,
            "attributes": {"Postal": "92130", "AddNum": "10615", "StName": "CALLE MAR DE MARIPOSA"},
        }
    ]
}
GEOCODER_WEAK = {"candidates": [{"address": "C ST, 92101", "location": {}, "score": 41.82}]}


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return list(self._rows)


class FakeSession:
    """A stand-in for AsyncSession that answers by target table.

    `address_rows` is a list of result sets consumed one select at a time,
    because the resolver queries `addresses` twice (exact match, then ILIKE).
    Everything else comes from `tables`, keyed by __tablename__.
    """

    def __init__(self, address_rows=(), zones=(), **tables):
        self._address_rows = list(address_rows)
        self._tables = {"trash_zones": list(zones), **tables}

    async def execute(self, stmt):
        table = stmt.column_descriptions[0]["entity"].__tablename__
        if table == "addresses":
            return FakeResult(self._address_rows.pop(0) if self._address_rows else [])
        return FakeResult(self._tables.get(table, []))


def _zone(zone_id, zips):
    return models.TrashZone(zone_id=zone_id, name=zone_id, trash_day="Tuesday", zips=zips)


def _transport(payload, status=200):
    return httpx.MockTransport(lambda request: httpx.Response(status, json=payload))


# ------------------------------------------------------------------ pure maths
def test_web_mercator_converts_to_the_expected_lat_lon():
    lat, lon = _to_lat_lon(-13042511.42, 3857768.06)
    # 202 C St is City Hall, downtown: about 32.717 N, 117.163 W. (The geocoder's
    # rooftop point and the permit layer's parcel centroid differ by ~150 m, which
    # is why this is a coarse check and not an exact one.)
    assert lon == pytest.approx(-117.1633, abs=0.001)
    assert lat == pytest.approx(32.7168, abs=0.001)


def test_zip_level_flag_only_set_for_non_seed_matches():
    assert Resolved(address="a", match="seed").zip_level is False
    assert Resolved(address="a", match="geocoded").zip_level is True
    assert Resolved(address="a", match="zip").zip_level is True


# ------------------------------------------------------------------ seed first
async def test_a_seed_address_never_reaches_the_network(live_on):
    row = models.Address(address="4521 Adams Ave", zip="92116", zone_id="Z06", council_district=9)

    def explode(request):  # pragma: no cover - only runs if the ordering breaks
        raise AssertionError("the geocoder must not be called for a seed address")

    http.set_transport(httpx.MockTransport(explode))
    found = await resolve_address("4521 Adams Ave", FakeSession(address_rows=[[row]]))
    assert found.match == "seed"
    assert found.zone_id == "Z06"
    assert found.council_district == 9


# ------------------------------------------------------------------ geocoder
async def test_a_real_address_geocodes_and_gets_a_zone_from_its_zip(live_on):
    http.set_transport(_transport(GEOCODER_OK))
    session = FakeSession(address_rows=[[], []], zones=[_zone("Z12", ["92130"])])
    found = await resolve_address("10615 Calle Mar de Mariposa", session)
    assert found.match == "geocoded"
    assert found.zip == "92130"
    assert found.zone_id == "Z12"
    assert found.lat == pytest.approx(32.95, abs=0.05)
    assert found.x == -13049732.53  # kept for the ArcGIS point queries


async def test_a_low_score_candidate_is_not_a_match(live_on):
    http.set_transport(_transport(GEOCODER_WEAK))
    assert await geocode("C St downtown") is None


async def test_a_comma_tailed_address_is_retried_on_the_street_line(live_on):
    # "202 C St, San Diego, CA" scores 58 on this locator and matches the wrong
    # street; the street line alone scores 100. Verified live 2026-09-05.
    asked: list[str] = []

    def handler(request):
        wanted = request.url.params["Address"]
        asked.append(wanted)
        if "," in wanted:
            return httpx.Response(200, json=GEOCODER_WEAK)
        return httpx.Response(200, json=GEOCODER_OK)

    http.set_transport(httpx.MockTransport(handler))
    best = await geocode("202 C St, San Diego, CA")
    assert asked == ["202 C St, San Diego, CA", "202 C St"]
    assert best["score"] == 100


# ------------------------------------------------------------------ bare ZIP
async def test_a_bare_zip_falls_through_to_the_zip_branch(live_on):
    # The City geocoder returns no candidates for a bare ZIP (checked 2026-09-05).
    http.set_transport(_transport({"candidates": []}))
    session = FakeSession(address_rows=[[], []], zones=[_zone("Z12", ["92130"])])
    found = await resolve_address("92130", session)
    assert found.match == "zip"
    assert found.zip == "92130"
    assert found.zone_id == "Z12"


async def test_unresolvable_text_returns_none(live_on):
    http.set_transport(_transport({"candidates": []}))
    session = FakeSession(address_rows=[[], []])
    assert await resolve_address("somewhere nice", session) is None


async def test_empty_text_short_circuits():
    assert await resolve_address("   ", FakeSession()) is None


# ------------------------------------------------------------------ live off
async def test_live_off_means_seed_or_nothing():
    # The autouse fixture leaves live_data_enabled False; http.fetch returns None
    # without a transport, so an unseeded address simply does not resolve.
    session = FakeSession(address_rows=[[], []])
    assert await resolve_address("10615 Calle Mar de Mariposa", session) is None


async def test_zone_for_zip_returns_none_when_no_zone_lists_it():
    session = FakeSession(zones=[_zone("Z12", ["92130"])])
    assert await zone_for_zip(session, "92101") is None
    assert await zone_for_zip(session, None) is None


# ------------------------------------------------- red team: wildcards and ZIPs
GEOCODER_CHULA_VISTA = {
    # What the City locator really returns for "276 Fourth Ave, Chula Vista, CA
    # 91910": a downtown San Diego address, scored 100.
    "candidates": [
        {
            "address": "276 4TH AVE, 92101",
            "location": {"x": -13042000.0, "y": 3857000.0},
            "score": 100,
            "attributes": {"Postal": "92101", "AddNum": "276", "StName": "4TH", "StType": "AVE"},
        }
    ]
}


async def test_a_typed_percent_is_escaped_before_it_reaches_ilike():
    """ "%" used to match the first row in `addresses` and answer for it.

    FakeSession cannot evaluate a WHERE clause, so the assertion is on the SQL we
    build: the pattern must carry a literal, escaped percent sign.
    """
    from app.live.geocode import escape_like

    assert escape_like("%") == "\\%"
    assert escape_like("100_A St") == "100\\_A St"

    captured = []

    class CapturingSession(FakeSession):
        async def execute(self, stmt):
            captured.append(str(stmt.compile(compile_kwargs={"literal_binds": True})))
            return await super().execute(stmt)

    await resolve_address("%", CapturingSession(address_rows=[[], []]))
    assert any("\\%" in sql for sql in captured), captured


async def test_a_candidate_in_a_different_zip_than_the_resident_typed_is_rejected(live_on):
    """A Chula Vista address must not come back as a downtown San Diego one."""
    http.set_transport(_transport(GEOCODER_CHULA_VISTA))
    assert await geocode("276 Fourth Ave, Chula Vista, CA 91910") is None


async def test_a_candidate_in_the_zip_the_resident_typed_is_kept(live_on):
    http.set_transport(_transport(GEOCODER_OK))
    best = await geocode("10615 Calle Mar de Mariposa, San Diego, CA 92130")
    assert best is not None and best["attributes"]["Postal"] == "92130"


async def test_an_address_with_no_zip_still_geocodes(live_on):
    http.set_transport(_transport(GEOCODER_OK))
    assert await geocode("10615 Calle Mar de Mariposa") is not None
