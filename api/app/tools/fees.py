"""Fee estimate tools: building permits (valuation-based) and business tax.

Called through app/tools/registry.py by the permits, business and general
profiles. Depends on: the permit_types seed table; the business tax rule is a
pure function so it can be tested without a database (research/00-synthesis.md §3).
"""

import math

from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models

# research/00-synthesis.md §3, all cents.
BTC_SMALL_BASE = 3400  # <=12 employees
BTC_LARGE_BASE = 12500  # >=13 employees
BTC_PER_EMPLOYEE = 500  # >=13 employees only
SB1186_FEE = 400  # accessibility fee, both tiers
MIN_WAGE_PER_EMPLOYEE = 147  # Minimum Wage Enforcement Fee, eff. 7/1/2025
SMALL_TIER_MAX_EMPLOYEES = 12

# Bounds the tools enforce themselves. They are deliberately NOT pydantic
# `Field(ge=..., le=...)`: Bedrock rejects `minimum`/`maximum` in a tool schema
# (DECISIONS.md, "Bedrock switch"), so the check lives in the function and the
# model gets a readable error dict instead of a 400 from the gateway.
# A negative valuation used to be echoed back with a fee; 10^20 employees used
# to get a quote (red-team finding 18).
MAX_EMPLOYEES = 10_000


class PermitFeeArgs(BaseModel):
    permit_type_code_or_name: str = Field(
        description="Permit type code (e.g. NOPLAN) or name (e.g. 'Building Permit with Plans')"
    )
    valuation_usd: float | None = Field(
        default=None, description="Construction valuation in dollars, if the project has one"
    )


class BusinessTaxArgs(BaseModel):
    employees: int = Field(description="Number of employees, including the owner")
    business_type: str | None = Field(default=None, description="What the business does, e.g. 'coffee cart'")


def business_tax_breakdown(employees: int, business_type: str | None = None) -> dict:
    """Pure fee rule so the numbers are testable and the tiers are visible.

    Two tiers: <=12 employees pay a flat base, 13+ pay a higher base plus a
    per-employee charge. Both add SB-1186 and the minimum-wage enforcement fee.
    """
    employees = max(0, int(employees))
    small = employees <= SMALL_TIER_MAX_EMPLOYEES
    base = BTC_SMALL_BASE if small else BTC_LARGE_BASE
    per_employee = 0 if small else BTC_PER_EMPLOYEE * employees
    min_wage = MIN_WAGE_PER_EMPLOYEE * employees
    total = base + per_employee + SB1186_FEE + min_wage

    lines = [
        {"label": "Business tax base", "amount_usd": base / 100},
        {"label": "SB-1186 accessibility fee", "amount_usd": SB1186_FEE / 100},
        {
            "label": f"Minimum Wage Enforcement Fee (${MIN_WAGE_PER_EMPLOYEE / 100:.2f} x {employees})",
            "amount_usd": min_wage / 100,
        },
    ]
    if not small:
        lines.insert(
            1,
            {
                "label": f"Per-employee charge (${BTC_PER_EMPLOYEE / 100:.2f} x {employees})",
                "amount_usd": per_employee / 100,
            },
        )
    return {
        "employees": employees,
        "business_type": business_type,
        "tier": "12 or fewer employees" if small else "13 or more employees",
        "line_items": lines,
        "total_usd": round(total / 100, 2),
        "total_cents": total,
        "summary": (
            f"Estimate for a Business Tax Certificate with {employees} employee(s): "
            + " + ".join(f"${line['amount_usd']:.2f} {line['label'].lower()}" for line in lines)
            + f" = about ${total / 100:.2f} (estimate; the Treasurer issues the exact invoice)."
        ),
    }


# STRO licence fees, all cents. Source: the City Treasurer's short-term
# residential occupancy page, https://www.sandiego.gov/treasurer/short-term-residential-occupancy
# (also linked as sandiego.gov/stro), summarised in
# research/06-parking-utilities-housing.md "Housing".
# The formula is application fee + licence fee, fixed per tier — there is no
# per-night or per-bedroom component, which is why this is a table and not maths.
STRO_FEES_CENTS: dict[str, tuple[int, int]] = {
    "tier1": (3300, 19300),
    "tier2": (3300, 28400),
    "tier3": (4100, 112900),
    "tier4": (4100, 112900),
}
# The Treasurer publishes no review time for a STRO application
# (research/09-resident-forms.md §2, "Treasurer, no published SLA"), so this is a
# stated assumption of the demo, not a City figure. It is quoted as an assumption
# wherever it is shown.
STRO_REVIEW_SLA_DAYS = 30


def stro_fee_breakdown(tier: str | None) -> dict:
    """Application fee + licence fee for one STRO tier; pure, so it is testable.

    An unknown or missing tier returns no total rather than a guess: the four
    tiers differ by more than $900, so quoting the wrong one is worse than
    saying the tier is needed first.
    """
    key = (tier or "").strip().lower()
    fees = STRO_FEES_CENTS.get(key)
    if fees is None:
        message = (
            "I need the licence tier before I can price a short-term rental licence: "
            "Tier 1 (20 nights a year or fewer), Tier 2 (home-sharing, host on site), "
            "Tier 3 (whole-home) or Tier 4 (whole-home in Mission Beach)."
        )
        return {
            "tier": None,
            "line_items": [],
            "total_usd": None,
            "total_cents": None,
            "review_sla_days": STRO_REVIEW_SLA_DAYS,
            "error": message,
            "summary": message,
        }
    application_fee, licence_fee = fees
    total = application_fee + licence_fee
    lines = [
        {"label": "Application fee", "amount_usd": application_fee / 100},
        {"label": "Licence fee", "amount_usd": licence_fee / 100},
    ]
    return {
        "tier": key,
        "line_items": lines,
        "total_usd": round(total / 100, 2),
        "total_cents": total,
        "review_sla_days": STRO_REVIEW_SLA_DAYS,
        "summary": (
            f"Estimate for a {key.replace('tier', 'Tier ')} short-term rental licence: "
            f"${application_fee / 100:,.2f} application fee + ${licence_fee / 100:,.2f} licence "
            f"fee = about ${total / 100:,.2f} (estimate; the City Treasurer issues the exact "
            "invoice). The Treasurer publishes no review time; this demo assumes about "
            f"{STRO_REVIEW_SLA_DAYS} days."
        ),
    }


def permit_fee_breakdown(
    base_fee_cents: int | None,
    per_1000_valuation_cents: int | None,
    requires_plans_over_valuation_cents: int | None,
    valuation_usd: float | None,
) -> dict:
    """Pure permit fee rule, shared by the tool and the workflow validator.

    Base fee plus a per-$1,000-of-valuation charge, rounded up per $1,000 (that
    is how valuation fees are charged), plus whether the project crosses the
    plans-required valuation threshold for its type.
    """
    base = base_fee_cents or 0
    per_1000 = per_1000_valuation_cents or 0
    valuation = float(valuation_usd or 0)
    units = math.ceil(valuation / 1000) if valuation > 0 else 0
    threshold = requires_plans_over_valuation_cents
    return {
        "base_fee_cents": base,
        "per_1000_valuation_cents": per_1000,
        "valuation_usd": valuation or None,
        "valuation_units_of_1000": units,
        "total_cents": base + per_1000 * units,
        "requires_plans": bool(threshold and valuation * 100 > threshold),
        "plans_threshold_cents": threshold,
    }


async def estimate_business_tax(args: BusinessTaxArgs, session: AsyncSession) -> dict:
    """Thin async wrapper, plus the employee-count bound the schema cannot carry."""
    if args.employees > MAX_EMPLOYEES:
        message = (
            f"{args.employees:,} employees is more than this estimator handles "
            f"(up to {MAX_EMPLOYEES:,}). A business that size should call the City "
            "Treasurer on 619-615-1500 for a quote."
        )
        return {"error": message, "summary": message}
    return business_tax_breakdown(args.employees, args.business_type)


async def estimate_permit_fee(args: PermitFeeArgs, session: AsyncSession) -> dict:
    """Base fee plus a per-$1,000-of-valuation charge, rounded up per $1,000."""
    if args.valuation_usd is not None and args.valuation_usd < 0:
        message = (
            f"A project valuation cannot be negative (${args.valuation_usd:,.2f}). "
            "Give me the estimated cost of the work and I'll price the permit."
        )
        return {"error": message, "summary": message}
    query = args.permit_type_code_or_name.strip()
    stmt = select(models.PermitType).where(
        or_(
            models.PermitType.code == query.upper(),
            models.PermitType.name.ilike(f"%{query}%"),
            models.PermitType.code.ilike(f"%{query}%"),
        )
    )
    permit = (await session.execute(stmt)).scalars().first()
    if permit is None:
        message = (
            f"I don't have a permit type matching '{query}'. Known types include Simple Permit, "
            "No-Plan Building Permit, Building Permit with Plans, ADU, Solar PV, Tenant "
            "Improvement, Sign, Grading and Demolition."
        )
        return {"error": message, "summary": message}

    breakdown = permit_fee_breakdown(
        permit.base_fee_cents,
        permit.per_1000_valuation_cents,
        permit.requires_plans_over_valuation_cents,
        args.valuation_usd,
    )
    base = breakdown["base_fee_cents"]
    per_1000 = breakdown["per_1000_valuation_cents"]
    valuation = float(args.valuation_usd or 0)
    units = breakdown["valuation_units_of_1000"]
    total = breakdown["total_cents"]
    threshold = breakdown["plans_threshold_cents"]
    requires_plans = breakdown["requires_plans"]
    plans_note = ""
    if threshold:
        plans_note = (
            f" Plans are required above a ${threshold / 100:,.0f} valuation"
            f" — this project {'does' if requires_plans else 'does not'} exceed it."
        )

    return {
        "code": permit.code,
        "name": permit.name,
        "description": permit.description,
        "base_fee_usd": round(base / 100, 2),
        "valuation_usd": valuation or None,
        "per_1000_valuation_usd": round(per_1000 / 100, 2) if per_1000 else None,
        "valuation_units_of_1000": units,
        "estimated_total_usd": round(total / 100, 2),
        "typical_turnaround_days": permit.typical_turnaround_days,
        "requires_plans": requires_plans,
        "summary": (
            f"Estimate for a {permit.name}: ${base / 100:,.2f} base"
            + (f" + ${per_1000 / 100:,.2f} per $1,000 of valuation x {units}" if per_1000 else "")
            + f" = about ${total / 100:,.2f} (estimate only; DSD issues the exact invoice)."
            + f" Typical turnaround {permit.typical_turnaround_days} days."
            + plans_note
        ),
    }
