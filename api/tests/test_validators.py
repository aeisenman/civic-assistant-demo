"""Validation rules: what is missing, what is only a warning, what the fee is.

The database-backed lookups are exercised through a fake session that returns a
fixed row, so these stay offline; the fee maths is pure and tested directly.
"""

from datetime import date

from app.tools.fees import permit_fee_breakdown
from app.workflows import validators


class FakeResult:
    def __init__(self, row):
        self._row = row

    def scalars(self):
        return self

    def first(self):
        return self._row


class FakeSession:
    """Returns the same row for every query; enough for one lookup per test."""

    def __init__(self, row=None):
        self.row = row

    async def execute(self, statement, *args, **kwargs):
        return FakeResult(self.row)


def test_missing_required_catches_absent_and_blank():
    fields = {
        "applicant_name": "Maria Lopez",
        "project_address": "  ",
        "permit_type": None,
        "project_description": "Kitchen remodel",
    }
    assert validators.missing_required("permit", fields) == [
        "project_address",
        "permit_type",
        "valuation_usd",
    ]


def test_missing_required_accepts_a_complete_service_request():
    fields = {"category": "pothole", "address": "1234 Cedar St", "description": "Deep pothole"}
    assert validators.missing_required("service_request", fields) == []


def test_zero_is_present_not_missing():
    """0 employees is an answer; only None and blank strings are gaps."""
    fields = {
        "business_name": "A",
        "owner_name": "B",
        "business_address": "C",
        "start_date": "2026-09-01",
        "business_type": "cafe",
        "employees": 0,
        "ownership_type": "llc",
    }
    assert validators.missing_required("business_tax", fields) == []


async def test_known_address_produces_no_warning():
    session = FakeSession(row=object())
    assert await validators.check_address(session, "1234 Cedar St, San Diego CA 92101") == []


async def test_unknown_address_with_a_san_diego_zip_is_a_soft_warning():
    warnings = await validators.check_address(FakeSession(), "99 Nowhere Ave, San Diego CA 92101")
    assert warnings == ["address not in demo address table"]


async def test_address_outside_the_city_says_so():
    warnings = await validators.check_address(FakeSession(), "1 Main St, Reno NV 89501")
    assert warnings == ["could not confirm the address is inside San Diego city limits"]


async def test_blank_address_is_left_to_the_missing_check():
    assert await validators.check_address(FakeSession(), None) == []


def test_late_business_start_uses_the_fifteen_day_rule():
    today = date(2026, 9, 2)
    assert validators.late_business_start("2026-08-01", today) is True
    assert validators.late_business_start("2026-08-25", today) is False
    assert validators.late_business_start("2026-09-15", today) is False
    assert validators.late_business_start(None, today) is False
    assert validators.late_business_start("not a date", today) is False


async def test_business_tax_validation_warns_about_a_late_filing():
    result = validators.ValidationResult()
    await validators._validate_business_tax(
        FakeSession(), result, {"employees": 4, "start_date": "2020-01-01"}
    )
    assert result.department == validators.TREASURER
    assert result.warnings == ["late application; penalties may apply"]
    # 4 employees: $34 base + $4 SB-1186 + 4 x $1.47 minimum wage fee.
    assert result.fee_cents == 3400 + 400 + 4 * 147


def test_plans_required_follows_the_valuation_threshold():
    over = permit_fee_breakdown(41102, None, 6_000_000, 80_000)
    under = permit_fee_breakdown(41102, None, 6_000_000, 45_000)
    assert over["requires_plans"] is True
    assert under["requires_plans"] is False
    assert over["total_cents"] == 41102


def test_valuation_fee_is_charged_per_whole_thousand():
    breakdown = permit_fee_breakdown(0, 4, None, 185_500)
    assert breakdown["valuation_units_of_1000"] == 186
    assert breakdown["total_cents"] == 744
    assert breakdown["requires_plans"] is False
