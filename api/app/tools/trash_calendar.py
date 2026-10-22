"""Pure date math for collection days: week parity, next pickup, holiday shift.

Called by app/tools/trash.py; no database, no I/O, so tests exercise it directly.
Depends on: nothing but the stdlib. Trash and organics run every week; only
recycling alternates (week A = odd ISO week, B = even), and a weekday holiday
earlier in the week pushes the route one day later.
"""

from datetime import date, timedelta

# The five days ESD actually skips collection in 2026, taken from
# sandiego.gov/environmental-services/collection/schedule (research/05, checked
# 2026-09-05). M8 removed MLK Day, Presidents' Day and the July 4th observance:
# City offices close on those, but the collection trucks still run, and telling a
# resident otherwise makes them miss a week.
HOLIDAYS_2026: dict[date, str] = {
    date(2026, 1, 1): "New Year's Day",
    date(2026, 5, 25): "Memorial Day",
    date(2026, 9, 7): "Labor Day",
    date(2026, 11, 26): "Thanksgiving Day",
    date(2026, 12, 25): "Christmas Day",
}

# The same five days in 2027. A pickup asked about on 2026-12-31 already lands in
# January 2027, and with only the 2026 table it was computed as if New Year's Day
# did not exist (red-team finding 21).
HOLIDAYS_2027: dict[date, str] = {
    date(2027, 1, 1): "New Year's Day",
    date(2027, 5, 31): "Memorial Day",
    date(2027, 9, 6): "Labor Day",
    date(2027, 11, 25): "Thanksgiving Day",
    date(2027, 12, 25): "Christmas Day",
}

# Looked up by year so adding 2028 is one line and no caller changes. A year we
# have no table for yields no holidays, which is the honest answer: we would
# rather give a resident an unshifted date than invent a closure.
HOLIDAYS_BY_YEAR: dict[int, dict[date, str]] = {
    2026: HOLIDAYS_2026,
    2027: HOLIDAYS_2027,
}


def holidays_in(year: int) -> dict[date, str]:
    """The collection holidays we have on file for one calendar year."""
    return HOLIDAYS_BY_YEAR.get(year, {})


def holiday_name(day: date) -> str | None:
    """The collection-holiday name for one date, or None."""
    return holidays_in(day.year).get(day)


WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


def week_letter(day: date) -> str:
    """A on odd ISO weeks, B on even ones — the alternating recycling cadence."""
    return "A" if day.isocalendar().week % 2 == 1 else "B"


def next_weekday_on_or_after(start: date, weekday_name: str) -> date:
    """The next `weekday_name` at or after `start` (same day counts)."""
    target = WEEKDAYS[weekday_name.strip().lower()]
    return start + timedelta(days=(target - start.weekday()) % 7)


def holiday_shift(pickup: date) -> tuple[date, str | None]:
    """Shift one day later if a weekday holiday falls in that week, at or before.

    Returns (effective date, holiday name or None). Only one shift: the city
    slides the whole remaining week by a single day, never two.
    """
    monday = pickup - timedelta(days=pickup.weekday())
    for offset in range(5):  # Monday..Friday only; weekend holidays move no route
        day = monday + timedelta(days=offset)
        if day > pickup:
            break
        name = holiday_name(day)
        if name:
            return pickup + timedelta(days=1), name
    return pickup, None


def next_pickup(
    trash_day: str,
    recycling_week: str | None,
    on_or_after: date,
) -> dict:
    """Everything get_next_pickup needs: date, what goes out, any holiday shift.

    Organics go out every week with trash (real ESD policy), so a zone's legacy
    `organics_week` letter is not a parameter here — it is never read.
    """
    scheduled = next_weekday_on_or_after(on_or_after, trash_day)
    effective, holiday = holiday_shift(scheduled)
    letter = week_letter(scheduled)
    return {
        "scheduled_date": scheduled.isoformat(),
        "pickup_date": effective.isoformat(),
        "weekday": effective.strftime("%A"),
        "iso_week": scheduled.isocalendar().week,
        "week_letter": letter,
        "recycling_this_week": recycling_week == letter,
        "organics_this_week": True,
        "holiday_shift": holiday,
    }


def next_recycling(trash_day: str, recycling_week: str | None, on_or_after: date) -> dict:
    """The next collection day that is also a recycling week, at most 2 weeks out.

    get_trash_schedule needs a real date so it can say "next on 2026-09-16"
    instead of making the resident work out a week letter for themselves.

    The weekday and the holiday name are returned alongside the date because the
    date is the *shifted* one: during Labor Day week a Wednesday route runs on a
    Thursday, and a summary that pairs "every other Wednesday" with a shifted
    date led the model to write "Wednesday, September 10" for 2026-09-10, which
    is a Thursday (2026-09-07 verification, issue 1).
    """
    if recycling_week is None:
        return {
            "next_recycling_date": None,
            "next_recycling_weekday": None,
            "next_recycling_holiday_shift": None,
            "recycling_this_week": False,
        }
    first = next_weekday_on_or_after(on_or_after, trash_day)
    day = first if week_letter(first) == recycling_week else first + timedelta(days=7)
    effective, holiday = holiday_shift(day)
    return {
        "next_recycling_date": effective.isoformat(),
        "next_recycling_weekday": effective.strftime("%A"),
        "next_recycling_holiday_shift": holiday,
        "recycling_this_week": day == first,
    }


def remaining_holidays(on_or_after: date) -> list[dict]:
    """City holidays still to come, earliest first — the holiday tool's payload.

    Spans every year on file, so a question asked in late December lists the
    January dates instead of returning an empty list.
    """
    every: dict[date, str] = {}
    for table in HOLIDAYS_BY_YEAR.values():
        every.update(table)
    return [
        {"date": day.isoformat(), "name": name, "weekday": day.strftime("%A")}
        for day, name in sorted(every.items())
        if day >= on_or_after
    ]
