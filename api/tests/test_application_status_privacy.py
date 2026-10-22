"""get_application_status must not read another resident's details out loud.

Drives app.tools.applications with a fake session holding one fully populated
application row, because red-team finding 2 was that anyone who can guess
PRM-2026-000102 gets the applicant's name and home address. Depends on:
app.tools.applications only — no database, no model.
"""

from datetime import UTC, datetime

from app.tools.applications import (
    NEXT_STEPS,
    TrackingArgs,
    get_application_status,
    get_permit_status,
    next_step_for,
)

# Every applicant-identifying value a permit row can carry, so the assertions can
# look for each of them anywhere in the tool result.
PII = {
    "applicant_name": "Marisol Gutierrez",
    "applicant_address": "4521 Adams Ave, San Diego, CA 92116",
    "applicant_email": "marisol@example.com",
    "applicant_phone": "619-555-0134",
    "apn": "445-820-13-00",
    "contractor_name": "Kevin Park Construction",
}


class _App:
    """Stands in for models.Application: the tool reads these attributes only."""

    tracking_number = "PRM-2026-000101"
    type = "permit"
    status = "in_review"
    department = "Development Services"
    fee_cents = 41102
    missing_fields = ["applicant_address"]
    fields = dict(PII)
    created_at = datetime(2026, 8, 1, 9, 0, tzinfo=UTC)
    updated_at = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)


class _Result:
    def __init__(self, row):
        self._row = row

    def scalars(self):
        return self

    def first(self):
        return self._row


class _Session:
    """Answers every select with the one application row (or with nothing)."""

    def __init__(self, row=None):
        self.row = row
        self.selects = 0

    async def execute(self, stmt, *args, **kwargs):
        self.selects += 1
        return _Result(self.row)


def _flatten(value) -> str:
    """Every string in a nested result, so a leak cannot hide inside a list."""
    if isinstance(value, dict):
        return " ".join(_flatten(v) for v in list(value.keys()) + list(value.values()))
    if isinstance(value, (list, tuple)):
        return " ".join(_flatten(v) for v in value)
    return str(value)


async def test_no_applicant_field_survives_into_the_tool_result():
    result = await get_application_status(TrackingArgs(tracking_number="PRM-2026-000101"), _Session(_App()))
    blob = _flatten(result).lower()
    for value in PII.values():
        assert value.lower() not in blob, f"{value!r} leaked into the tool result"
    assert "fields" not in result
    assert "events" not in result


async def test_the_status_facts_a_resident_actually_needs_are_still_there():
    result = await get_application_status(TrackingArgs(tracking_number="PRM-2026-000101"), _Session(_App()))
    assert result["tracking_number"] == "PRM-2026-000101"
    assert result["type"] == "permit"
    assert result["status"] == "in_review"
    assert result["department"] == "Development Services"
    assert result["fee_usd"] == 411.02
    assert result["created_at"].startswith("2026-08-01")
    assert result["updated_at"].startswith("2026-09-01")
    assert result["next_step"] == NEXT_STEPS["in_review"]
    assert "411.02" in result["summary"]


async def test_a_missing_field_is_named_but_its_value_is_not():
    """ "still needed: applicant_address" is a to-do, not a disclosure."""
    result = await get_application_status(TrackingArgs(tracking_number="PRM-2026-000101"), _Session(_App()))
    assert result["missing_fields"] == ["applicant_address"]
    assert "applicant_address" in result["summary"]
    assert "4521 Adams Ave" not in result["summary"]


async def test_get_permit_status_is_the_same_redacted_lookup():
    permit = await get_permit_status(TrackingArgs(tracking_number="PRM-2026-000101"), _Session(_App()))
    application = await get_application_status(
        TrackingArgs(tracking_number="PRM-2026-000101"), _Session(_App())
    )
    assert permit == application


async def test_an_unknown_tracking_number_still_says_so():
    result = await get_application_status(TrackingArgs(tracking_number="PRM-2026-999999"), _Session(None))
    assert "error" in result
    assert "PRM-2026-999999" in result["error"]


def test_every_workflow_status_has_a_next_step_and_unknowns_fall_back():
    from app.workflows.engine import TRANSITIONS

    for status in TRANSITIONS:
        assert status in NEXT_STEPS, f"no resident-facing next step for {status!r}"
    assert "619-236-5555" in next_step_for("some_status_we_added_later")
