"""One pydantic model per application type — the single definition of a form.

Read by the extractor (JSON schema for the model), the validator (REQUIRED_FIELDS),
GET /api/forms/{type} (form_schema) and conversational gap-filling
(missing_fields_model). Depends on: pydantic only, so it is import-cheap and
testable without a database. Fields are all Optional because extraction from a
PDF routinely misses some; "required" is a validation question, not a parse one.
"""

from typing import Literal

from pydantic import BaseModel, Field, create_model

OWNERSHIP_TYPES = ["sole_proprietor", "partnership", "llc", "corporation", "other"]

# The four Short-Term Residential Occupancy tiers, in the City's own words
# (research/06-parking-utilities-housing.md, sandiego.gov/stro). Kept as data
# rather than prose so the form, the extractor prompt, the validator's
# consistency rules and the licence PDF all describe a tier the same way.
STRO_TIERS = ["tier1", "tier2", "tier3", "tier4"]
STRO_TIER_LABELS = {
    "tier1": "Tier 1 — part-time, 20 nights a year or fewer, host need not live on site",
    "tier2": "Tier 2 — home-sharing, host lives on site and may be away up to 90 days a year",
    "tier3": "Tier 3 — whole-home, more than 20 nights a year, citywide except Mission Beach",
    "tier4": "Tier 4 — whole-home, Mission Beach Community Planning Area only",
}
STRO_UNIT_TYPES = [
    "single_family",
    "condo",
    "apartment",
    "duplex",
    "accessory_dwelling_unit",
    "other",
]


class PermitFields(BaseModel):
    """DS-3032-style building permit application (research/00-synthesis.md §1)."""

    applicant_name: str | None = Field(default=None, description="Full name of the applicant")
    applicant_email: str | None = Field(default=None, description="Applicant email address")
    applicant_phone: str | None = Field(default=None, description="Applicant phone number")
    project_address: str | None = Field(default=None, description="Street address where the work will happen")
    apn: str | None = Field(default=None, description="Assessor's Parcel Number, e.g. 533-421-08-00")
    permit_type: str | None = Field(
        default=None,
        description="Permit type code or name, e.g. Building Permit with Plans, No-Plan, Solar PV",
    )
    project_description: str | None = Field(
        default=None, description="What the project is, in the applicant's words"
    )
    valuation_usd: float | None = Field(default=None, description="Construction valuation in US dollars")
    square_feet: int | None = Field(default=None, description="Affected floor area in square feet")
    contractor_name: str | None = Field(default=None, description="Contractor business name")
    contractor_license: str | None = Field(default=None, description="California contractor licence number")
    owner_builder: bool | None = Field(
        default=None, description="True if the property owner is pulling the permit themselves"
    )


class BusinessTaxFields(BaseModel):
    """Business Tax Certificate application, City Treasurer."""

    business_name: str | None = Field(default=None, description="Legal business name")
    dba: str | None = Field(default=None, description="Doing-business-as / fictitious business name")
    owner_name: str | None = Field(default=None, description="Name of the owner or officer")
    business_address: str | None = Field(
        default=None, description="Physical business address; a PO Box is not accepted"
    )
    mailing_address: str | None = Field(default=None, description="Mailing address if different")
    start_date: str | None = Field(
        default=None, description="Date the business started or will start, as YYYY-MM-DD"
    )
    business_type: str | None = Field(
        default=None, description="What the business does, e.g. coffee shop / cafe"
    )
    naics_code: str | None = Field(default=None, description="NAICS activity code, e.g. 722515")
    employees: int | None = Field(default=None, description="Number of employees including the owner")
    ownership_type: Literal["sole_proprietor", "partnership", "llc", "corporation", "other"] | None = Field(
        default=None, description="Ownership structure"
    )
    sellers_permit_number: str | None = Field(
        default=None, description="CDTFA seller's permit number, if the business sells goods"
    )
    contact_email: str | None = Field(default=None, description="Contact email address")
    contact_phone: str | None = Field(default=None, description="Contact phone number")


class ServiceRequestFields(BaseModel):
    """Get It Done (311) report."""

    category: str | None = Field(
        default=None,
        description="Service category, e.g. pothole, graffiti_removal, missed_pickup, bulky_item",
    )
    address: str | None = Field(default=None, description="Where the problem is")
    description: str | None = Field(default=None, description="What the resident reported")
    contact_email: str | None = Field(default=None, description="Optional email for updates")
    contact_phone: str | None = Field(default=None, description="Optional phone number")
    photo_note: str | None = Field(
        default=None, description="Note about a photo; required for graffiti and illegal dumping"
    )


class StroFields(BaseModel):
    """Short-Term Residential Occupancy (STRO) licence application, City Treasurer.

    Field list from research/09-resident-forms.md §2 ("1. STRO License") plus the
    paperwork the knowledge base already tells residents to hold: a Transient
    Occupancy Tax certificate, a Rental Unit Business Tax certificate and a local
    contact who can be reached while guests are in the unit (api/kb/housing.md).
    """

    host_name: str | None = Field(default=None, description="Full name of the host applying")
    contact_email: str | None = Field(default=None, description="Host email address")
    contact_phone: str | None = Field(default=None, description="Host phone number")
    property_address: str | None = Field(
        default=None, description="Street address of the dwelling unit being licensed"
    )
    unit_type: (
        Literal["single_family", "condo", "apartment", "duplex", "accessory_dwelling_unit", "other"] | None
    ) = Field(default=None, description="What kind of dwelling unit this is")
    tier: Literal["tier1", "tier2", "tier3", "tier4"] | None = Field(
        default=None,
        description=(
            "Licence tier: tier1 = part-time, 20 nights a year or fewer, host need not live on "
            "site; tier2 = home-sharing, host lives on site and may be away up to 90 days a "
            "year; tier3 = whole-home, more than 20 nights a year, citywide except Mission "
            "Beach; tier4 = whole-home, Mission Beach Community Planning Area only"
        ),
    )
    host_resides_onsite: bool | None = Field(
        default=None,
        description=(
            "True if the dwelling unit is the host's primary residence and they live on site; "
            "required for a Tier 2 home-sharing licence"
        ),
    )
    nights_offered_per_year: int | None = Field(
        default=None,
        description=(
            "Nights per year the unit will be offered for short-term rental; Tier 1 is capped "
            "at 20, and Tier 3 and 4 need at least 90 nights of actual use to keep the licence"
        ),
    )
    owner_or_agent: Literal["owner", "authorized_agent"] | None = Field(
        default=None, description="Whether the applicant owns the unit or is an authorised agent"
    )
    tot_certificate_number: str | None = Field(
        default=None, description="Transient Occupancy Tax (TOT) certificate number"
    )
    rental_unit_btc_number: str | None = Field(
        default=None, description="Rental Unit Business Tax certificate number"
    )
    local_contact_name: str | None = Field(
        default=None, description="Name of the local contact reachable while guests are in the unit"
    )
    local_contact_phone: str | None = Field(
        default=None, description="24-hour phone number for the local contact"
    )
    attestation_accepted: bool | None = Field(
        default=None,
        description=(
            "True if the applicant attests the information is true and that they will comply "
            "with the City's short-term residential occupancy ordinance"
        ),
    )


FIELD_MODELS: dict[str, type[BaseModel]] = {
    "permit": PermitFields,
    "business_tax": BusinessTaxFields,
    "service_request": ServiceRequestFields,
    "stro": StroFields,
}

REQUIRED_FIELDS: dict[type[BaseModel], list[str]] = {
    PermitFields: [
        "applicant_name",
        "project_address",
        "permit_type",
        "project_description",
        "valuation_usd",
    ],
    BusinessTaxFields: [
        "business_name",
        "owner_name",
        "business_address",
        "start_date",
        "business_type",
        "employees",
        "ownership_type",
    ],
    ServiceRequestFields: ["category", "address", "description"],
    # `host_resides_onsite` and `nights_offered_per_year` are deliberately absent:
    # they are required only for some tiers, so validators._validate_stro adds
    # them to `missing` once it knows which tier was chosen.
    StroFields: [
        "host_name",
        "contact_email",
        "property_address",
        "unit_type",
        "tier",
        "owner_or_agent",
        "tot_certificate_number",
        "rental_unit_btc_number",
        "local_contact_name",
        "local_contact_phone",
        "attestation_accepted",
    ],
}

TITLES = {
    "permit": "Building Permit Application",
    "business_tax": "Business Tax Certificate Application",
    "service_request": "Report a Problem (Get It Done)",
    "stro": "Short-Term Residential Occupancy (STRO) Licence Application",
}

# Name suffix -> widget. Checked in order, so "_email" beats the "_name" default.
_LONG_TEXT = {"project_description", "description"}


def required_for(form_type: str) -> list[str]:
    """Required field names for a form type, from the pydantic model itself.

    One source of truth: the same list drives the form, the validator and the
    "still needed" line a resident sees.
    """
    return REQUIRED_FIELDS[FIELD_MODELS[form_type]]


def label_for(name: str, description: str | None = None) -> str:
    """Human label: the field name in sentence case, which reads better on a form
    than the pydantic description (which is written for the extractor)."""
    special = {
        "apn": "APN (Assessor's Parcel Number)",
        "dba": "DBA (fictitious business name)",
        "naics_code": "NAICS code",
        "valuation_usd": "Valuation (USD)",
        "sellers_permit_number": "Seller's permit number",
        "tot_certificate_number": "TOT (Transient Occupancy Tax) certificate number",
        "rental_unit_btc_number": "Rental Unit Business Tax certificate number",
        "host_resides_onsite": "Host's primary residence (host lives on site)",
        "nights_offered_per_year": "Nights offered per year",
        "attestation_accepted": "I attest this is true and I will comply with the STRO ordinance",
        "owner_or_agent": "Applying as",
    }
    if name in special:
        return special[name]
    return name.replace("_", " ").capitalize()


def display_value(name: str, value) -> str:
    """A field value as a person should read it, for a PDF or a chat summary.

    Only the STRO tier needs this today: "tier3" on a licence tells the holder
    nothing, while "Tier 3 — whole-home…" is the sentence the ordinance uses.
    Everything else is returned unchanged, so callers can use it everywhere.
    """
    if name == "tier" and isinstance(value, str) and value in STRO_TIER_LABELS:
        return STRO_TIER_LABELS[value]
    return str(value)


def _widget(name: str, annotation_json: dict) -> tuple[str, list[str] | None]:
    """Map a field to an HTML-ish input type plus options for a select."""
    enum = annotation_json.get("enum")
    if enum:
        return "select", [str(v) for v in enum if v is not None]
    if name in _LONG_TEXT:
        return "textarea", None
    if name.endswith("_email"):
        return "email", None
    if name.endswith("date"):
        return "date", None
    kind = annotation_json.get("type")
    if kind == "boolean":
        return "checkbox", None
    if kind in ("number", "integer"):
        return "number", None
    return "text", None


def _unwrap(schema: dict) -> dict:
    """Optional[X] renders as anyOf[X, null]; return the non-null branch."""
    for branch in schema.get("anyOf", []):
        if branch.get("type") != "null":
            return branch
    return schema


def form_schema(form_type: str) -> dict:
    """The field list GET /api/forms/{type} returns and the web app renders."""
    model = FIELD_MODELS[form_type]
    required = REQUIRED_FIELDS[model]
    json_schema = model.model_json_schema()
    fields = []
    for name, prop in json_schema.get("properties", {}).items():
        branch = _unwrap(prop)
        widget, options = _widget(name, branch)
        field: dict = {
            "name": name,
            "label": label_for(name),
            "type": widget,
            "required": name in required,
        }
        if options:
            field["options"] = options
        placeholder = prop.get("description")
        if placeholder:
            field["placeholder"] = placeholder
        fields.append(field)
    return {"form_type": form_type, "title": TITLES[form_type], "fields": fields}


def missing_fields_model(form_type: str, missing: list[str]) -> type[BaseModel]:
    """A throwaway model holding only `missing`, for one gap-filling extraction.

    Narrowing the schema keeps a small model focused: it is asked for four fields
    it does not have rather than twelve it mostly does.
    """
    model = FIELD_MODELS[form_type]
    wanted = [m for m in missing if m in model.model_fields] or list(model.model_fields)
    definitions = {name: (model.model_fields[name].annotation, model.model_fields[name]) for name in wanted}
    return create_model(f"Missing{model.__name__}", **definitions)  # type: ignore[call-overload]
