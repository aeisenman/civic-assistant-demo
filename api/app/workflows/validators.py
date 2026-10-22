"""Completeness, address and fee checks that decide needs_info vs routed.

Called by the `validating` hook in app/workflows/engine.py, never directly by a
router. Depends on: app.workflows.schemas (required fields), app.tools.fees (the
pure fee rules) and the addresses / permit_types / service_categories seed tables.
Rules come from research/00-synthesis.md §2-§3.
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app import clock
from app.db import models
from app.tools.fees import business_tax_breakdown, permit_fee_breakdown, stro_fee_breakdown
from app.workflows.schemas import required_for

log = logging.getLogger(__name__)

DSD = "Development Services Department"
TREASURER = "Office of the City Treasurer"
UNKNOWN_DEPARTMENT = "City Clerk / General Services"
SD_ZIP = re.compile(r"\b921\d{2}\b")
LATE_FILING_DAYS = 15  # BTC must be filed within 15 days of the business start date

# STRO tier rules, from research/06-parking-utilities-housing.md "Housing".
TIER1_MAX_NIGHTS = 20  # Tier 1 is the part-time tier: 20 nights a year or fewer.
WHOLE_HOME_MIN_NIGHTS = 90  # Tier 3/4 need 90 nights of actual use to keep the licence.
WHOLE_HOME_TIERS = ("tier3", "tier4")
MISSION_BEACH = "mission beach"  # Tier 4 is the Mission Beach Community Planning Area only.

ADDRESS_FIELD = {
    "permit": "project_address",
    "business_tax": "business_address",
    "service_request": "address",
    "stro": "property_address",
}


@dataclass
class ValidationResult:
    """What the validator decided; the engine turns this into the next status."""

    missing: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    fee_cents: int | None = None
    department: str = UNKNOWN_DEPARTMENT
    plans_required: bool | None = None

    @property
    def complete(self) -> bool:
        """True when nothing required is missing — the engine's routed/needs_info fork."""
        return not self.missing


def missing_required(app_type: str, fields: dict) -> list[str]:
    """Required names whose value is absent, null, or blank/whitespace."""
    out = []
    for name in required_for(app_type):
        value = (fields or {}).get(name)
        if value is None or (isinstance(value, str) and not value.strip()):
            out.append(name)
    return out


async def check_address(session: AsyncSession, address: str | None) -> list[str]:
    """Warn (never block) when we cannot place the address in the demo city.

    The demo has 40 fake addresses; a resident's real one will not be among them,
    so this is a warning for staff, not a rejection.
    """
    if not address or not address.strip():
        return []
    # Match the other way round: the table holds "1234 Cedar St" and the form
    # holds "1234 Cedar St, San Diego CA 92101".
    row = (
        (
            await session.execute(
                select(models.Address).where(
                    text(":addr ILIKE '%' || addresses.address || '%'").bindparams(addr=address)
                )
            )
        )
        .scalars()
        .first()
    )
    if row is not None:
        return []
    if SD_ZIP.search(address):
        return ["address not in demo address table"]
    return ["could not confirm the address is inside San Diego city limits"]


def _parse_date(value) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.strip()[:10]).date()
        except ValueError:
            return None
    return None


def late_business_start(start_date: str | date | None, today: date | None = None) -> bool:
    """True when the business started more than 15 days before the filing date."""
    parsed = _parse_date(start_date)
    if parsed is None:
        return False
    return (today or clock.today()) - parsed > timedelta(days=LATE_FILING_DAYS)


async def _validate_permit(session: AsyncSession, result: ValidationResult, fields: dict) -> None:
    result.department = DSD
    query = (fields.get("permit_type") or "").strip()
    if not query:
        return
    permit = (
        (
            await session.execute(
                select(models.PermitType).where(
                    or_(
                        models.PermitType.code == query.upper(),
                        models.PermitType.name.ilike(f"%{query}%"),
                        models.PermitType.code.ilike(f"%{query}%"),
                    )
                )
            )
        )
        .scalars()
        .first()
    )
    if permit is None:
        result.warnings.append(f"permit type '{query}' is not in the City's catalogue")
        return
    breakdown = permit_fee_breakdown(
        permit.base_fee_cents,
        permit.per_1000_valuation_cents,
        permit.requires_plans_over_valuation_cents,
        fields.get("valuation_usd"),
    )
    result.fee_cents = breakdown["total_cents"]
    result.plans_required = breakdown["requires_plans"]


async def _validate_business_tax(session: AsyncSession, result: ValidationResult, fields: dict) -> None:
    result.department = TREASURER
    employees = fields.get("employees")
    if employees is not None:
        result.fee_cents = business_tax_breakdown(int(employees))["total_cents"]
    if late_business_start(fields.get("start_date")):
        result.warnings.append("late application; penalties may apply")


async def _validate_service_request(session: AsyncSession, result: ValidationResult, fields: dict) -> None:
    result.fee_cents = 0
    key = (fields.get("category") or "").strip().lower().replace(" ", "_")
    if not key:
        return
    category = (
        (
            await session.execute(
                select(models.ServiceCategory).where(
                    or_(
                        models.ServiceCategory.category == key,
                        models.ServiceCategory.category.ilike(f"%{key}%"),
                        models.ServiceCategory.label.ilike(f"%{key.replace('_', ' ')}%"),
                    )
                )
            )
        )
        .scalars()
        .first()
    )
    if category is None:
        # An unroutable category is a gap the resident has to fill, not a warning.
        result.missing.append("category")
        result.warnings.append(f"'{fields.get('category')}' is not a known service category")
        return
    result.department = category.department or UNKNOWN_DEPARTMENT


async def _validate_stro(session: AsyncSession, result: ValidationResult, fields: dict) -> None:
    """Tier/residence consistency, the attestation, and the tier's flat fee.

    The four tiers are not interchangeable: they differ by more than $900 and by
    who may live in the unit, so a tier that contradicts the rest of the form is
    sent back as a gap rather than priced. Everything that is merely unusual
    (a Mission Beach address on a Tier 3, a whole-home host who says they live
    there) is a warning for the reviewer, because the ordinance detail the
    resident got wrong might be the address, not the tier.
    """
    result.department = TREASURER
    tier = (fields.get("tier") or "").strip().lower()
    nights = fields.get("nights_offered_per_year")
    onsite = fields.get("host_resides_onsite")
    address = (fields.get("property_address") or "").lower()

    # The City publishes no format for a TOT certificate number
    # (research/06 "What's approximate"), so presence is all that can be checked;
    # REQUIRED_FIELDS already does that. Inventing a pattern would reject real ones.

    if fields.get("attestation_accepted") is not True and "attestation_accepted" not in result.missing:
        result.missing.append("attestation_accepted")

    if (fields.get("unit_type") or "") == "accessory_dwelling_unit":
        result.warnings.append(
            "accessory dwelling units are not eligible for short-term rental under current "
            "City policy, regardless of tier"
        )

    if tier == "tier2":
        if onsite is not True:
            result.missing.append("host_resides_onsite")
            result.warnings.append(
                "Tier 2 is the home-sharing tier and requires the host to live on site; "
                "a whole-home rental is Tier 3, or Tier 4 in Mission Beach"
            )
    elif tier == "tier1":
        if nights is None:
            result.missing.append("nights_offered_per_year")
        elif int(nights) > TIER1_MAX_NIGHTS:
            # The tier is the field that has to change, so that is what is asked for.
            result.missing.append("tier")
            result.warnings.append(
                f"Tier 1 is limited to {TIER1_MAX_NIGHTS} nights a year; {int(nights)} nights "
                "is a Tier 3 licence, or Tier 4 in Mission Beach"
            )
    elif tier in WHOLE_HOME_TIERS:
        if nights is None:
            result.missing.append("nights_offered_per_year")
        elif int(nights) < WHOLE_HOME_MIN_NIGHTS:
            result.warnings.append(
                f"Tier 3 and Tier 4 licences need at least {WHOLE_HOME_MIN_NIGHTS} nights of "
                f"actual rental use a year to keep the licence; {int(nights)} was stated"
            )
        if onsite is True:
            result.warnings.append(
                "a whole-home licence is for a unit the host does not occupy, but this "
                "application says the host lives on site"
            )
        if tier == "tier4" and address and MISSION_BEACH not in address:
            result.warnings.append(
                "Tier 4 covers the Mission Beach Community Planning Area only; this address "
                "does not look like Mission Beach"
            )
        if tier == "tier3" and MISSION_BEACH in address:
            result.warnings.append("a whole-home rental in Mission Beach is a Tier 4 licence, not Tier 3")

    breakdown = stro_fee_breakdown(tier)
    result.fee_cents = breakdown["total_cents"]


_BY_TYPE = {
    "permit": _validate_permit,
    "business_tax": _validate_business_tax,
    "service_request": _validate_service_request,
    "stro": _validate_stro,
}


async def validate(session: AsyncSession, app: models.Application) -> ValidationResult:
    """Run every check for `app.type` and return the decision in one object."""
    fields = app.fields or {}
    result = ValidationResult(missing=missing_required(app.type, fields))
    result.warnings.extend(await check_address(session, fields.get(ADDRESS_FIELD[app.type])))
    handler = _BY_TYPE.get(app.type)
    if handler is not None:
        await handler(session, result, fields)
    log.info(
        "validated %s: missing=%s warnings=%d fee_cents=%s dept=%s",
        app.tracking_number,
        result.missing,
        len(result.warnings),
        result.fee_cents,
        result.department,
    )
    return result
