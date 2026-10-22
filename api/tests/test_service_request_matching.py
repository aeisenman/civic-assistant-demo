"""create_service_request must not file a case under a category nobody named,
and its summary must carry the department the category row actually holds.

Drives app.tools.applications with a fake session, because both defects are in
this function: an empty category matched the first row through ILIKE and filed a
*pothole*, a "%" reached the database as a wildcard, and in the M23 run the model
renamed the department because the summary buried it mid-sentence. Depends on:
app.tools.applications, app.db.models and a stubbed workflow engine.
"""

import json
import pathlib

from app.tools import applications as tool_module
from app.tools.applications import ServiceRequestArgs, create_service_request

SERVICE_CATEGORIES = json.loads(
    (pathlib.Path(__file__).resolve().parents[1] / "seed_data" / "service_categories.json").read_text()
)


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return list(self._rows)


class _Session:
    """Records the SQL it is handed and answers the category-list select only."""

    def __init__(self):
        self.sql: list[str] = []

    async def execute(self, stmt, *args, **kwargs):
        self.sql.append(str(stmt.compile(compile_kwargs={"literal_binds": True})))
        # The "which categories exist" select is the only one these tests answer;
        # every lookup select returns nothing, which is the point.
        return _Result(["pothole", "graffiti_removal"] if "LIMIT" in self.sql[-1] else [])


async def test_a_blank_category_is_refused_rather_than_filed_as_the_first_row():
    session = _Session()
    result = await create_service_request(ServiceRequestArgs(category="", address="4521 Adams Ave"), session)
    assert "error" in result
    assert "tracking_number" not in result
    assert "pothole" in result["error"]  # it lists the real options instead
    # No ILIKE lookup was even attempted for an empty category.
    assert not any("ilike" in sql.lower() for sql in session.sql)


async def test_a_wildcard_category_reaches_the_database_escaped():
    session = _Session()
    result = await create_service_request(ServiceRequestArgs(category="%", address="4521 Adams Ave"), session)
    assert "error" in result
    assert "isn't a category I can file" in result["error"]
    assert any("\\%" in sql for sql in session.sql), session.sql


# ------------------------------------------- M27: the department is the tool's, verbatim
class _Row:
    """The four fields of models.ServiceCategory that create_service_request reads."""

    def __init__(self, row: dict):
        self.category = row["category"]
        self.label = row["label"]
        self.department = row["department"]
        self.sla_days = row["sla_days"]


class _MatchingSession(_Session):
    """Answers the category lookup with one seeded row; every other select is empty."""

    def __init__(self, row: _Row):
        super().__init__()
        self.row = row

    async def execute(self, stmt, *args, **kwargs):
        self.sql.append(str(stmt.compile(compile_kwargs={"literal_binds": True})))
        if "service_categories" in self.sql[-1]:
            return _Result([self.row])
        return _Result([])


class _FiledApplication:
    tracking_number = "SR-2026-000123"
    status = "submitted"


async def _file(monkeypatch, row: dict) -> dict:
    """File one case against a stubbed engine.submit and return the tool result."""

    async def _submit(session, type_, fields):
        return _FiledApplication()

    monkeypatch.setattr(tool_module.engine, "submit", _submit)
    session = _MatchingSession(_Row(row))
    return await create_service_request(
        ServiceRequestArgs(category=row["category"], address="4521 Adams Ave"), session
    )


async def test_the_summary_states_the_department_from_the_category_row(monkeypatch):
    """The reply is told to quote this verbatim, so it has to be there to quote."""
    encampment = next(r for r in SERVICE_CATEGORIES if r["category"] == "homeless_encampment")
    result = await _file(monkeypatch, encampment)

    assert result["department"] == encampment["department"]
    # The M23 defect: the reply said "Homelessness Strategies and Solutions
    # Department", which is not what the table holds. The summary now carries the
    # row's own spelling, ampersand and abbreviation included.
    assert f"Department: {encampment['department']}" in result["summary"]
    assert str(encampment["sla_days"]) in result["summary"]
    assert "SR-2026-000123" in result["summary"]


async def test_every_seeded_category_puts_its_own_department_in_the_summary(monkeypatch):
    """Not only the row that broke: all twenty-one of them, "other" included."""
    for row in SERVICE_CATEGORIES:
        result = await _file(monkeypatch, row)
        assert f"Department: {row['department']}" in result["summary"], row["category"]
        assert f"Target response time: {row['sla_days']} day(s)" in result["summary"]
