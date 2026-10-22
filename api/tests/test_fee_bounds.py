"""The fee estimators refuse impossible inputs instead of quoting a number.

Drives the two async tool functions in app.tools.fees; estimate_permit_fee never
reaches the database because the bound is checked first, so a fake session that
would fail if used is exactly the right stub. Depends on: app.tools.fees.

The bounds live in the function, not in `Field(ge=..., le=...)`: Bedrock rejects
`minimum`/`maximum` in a tool schema (DECISIONS.md, "Bedrock switch").
"""

from app.tools.fees import (
    MAX_EMPLOYEES,
    BusinessTaxArgs,
    PermitFeeArgs,
    estimate_business_tax,
    estimate_permit_fee,
)


class _ExplodingSession:
    """Any query at all is a failure: the guard must run before the lookup."""

    async def execute(self, *args, **kwargs):
        raise AssertionError("the bound should have been checked before any SQL")


def test_neither_argument_model_carries_a_numeric_bound():
    """A `minimum` or `maximum` keyword in either schema would 400 on Bedrock."""
    for model in (PermitFeeArgs, BusinessTaxArgs):
        schema = str(model.model_json_schema())
        assert "minimum" not in schema, model.__name__
        assert "maximum" not in schema, model.__name__
        assert "exclusiveMinimum" not in schema, model.__name__


async def test_a_negative_valuation_is_refused_not_echoed_back():
    result = await estimate_permit_fee(
        PermitFeeArgs(permit_type_code_or_name="NOPLAN", valuation_usd=-5000),
        _ExplodingSession(),
    )
    assert "error" in result
    assert "cannot be negative" in result["error"]
    assert "estimated_total_usd" not in result
    assert result["summary"] == result["error"]


async def test_a_zero_valuation_is_still_a_real_question():
    """Zero is not negative: a permit with no valuation still has a base fee."""
    session = _ExplodingSession()
    try:
        await estimate_permit_fee(PermitFeeArgs(permit_type_code_or_name="NOPLAN", valuation_usd=0), session)
    except AssertionError:
        pass  # it got as far as the lookup, which is what we wanted to prove
    else:
        raise AssertionError("zero valuation was refused by the bound")


async def test_an_absurd_employee_count_is_refused():
    result = await estimate_business_tax(BusinessTaxArgs(employees=10**20), _ExplodingSession())
    assert "error" in result
    assert "total_usd" not in result
    assert "619-615-1500" in result["error"]


async def test_the_employee_bound_is_inclusive():
    ok = await estimate_business_tax(BusinessTaxArgs(employees=MAX_EMPLOYEES), _ExplodingSession())
    assert ok["total_usd"] > 0
    too_many = await estimate_business_tax(BusinessTaxArgs(employees=MAX_EMPLOYEES + 1), _ExplodingSession())
    assert "error" in too_many
