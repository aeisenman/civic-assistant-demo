"""The tool catalogue: name -> pydantic input model + async function.

Called by app/agents/chat.py (schemas for the model, dispatch for the calls) and
by app/agents/profiles.py (which names each intent is allowed to use). Depends
on: the domain modules in this package. Derives JSON schemas from pydantic so
the model contract and the validation can never drift apart.
"""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.live import arcgis, search
from app.tools import applications, civic, fees, trash

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ToolSpec:
    """One callable tool: what the model sees and what actually runs."""

    name: str
    description: str
    model: type[BaseModel]
    fn: Callable[[Any, AsyncSession], Awaitable[dict]]


def _spec(name: str, description: str, model: type[BaseModel], fn) -> ToolSpec:
    return ToolSpec(name=name, description=description, model=model, fn=fn)


TOOLS: dict[str, ToolSpec] = {
    t.name: t
    for t in [
        _spec(
            "get_trash_schedule",
            "Look up the trash/recycling/organics collection schedule for a street address.",
            trash.TrashScheduleArgs,
            trash.get_trash_schedule,
        ),
        _spec(
            "get_next_pickup",
            "Get the next collection date for an address, including holiday shifts and "
            "whether recycling or organics goes out that week.",
            trash.NextPickupArgs,
            trash.get_next_pickup,
        ),
        _spec(
            "get_holiday_schedule",
            "List the City collection holidays still to come and the one-day shift rule. "
            "Use this for holiday questions when no address has been given.",
            trash.HolidayScheduleArgs,
            trash.get_holiday_schedule,
        ),
        _spec(
            "get_permit_status",
            "Look up a building permit by its tracking number (PRM-2026-000101).",
            applications.TrackingArgs,
            applications.get_permit_status,
        ),
        _spec(
            "get_application_status",
            "Look up any application — permit, business tax certificate or service request "
            "— by its tracking number.",
            applications.TrackingArgs,
            applications.get_application_status,
        ),
        _spec(
            "estimate_permit_fee",
            "Estimate the fee for a permit type, optionally using a project valuation.",
            fees.PermitFeeArgs,
            fees.estimate_permit_fee,
        ),
        _spec(
            "estimate_business_tax",
            "Estimate the Business Tax Certificate fee from the employee count.",
            fees.BusinessTaxArgs,
            fees.estimate_business_tax,
        ),
        _spec(
            "search_events",
            "Search upcoming City events, meetings, markets and library programs.",
            civic.SearchEventsArgs,
            civic.search_events,
        ),
        _spec(
            "get_council_district",
            "Find the council district and councilmember for a street address, from the "
            "City's live district map where possible.",
            arcgis.CouncilDistrictArgs,
            arcgis.get_council_district,
        ),
        _spec(
            "get_street_sweeping",
            "Look up the City's posted street-sweeping schedule for a street or address "
            "(when the resident has to move their car).",
            arcgis.AddressArgs,
            arcgis.get_street_sweeping,
        ),
        _spec(
            "get_zoning",
            "Look up the City zoning code at a street address from the live zoning map.",
            arcgis.AddressArgs,
            arcgis.get_zoning,
        ),
        _spec(
            "search_city_permits",
            "Search the City's real permit records (PMT- numbers) filed at a street address.",
            arcgis.AddressArgs,
            arcgis.search_city_permits,
        ),
        _spec(
            "search_city_website",
            "Last resort: search sandiego.gov and read the top pages. Use only when the "
            "sources and the other tools do not cover the question.",
            search.SearchArgs,
            search.search_city_website,
        ),
        _spec(
            "get_referral",
            "Find the outside agency that handles something the City does not "
            "(dog licences, voter registration, seller's permits, DMV, courts).",
            civic.ReferralArgs,
            civic.get_referral,
        ),
        _spec(
            "start_application",
            "Open the inline application form for a permit, business tax certificate or "
            "service request so the resident can fill it in.",
            applications.StartApplicationArgs,
            applications.start_application,
        ),
        _spec(
            "create_service_request",
            "File a Get It Done service request (pothole, graffiti, missed collection, "
            "broken container, streetlight) and return the tracking number.",
            applications.ServiceRequestArgs,
            applications.create_service_request,
        ),
    ]
}


def openai_schemas(names: list[str]) -> list[dict]:
    """OpenAI-protocol tool definitions for `names`, unknown names ignored."""
    out = []
    for name in names:
        spec = TOOLS.get(name)
        if spec is None:
            log.warning("openai_schemas: unknown tool %s", name)
            continue
        out.append(
            {
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": spec.model.model_json_schema(),
                },
            }
        )
    return out


async def dispatch(name: str, arguments: dict, session: AsyncSession) -> dict:
    """Validate and run one tool call. Never raises: the loop needs a result dict.

    A small model that invents a tool name or drops a required argument should
    get a readable error back and another turn, not a 500 for the resident.
    """
    spec = TOOLS.get(name)
    if spec is None:
        return {"error": f"unknown tool '{name}'", "summary": f"unknown tool '{name}'"}
    try:
        args = spec.model.model_validate(arguments or {})
    except ValidationError as exc:
        message = f"invalid arguments for {name}: {exc.errors(include_url=False)}"
        return {"error": message, "summary": message}
    try:
        return await spec.fn(args, session)
    except Exception as exc:  # noqa: BLE001 - a tool failure is an answer, not a crash
        log.exception("tool %s failed", name)
        message = f"{name} failed: {exc}"
        return {"error": message, "summary": message}
