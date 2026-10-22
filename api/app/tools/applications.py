"""Application tools: status lookups, starting a form, filing a service request.

Called through app/tools/registry.py by the permits, business, service_request
and general profiles. Depends on: app.db.models, app.workflows.engine (so a
service request filed from chat goes through exactly the same state machine as
one filed from a form or a PDF) and app.api.forms for the schema
start_application hands back to the UI.
"""

from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.forms import FORM_SCHEMAS
from app.db import models
from app.live.geocode import escape_like
from app.workflows import engine

# The resident-facing next step for each workflow status. The status word alone
# ("routed") means nothing to a resident, and the tool used to hand the model the
# whole transition log instead — which carried staff actor names and notes.
NEXT_STEPS: dict[str, str] = {
    "draft": "It has not been submitted yet — finish and submit the form.",
    "submitted": "It is queued for validation; no action needed right now.",
    "validating": "The City is checking the form for missing fields.",
    "needs_info": "The City needs more information before it can go further.",
    "routed": "It has been sent to the reviewing department.",
    "in_review": "A reviewer has it now; watch for an approval or a request for more detail.",
    "approved": "Approved — the certificate or permit is being issued.",
    "issued": "Issued. The certificate is available from the City.",
    "rejected": "It was rejected; contact the department for the reason.",
    "closed": "This one is closed; nothing further is expected.",
}


def next_step_for(status: str) -> str:
    """What the resident should expect next, in plain words.

    Residents ask "what happens now", not "what is the enum". Falling back to a
    generic line keeps a new status from producing an empty answer.
    """
    return NEXT_STEPS.get(status, "The City is working on it; call 619-236-5555 for the current step.")


class TrackingArgs(BaseModel):
    tracking_number: str = Field(
        description=(
            "Tracking number, e.g. PRM-2026-000101, BTC-2026-000201, SR-2026-000301 or STR-2026-000401"
        )
    )


class StartApplicationArgs(BaseModel):
    type: Literal["permit", "business_tax", "service_request", "stro"] = Field(
        description=(
            "Which application form the resident wants to fill in. 'stro' is the Short-Term "
            "Residential Occupancy licence for a short-term or vacation rental."
        )
    )


class ServiceRequestArgs(BaseModel):
    category: str = Field(
        description="Service category, e.g. pothole, graffiti_removal, missed_pickup, container_issue"
    )
    address: str = Field(description="Where the problem is")
    # M10: this was required, so the model stopped to ask "describe the pothole" when it
    # already had the category and the address. The workflow validator only ever needed an
    # address, so an optional field is both honest and the thing that lets the tool run now.
    description: str = Field(
        default="",
        description=(
            "What the resident reported, in their words. Optional: if they only named the "
            "problem, leave this out and file the case now rather than asking for detail."
        ),
    )
    contact_email: str | None = Field(default=None, description="Optional email for status updates")


async def get_application_status(args: TrackingArgs, session: AsyncSession) -> dict:
    """Status, department, fee and next step for one tracking number — and no PII.

    Anyone can guess PRM-2026-000102 from PRM-2026-000101, and nothing ties a
    tracking number to the person asking (red-team finding 2: the model happily
    tabulated four residents' names and home addresses). So this tool returns only
    what is safe to read out to a stranger holding the number: no applicant name,
    address, APN or contact details, no `fields` payload and no transition log
    (which carries staff actor names and free-text notes). Only the NAMES of the
    missing fields survive, because "still needed: applicant_address" tells the
    resident what to do without disclosing anything. The staff API, behind a
    login, is unchanged.
    """
    tracking = args.tracking_number.strip()
    app = (
        (
            await session.execute(
                select(models.Application).where(
                    func.lower(models.Application.tracking_number) == tracking.lower()
                )
            )
        )
        .scalars()
        .first()
    )
    if app is None:
        message = (
            f"I couldn't find {tracking}. Tracking numbers look like PRM-2026-000101 "
            "(permit), BTC-2026-000201 (business tax), SR-2026-000301 (service request) or "
            "STR-2026-000401 (short-term rental licence) — please double-check the digits."
        )
        return {"error": message, "summary": message}

    fee_usd = round(app.fee_cents / 100, 2) if app.fee_cents is not None else None
    missing = list(app.missing_fields or [])
    next_step = next_step_for(app.status)
    return {
        "tracking_number": app.tracking_number,
        "type": app.type,
        "status": app.status,
        "department": app.department,
        "fee_usd": fee_usd,
        "missing_fields": missing,
        "created_at": app.created_at.isoformat() if app.created_at else None,
        "updated_at": app.updated_at.isoformat() if app.updated_at else None,
        "next_step": next_step,
        "summary": (
            f"{app.tracking_number} ({app.type}) is currently '{app.status}' with "
            f"{app.department or 'the City'}."
            + (f" Fee on file: ${fee_usd:,.2f}." if fee_usd is not None else "")
            + (f" Still needed: {', '.join(missing)}." if missing else "")
            + f" {next_step}"
            + " Applicant details are not available through this assistant."
        ),
    }


async def get_permit_status(args: TrackingArgs, session: AsyncSession) -> dict:
    """Alias kept because residents say "permit status"; same lookup underneath."""
    return await get_application_status(args, session)


async def start_application(args: StartApplicationArgs, session: AsyncSession) -> dict:
    """Ask the UI to render the inline form for `type` and return its schema."""
    schema = FORM_SCHEMAS[args.type]
    return {
        "action": "render_form",
        "form_type": args.type,
        "form": schema,
        "summary": (
            f"Opening the {schema['title']} form in the chat. Fill in "
            f"{', '.join(f['label'] for f in schema['fields'] if f['required'])} and submit."
        ),
    }


async def create_service_request(args: ServiceRequestArgs, session: AsyncSession) -> dict:
    """File a Get It Done case: validate the category, insert, return the case id."""
    key = args.category.strip().lower().replace(" ", "_")
    # An empty or wildcard category used to match the first row through ILIKE and
    # file a *pothole* case for whatever the resident actually reported.
    category = None
    if key:
        category = (
            (
                await session.execute(
                    select(models.ServiceCategory).where(
                        or_(
                            models.ServiceCategory.category == key,
                            models.ServiceCategory.category.ilike(f"%{escape_like(key)}%", escape="\\"),
                            models.ServiceCategory.label.ilike(
                                f"%{escape_like(args.category.strip())}%", escape="\\"
                            ),
                        )
                    )
                )
            )
            .scalars()
            .first()
        )
    if category is None:
        known = (await session.execute(select(models.ServiceCategory.category).limit(25))).scalars().all()
        message = f"'{args.category}' isn't a category I can file. Try one of: {', '.join(known)}."
        return {"error": message, "summary": message}

    # Council district is derived where the address is known, as Get It Done does.
    address_row = (
        (
            await session.execute(
                select(models.Address).where(
                    models.Address.address.ilike(f"%{escape_like(args.address.strip())}%", escape="\\")
                )
            )
        )
        .scalars()
        .first()
    )

    # Field names are the ServiceRequestFields ones so the validator, the form
    # and the extractor all see the same keys.
    app = await engine.submit(
        session,
        "service_request",
        {
            "category": category.category,
            "address": args.address.strip(),
            # A resident who only named the problem still gets a readable case body.
            "description": args.description.strip() or f"{category.label} reported at {args.address.strip()}",
            "contact_email": args.contact_email,
            "council_district": address_row.council_district if address_row else None,
        },
    )
    return {
        "action": "application_created",
        "tracking_number": app.tracking_number,
        "category": category.category,
        "category_label": category.label,
        "department": category.department,
        "sla_days": category.sla_days,
        "status": app.status,
        "address": args.address.strip(),
        # Labelled, one fact per clause, because the model has to quote these three
        # back verbatim (the "word for word" rule in app/agents/profiles.py). In the
        # M23 run the reply named "Homelessness Strategies and Solutions Department"
        # while this row says "Homelessness Strategies & Solutions Dept"; naming the
        # department and the SLA as their own facts leaves nothing to paraphrase.
        # No instruction goes in here — a tool result is data, and the rule that
        # governs how it is quoted belongs in the system prompt.
        "summary": (
            f"Filed a {category.label} case for {args.address.strip()}. "
            f"Tracking number: {app.tracking_number}. "
            f"Department: {category.department}. "
            f"Target response time: {category.sla_days} day(s)."
        ),
    }
