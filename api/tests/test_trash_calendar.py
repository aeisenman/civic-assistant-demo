"""Week parity, next pickup, the holiday shift, holiday list — all pure date math."""

from datetime import date, timedelta

from app.tools.trash_calendar import (
    HOLIDAYS_2026,
    HOLIDAYS_2027,
    HOLIDAYS_BY_YEAR,
    holiday_name,
    holiday_shift,
    holidays_in,
    next_pickup,
    next_recycling,
    next_weekday_on_or_after,
    remaining_holidays,
    week_letter,
)


def test_week_letter_follows_iso_week_parity():
    # 2026-01-05 is ISO week 2 (even -> B); a week later is week 3 (odd -> A).
    assert week_letter(date(2026, 1, 5)) == "B"
    assert week_letter(date(2026, 1, 12)) == "A"


def test_next_weekday_includes_today():
    wednesday = date(2026, 9, 2)
    assert next_weekday_on_or_after(wednesday, "Wednesday") == wednesday
    assert next_weekday_on_or_after(wednesday, "Monday") == date(2026, 9, 7)


def test_no_shift_in_an_ordinary_week():
    assert holiday_shift(date(2026, 9, 2)) == (date(2026, 9, 2), None)


def test_holiday_earlier_in_the_week_shifts_the_route():
    # Labor Day is Monday 2026-09-07; a Wednesday route that week runs Thursday.
    shifted, name = holiday_shift(date(2026, 9, 9))
    assert shifted == date(2026, 9, 10)
    assert name == "Labor Day"


def test_holiday_later_in_the_week_does_not_shift():
    # Thanksgiving is Thursday 2026-11-26; the Wednesday route is unaffected.
    assert holiday_shift(date(2026, 11, 25)) == (date(2026, 11, 25), None)


def test_holiday_on_its_own_day_shifts_that_day():
    shifted, name = holiday_shift(date(2026, 9, 7))
    assert shifted == date(2026, 9, 8)
    assert name == "Labor Day"


def test_next_pickup_reports_week_and_bins():
    # Zone Z06: Wednesday collection, recycling week B.
    result = next_pickup("Wednesday", "B", date(2026, 9, 1))
    assert result["pickup_date"] == "2026-09-02"
    assert result["week_letter"] == week_letter(date(2026, 9, 2))
    assert result["recycling_this_week"] == (week_letter(date(2026, 9, 2)) == "B")


def test_organics_go_out_every_week_whatever_the_letter():
    # M6: organics are weekly, so no date can ever leave the green bin at home.
    for offset in range(14):
        result = next_pickup("Wednesday", "B", date(2026, 9, 1) + timedelta(days=offset))
        assert result["organics_this_week"] is True


def test_next_pickup_applies_the_holiday_shift():
    result = next_pickup("Wednesday", "B", date(2026, 9, 8))
    assert result["scheduled_date"] == "2026-09-09"
    assert result["pickup_date"] == "2026-09-10"
    assert result["holiday_shift"] == "Labor Day"


def test_next_recycling_is_this_week_when_the_letters_match():
    # 2026-09-02 is ISO week 36 (even -> B), so a week-B zone recycles that day.
    result = next_recycling("Wednesday", "B", date(2026, 9, 1))
    assert result == {
        "next_recycling_date": "2026-09-02",
        "next_recycling_weekday": "Wednesday",
        "next_recycling_holiday_shift": None,
        "recycling_this_week": True,
    }


def test_next_recycling_skips_to_the_following_week_when_they_do_not():
    # 2026-09-16 is week B, so a week-A zone waits until 2026-09-23.
    result = next_recycling("Wednesday", "A", date(2026, 9, 15))
    assert result == {
        "next_recycling_date": "2026-09-23",
        "next_recycling_weekday": "Wednesday",
        "next_recycling_holiday_shift": None,
        "recycling_this_week": False,
    }


def test_next_recycling_carries_the_holiday_shift():
    # Labor Day week: the week-A Wednesday route (2026-09-09) runs Thursday.
    result = next_recycling("Wednesday", "A", date(2026, 9, 8))
    assert result["next_recycling_date"] == "2026-09-10"
    # The date moved, so the weekday has to move with it (2026-09-07 issue 1).
    assert result["next_recycling_weekday"] == "Thursday"
    assert result["next_recycling_holiday_shift"] == "Labor Day"


def test_next_recycling_without_a_week_letter_has_no_date():
    assert next_recycling("Wednesday", None, date(2026, 9, 1)) == {
        "next_recycling_date": None,
        "next_recycling_weekday": None,
        "next_recycling_holiday_shift": None,
        "recycling_this_week": False,
    }


def test_remaining_holidays_starts_at_the_given_date_and_is_ordered():
    holidays = remaining_holidays(date(2026, 9, 1))
    assert [h["name"] for h in holidays[:3]] == [
        "Labor Day",
        "Thanksgiving Day",
        "Christmas Day",
    ]
    assert holidays[0] == {"date": "2026-09-07", "name": "Labor Day", "weekday": "Monday"}
    assert [h["date"] for h in holidays] == sorted(h["date"] for h in holidays)


def test_remaining_holidays_includes_the_day_itself_and_runs_out_eventually():
    assert remaining_holidays(date(2026, 9, 7))[0]["name"] == "Labor Day"
    assert remaining_holidays(date(2027, 12, 26)) == []
    assert len(remaining_holidays(date(2026, 1, 1))) == len(HOLIDAYS_2026) + len(HOLIDAYS_2027)


def test_remaining_holidays_crosses_the_year_boundary():
    """Asked on Boxing Day 2026, the next holiday is New Year's Day 2027."""
    upcoming = remaining_holidays(date(2026, 12, 26))
    assert upcoming[0] == {
        "date": "2027-01-01",
        "name": "New Year's Day",
        "weekday": "Friday",
    }
    assert len(upcoming) == len(HOLIDAYS_2027)


def test_the_calendar_is_looked_up_by_year():
    assert holidays_in(2026) is HOLIDAYS_2026
    assert holidays_in(2027) is HOLIDAYS_2027
    # An unknown year yields no holidays rather than pretending 2026's apply.
    assert holidays_in(2031) == {}
    assert holiday_name(date(2027, 5, 31)) == "Memorial Day"
    assert holiday_name(date(2027, 5, 30)) is None
    assert set(HOLIDAYS_BY_YEAR) == {2026, 2027}


def test_a_2027_holiday_still_shifts_the_route_one_day():
    """Red-team finding 21: a January 2027 pickup was computed with no holidays."""
    # New Year's Day 2027 is a Friday; a Friday route slides to Saturday.
    assert holiday_shift(date(2027, 1, 1)) == (date(2027, 1, 2), "New Year's Day")
    # A Wednesday route the same week is before the holiday, so it does not move.
    assert holiday_shift(date(2026, 12, 30)) == (date(2026, 12, 30), None)


def test_a_pickup_computed_from_new_years_eve_respects_the_2027_calendar():
    result = next_pickup("Friday", "A", date(2026, 12, 31))
    assert result["scheduled_date"] == "2027-01-01"
    assert result["holiday_shift"] == "New Year's Day"
    assert result["pickup_date"] == "2027-01-02"
