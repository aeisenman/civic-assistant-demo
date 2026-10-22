"""The City's wall clock: `now()` and `today()` in America/Los_Angeles.

Called by everything that produces a resident-facing date — the trash tools, the
tracking-number year, the certificate issue date, the business-tax late-filing
check and the prompt's "Today is …" line. Depends on: zoneinfo (stdlib) only, so
it imports from a unit test as happily as from the container.

Why it exists: the API container has no TZ, so `date.today()` is UTC. Between
5 pm and midnight Pacific that is already tomorrow — the prompt said "Today is
Monday" while the trash tool answered for Tuesday, and on 31 December at 5 pm PT
a permit would have been minted `PRM-2027-…`. One helper, one zone, and bare
`date.today()` is out of resident-facing code.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

#: The City runs on Pacific time; every resident-facing date is in this zone.
CITY_TZ = ZoneInfo("America/Los_Angeles")


def now() -> datetime:
    """The current moment as a timezone-aware datetime in America/Los_Angeles.

    Monkeypatch this one function to freeze the clock in a test: `today()` reads
    it through the module namespace, so both move together.
    """
    return datetime.now(CITY_TZ)


def today() -> date:
    """The current calendar date in America/Los_Angeles."""
    return now().date()
