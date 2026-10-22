"""The four live City tools, driven by a mocked httpx transport (no network).

Routes each request by hostname/path to a canned ArcGIS payload copied from the
responses recorded in research/05-live-data-sources.md, so the parsing, the
address-range filter, the seed fallback and the RSS merge are all covered.
"""

import json

import httpx

from app.db import models
from app.live import arcgis, http
from app.live.arcgis import street_name_for_sweeping
from tests.test_live_geocode import FakeSession, _zone

GEOCODER_202_C = {
    "candidates": [
        {
            "address": "202 C ST, 92101",
            "location": {"x": -13042511.42, "y": 3857768.06},
            "score": 100,
            "attributes": {
                "Postal": "92101",
                "AddNum": "202",
                "StName": "C",
                "StType": "ST",
                "StPreDir": "",
            },
        }
    ]
}
DISTRICT_3 = {
    "features": [
        {
            "attributes": {
                "DISTRICT": 3,
                "NAME": "Stephen Whitburn",
                "PHONE": "(619) 236-6633",
                "WEBSITE": "http://www.sandiego.gov/citycouncil/cd3",
            }
        }
    ]
}
ZONING_CCPD = {"features": [{"attributes": {"ZONE_NAME": "CCPD-CORE", "ORDNUM": "O-19471 NS"}}]}
SWEEP_C_ST = {
    "features": [
        {
            "attributes": {
                "RD20FULL": "C ST",
                "LOW_ADDR": 100,
                "HIGH_ADDR": 199,
                "SCHEDULE": "Posted (3am - 6am), NS Mon,Wed & Fri",
                "POSTED": "P",
                "CDCODE": 3,
                "ZIP": 92101,
            }
        },
        {
            "attributes": {
                "RD20FULL": "C ST",
                "LOW_ADDR": 3900,
                "HIGH_ADDR": 3939,
                "SCHEDULE": "Not Posted, Both Sides 1st Mon",
                "POSTED": "NP",
                "CDCODE": 9,
                "ZIP": 92102,
            }
        },
    ]
}
PERMITS_202_C = {
    "features": [
        {
            "attributes": {
                "APPROVAL_ID": "PMT-3222838",
                "APPROVAL_TYPE": "Building Permit",
                "APPROVAL_STATUS": "Cancelled Application Expired",
                "APPROVAL_CREATE_DATE": 1684368000000,
                "APPROVAL_ISSUE_DATE": None,
                "GIS_ADDRESS": "202 C St, San Diego, CA",
            }
        },
    ]
}
AGENDA_RSS = """<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>Tuesday Agenda - Sep 01, 2026</title>
<pubDate>Tue, 01 Sep 2026 10:00:00 -0800</pubDate>
<link>https://sandiego.granicus.com/AgendaViewer.php?view_id=3&amp;clip_id=9484</link></item>
</channel></rss>"""

# One transport for every host: match on the bit of the path that identifies the
# service, which keeps the fixtures readable.
ROUTES = [
    ("DoIT_Public/MapServer/5", DISTRICT_3),
    ("Zoning_Base", ZONING_CCPD),
    ("GeoSweep", SWEEP_C_ST),
    ("DSDPermits", PERMITS_202_C),
]


def _handler(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    if "granicus.com" in url:
        return httpx.Response(200, text=AGENDA_RSS)
    if "GeocodeServer" in url:
        # The real locator only matches a street *address*; "C St downtown" scores
        # in the forties, which resolve_address rejects. Mirror that here, and
        # echo back the house number that was asked for.
        wanted = request.url.params.get("Address", "")
        digits = "".join(c for c in wanted.split()[0] if c.isdigit()) if wanted else ""
        if not digits:
            return httpx.Response(200, json={"candidates": []})
        candidate = json.loads(json.dumps(GEOCODER_202_C))
        candidate["candidates"][0]["attributes"]["AddNum"] = digits
        return httpx.Response(200, json=candidate)
    for fragment, payload in ROUTES:
        if fragment in url:
            return httpx.Response(200, json=payload)
    raise AssertionError(f"unexpected live call: {url}")  # pragma: no cover


def _install():
    http.set_transport(httpx.MockTransport(_handler))


def _seed_session(row=None, **tables):
    """A session whose `addresses` table holds `row` (or nothing) and nothing else."""
    return FakeSession(address_rows=[[row] if row else [], []], **tables)


# ------------------------------------------------------------------ street names
def test_street_name_prefers_the_geocoders_own_parse():
    assert street_name_for_sweeping("202 C St", GEOCODER_202_C["candidates"][0]) == "C ST"


def test_street_name_falls_back_to_normalising_free_text():
    # No house number, so the geocoder scores too low to match: "C St downtown".
    assert street_name_for_sweeping("C St downtown", None) == "C ST"
    assert street_name_for_sweeping("4521 Adams Avenue", None) == "ADAMS AV"
    assert street_name_for_sweeping("Mission Blvd", None) == "MISSION BL"


def test_street_name_gives_up_on_a_number():
    assert street_name_for_sweeping("92101", None) is None


# ------------------------------------------------------------------ district
async def test_council_district_uses_the_live_layer(live_on):
    _install()
    result = await arcgis.get_council_district(
        arcgis.CouncilDistrictArgs(address="202 C St"), _seed_session()
    )
    assert result["source"] == "live"
    assert result["district"] == 3
    assert result["councilmember"] == "Stephen Whitburn"
    assert "live map data" in result["summary"]


async def test_council_district_falls_back_to_seed_when_live_is_off():
    # live_data_enabled stays False (autouse fixture): no HTTP, seed row only.
    row = models.Address(address="7890 Girard Ave", zip="92037", zone_id="Z03", council_district=1)
    session = _seed_session(
        row,
        council_districts=[
            models.CouncilDistrict(
                district=1,
                councilmember="(fictional) Priya Nakamura",
                neighborhoods=["La Jolla"],
            )
        ],
    )
    result = await arcgis.get_council_district(arcgis.CouncilDistrictArgs(address="7890 Girard Ave"), session)
    assert result["source"] == "seed"
    assert result["district"] == 1
    assert "based on demo data" in result["summary"].lower()


# ------------------------------------------------------------------ sweeping
async def test_street_sweeping_narrows_to_the_matching_address_range(live_on):
    _install()
    result = await arcgis.get_street_sweeping(arcgis.AddressArgs(address="150 C St"), _seed_session())
    assert result["matched_block"] is True
    assert [s["block"] for s in result["segments"]] == ["100-199"]
    assert "NS Mon,Wed & Fri" in result["summary"]


async def test_street_sweeping_lists_the_zips_blocks_when_no_range_covers_it(live_on):
    # The City's layer genuinely has no 200-299 segment on C ST in 92101, so the
    # honest answer is every block in that ZIP, flagged as not narrowed.
    _install()
    result = await arcgis.get_street_sweeping(arcgis.AddressArgs(address="202 C St"), _seed_session())
    assert result["matched_block"] is False
    assert [s["zip"] for s in result["segments"]] == ["92101"]


async def test_street_sweeping_filters_by_zip_before_the_address_range(live_on):
    # The live defect this guards: C ST in 92102 has a 0-3849 block that contains
    # 202, so a number-only filter answered a downtown question with City Heights.
    wide = {
        "features": [
            {
                "attributes": {
                    "RD20FULL": "C ST",
                    "LOW_ADDR": 0,
                    "HIGH_ADDR": 3849,
                    "SCHEDULE": "Not Posted, Both Sides 1st Mon",
                    "POSTED": "NP",
                    "CDCODE": 9,
                    "ZIP": 92102,
                }
            },
            *SWEEP_C_ST["features"][:1],
        ]
    }

    def handler(request):
        if "GeocodeServer" in str(request.url):
            return httpx.Response(200, json=GEOCODER_202_C)
        return httpx.Response(200, json=wide)

    http.set_transport(httpx.MockTransport(handler))
    result = await arcgis.get_street_sweeping(arcgis.AddressArgs(address="202 C St"), _seed_session())
    assert [s["zip"] for s in result["segments"]] == ["92101"]
    assert [s["block"] for s in result["segments"]] == ["100-199"]


async def test_street_sweeping_without_a_number_lists_the_blocks(live_on):
    _install()
    result = await arcgis.get_street_sweeping(arcgis.AddressArgs(address="C St downtown"), _seed_session())
    assert result["matched_block"] is False
    assert len(result["segments"]) == 2


async def test_street_sweeping_says_so_when_the_layer_is_empty(live_on):
    http.set_transport(httpx.MockTransport(lambda r: httpx.Response(200, json={"features": []})))
    result = await arcgis.get_street_sweeping(
        arcgis.AddressArgs(address="Calle Mar de Mariposa"), _seed_session()
    )
    assert result["segments"] == []
    assert "no posted route" in result["summary"]


# ------------------------------------------------------------------ zoning
async def test_zoning_reports_the_code_and_the_ordinance(live_on):
    _install()
    result = await arcgis.get_zoning(arcgis.AddressArgs(address="202 C St"), _seed_session())
    assert result["zone"] == "CCPD-CORE"
    assert result["source"] == "live"
    assert "O-19471 NS" in result["summary"]


async def test_zoning_needs_a_point(live_on):
    # A seed match carries no coordinates, so there is nothing to query with.
    row = models.Address(address="7890 Girard Ave", zip="92037", zone_id="Z03", council_district=1)
    _install()
    result = await arcgis.get_zoning(arcgis.AddressArgs(address="7890 Girard Ave"), _seed_session(row))
    assert "couldn't place" in result["error"]


# ------------------------------------------------------------------ permits
async def test_city_permits_return_real_pmt_numbers(live_on):
    _install()
    result = await arcgis.search_city_permits(arcgis.AddressArgs(address="202 C St"), _seed_session())
    assert result["permits"][0]["number"] == "PMT-3222838"
    assert result["permits"][0]["created"] == "2023-05-18"
    assert "PRM-2026- numbers this assistant issues are demo" in result["summary"]


async def test_city_permits_query_is_case_insensitive(live_on):
    # The layer's LIKE is case-sensitive: '%202 C ST%' finds 0 records where
    # '%202 C St%' finds 18. The geocoder always returns upper case.
    seen: list[str] = []

    def handler(request):
        if "GeocodeServer" in str(request.url):
            return httpx.Response(200, json=GEOCODER_202_C)
        seen.append(request.url.params.get("where", ""))
        return httpx.Response(200, json=PERMITS_202_C)

    http.set_transport(httpx.MockTransport(handler))
    await arcgis.search_city_permits(arcgis.AddressArgs(address="202 C St"), _seed_session())
    assert seen == ["UPPER(GIS_ADDRESS) LIKE UPPER('%202 C ST%') ESCAPE '\\'"]


async def test_a_wildcard_address_cannot_dump_the_permit_layer(live_on):
    """A resident address of "%" used to mean LIKE '%%%' — i.e. every row."""
    seen: list[str] = []

    def handler(request):
        if "GeocodeServer" in str(request.url):
            return httpx.Response(200, json={"candidates": []})
        seen.append(request.url.params.get("where", ""))
        return httpx.Response(200, json={"features": []})

    http.set_transport(httpx.MockTransport(handler))
    await arcgis.search_city_permits(arcgis.AddressArgs(address="%_%"), _seed_session())
    # The metacharacters are escaped, and the ESCAPE clause says what \ means.
    assert seen == ["UPPER(GIS_ADDRESS) LIKE UPPER('%\\%\\_\\%%') ESCAPE '\\'"]


async def test_city_permits_report_an_empty_layer_honestly(live_on):
    http.set_transport(httpx.MockTransport(lambda r: httpx.Response(200, json={"features": []})))
    result = await arcgis.search_city_permits(arcgis.AddressArgs(address="1 Nowhere St"), _seed_session())
    assert result["permits"] == []
    assert "no records matching" in result["summary"]


# ------------------------------------------------------------------ agendas
async def test_council_agendas_parse_the_granicus_feed(live_on):
    _install()
    agendas = await arcgis.council_agendas()
    assert agendas[0]["date"] == "2026-09-01"
    assert agendas[0]["source"] == "live"
    assert agendas[0]["department"] == "City Council"


async def test_council_agendas_are_empty_when_live_is_off():
    assert await arcgis.council_agendas() == []


async def test_a_dead_city_service_is_an_answer_not_a_crash(live_on):
    http.set_transport(httpx.MockTransport(lambda r: httpx.Response(500, text="boom")))
    result = await arcgis.get_zoning(arcgis.AddressArgs(address="202 C St"), _seed_session())
    assert "error" in result  # and nothing raised


def test_zone_helper_is_shared_with_the_geocode_tests():
    # Guards the import above: the fixture builder must keep producing zones.
    assert _zone("Z12", ["92130"]).zips == ["92130"]


# ------------------------------------- red team: a dead service is not "no data"
def _dead_transport():
    """Every City call fails, the way a timeout or a 503 does."""

    def handler(request):
        raise httpx.ConnectTimeout("city service down", request=request)

    return httpx.MockTransport(handler)


async def test_street_sweeping_says_the_service_is_down_not_that_there_is_no_route(live_on):
    http.set_transport(_dead_transport())
    result = await arcgis.get_street_sweeping(arcgis.AddressArgs(address="202 C St"), FakeSession())
    assert result["source"] == "unavailable"
    assert "didn't answer" in result["summary"]
    assert "no posted route" not in result["summary"]


async def test_permit_search_says_the_service_is_down_not_that_there_are_no_permits(live_on):
    http.set_transport(_dead_transport())
    result = await arcgis.search_city_permits(arcgis.AddressArgs(address="202 C St"), FakeSession())
    assert result["source"] == "unavailable"
    assert "no records" not in result["summary"]


async def test_an_empty_feature_list_still_means_no_record(live_on):
    """The other half of the distinction: the service answered, with nothing."""
    http.set_transport(httpx.MockTransport(lambda r: httpx.Response(200, json={"features": []})))
    result = await arcgis.search_city_permits(arcgis.AddressArgs(address="202 C St"), FakeSession())
    assert result["source"] == "live"
    assert result["permits"] == []
