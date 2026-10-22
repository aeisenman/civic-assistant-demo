"""The City clock: one zone, and the two places a UTC day used to be wrong.

Pure unit tests over app.clock, app.workflows.store and app.tools.trash with the
clock frozen at 2026-12-31 23:30 Pacific — the moment the old `date.today()` in a
UTC container said 2027-01-01. Depends on: nothing but the modules under test.
"""

from datetime import UTC, date, datetime

from app import clock
from app.agents import rendering
from app.tools import trash as trash_tool
from app.workflows import store, validators

# 23:30 on New Year's Eve, Pacific. In UTC this is 2027-01-01 07:30 — the exact
# window in which the reviewer's finding #6 said a permit would be minted
# `PRM-2027-…` and the prompt would name the wrong weekday.
NEW_YEARS_EVE = datetime(2026, 12, 31, 23, 30, tzinfo=clock.CITY_TZ)


def freeze(monkeypatch, moment: datetime) -> None:
    """Pin app.clock.now; today() reads it through the module, so both move."""
    monkeypatch.setattr(clock, "now", lambda: moment)


class _SequenceSession:
    """Answers nextval() with a fixed number; the year is what is under test."""

    async def execute(self, statement, *args, **kwargs):
        class _R:
            def scalar_one(self):
                return 400

        return _R()


def test_the_city_clock_is_pacific():
    assert str(clock.CITY_TZ) == "America/Los_Angeles"
    assert clock.now().tzinfo is clock.CITY_TZ
    assert clock.today() == clock.now().date()


def test_a_tracking_number_minted_at_2330_on_new_years_eve_still_says_2026(monkeypatch):
    """UTC had already rolled over; the City had not, and the City mints the number."""
    freeze(monkeypatch, NEW_YEARS_EVE)
    assert NEW_YEARS_EVE.astimezone(UTC).year == 2027
    assert clock.today() == date(2026, 12, 31)


async def test_the_tracking_number_year_comes_from_the_city_clock(monkeypatch):
    freeze(monkeypatch, NEW_YEARS_EVE)
    number = await store.next_tracking_number(_SequenceSession(), "permit")
    assert number == "PRM-2026-000400"
    assert "-2027-" not in number


def test_the_prompt_names_the_city_weekday(monkeypatch):
    """2026-12-31 is a Thursday in San Diego and a Friday in UTC at 23:30 PT."""
    freeze(monkeypatch, NEW_YEARS_EVE)
    line = rendering.today_line()
    assert "Thursday" in line
    assert "2026-12-31" in line
    assert "America/Los_Angeles" in line


def test_the_trash_tool_reads_the_same_clock(monkeypatch):
    """get_next_pickup with no date argument starts from the City's today."""
    freeze(monkeypatch, NEW_YEARS_EVE)
    assert trash_tool.clock.today() == date(2026, 12, 31)


def test_the_late_filing_check_reads_the_same_clock(monkeypatch):
    """A business that started 16 City-days ago is late; 14 is not."""
    freeze(monkeypatch, NEW_YEARS_EVE)
    assert validators.late_business_start("2026-12-10") is True
    assert validators.late_business_start("2026-12-25") is False
