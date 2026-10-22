"""get_holiday_schedule: the address-free answer to "is pickup delayed for Labor Day?".

Calls the tool through the registry so the schema and the dispatch path are covered
too. It touches no tables, so `session` is None throughout.
"""

from app.agents.profiles import profile_for
from app.tools.registry import TOOLS, dispatch


async def test_holiday_schedule_lists_the_holidays_from_a_date():
    result = await dispatch("get_holiday_schedule", {"date": "2026-09-01"}, None)
    assert [h["name"] for h in result["holidays"][:3]] == [
        "Labor Day",
        "Thanksgiving Day",
        "Christmas Day",
    ]
    assert "Labor Day Monday 2026-09-07" in result["summary"]
    assert "one day later" in result["shift_rule"]


async def test_holiday_schedule_needs_no_arguments():
    # The point of the tool: a holiday question arrives with no address and no date.
    result = await dispatch("get_holiday_schedule", {}, None)
    assert "error" not in result
    assert result["from_date"]


async def test_holiday_schedule_rejects_an_unreadable_date():
    result = await dispatch("get_holiday_schedule", {"date": "next Tuesday"}, None)
    assert "not a date I can read" in result["error"]


async def test_holiday_schedule_rolls_into_the_next_year():
    """Asked after Christmas, the answer is January's dates, not an empty list."""
    result = await dispatch("get_holiday_schedule", {"date": "2026-12-26"}, None)
    assert result["holidays"][0]["date"] == "2027-01-01"
    assert "New Year's Day Friday 2027-01-01" in result["summary"]


async def test_holiday_schedule_says_so_when_the_calendar_runs_out():
    result = await dispatch("get_holiday_schedule", {"date": "2028-01-01"}, None)
    assert result["holidays"] == []
    assert "none left on the published calendar" in result["summary"]


def test_the_trash_profile_can_call_it():
    assert "get_holiday_schedule" in TOOLS
    assert "get_holiday_schedule" in profile_for("trash").tools


async def test_a_date_outside_the_calendar_is_a_readable_error_not_an_overflow():
    """`9999-12-31` used to surface "get_next_pickup failed: date value out of range"."""
    result = await dispatch("get_holiday_schedule", {"date": "9999-12-31"}, None)
    assert "error" in result
    assert "calendar" in result["error"]
    assert "out of range" not in result["error"]
