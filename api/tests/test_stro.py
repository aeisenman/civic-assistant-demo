"""The fourth application type end to end, minus the model and the database.

Everything M24 added that can be asserted offline: the schema and its required
list, the tier/residence consistency rules, the flat per-tier fee, the STR-
tracking prefix and its own sequence, the form schema the UI renders, the
narrowed gap-filling model, the licence PDF, and that validation routes a STRO
application to the Treasurer. Depends on: app.workflows.* and app.tools.fees.
"""

import io

import pytest
from pypdf import PdfReader

from app.api.forms import FORM_SCHEMAS
from app.tools.fees import STRO_REVIEW_SLA_DAYS, stro_fee_breakdown
from app.workflows import schemas, store, validators
from app.workflows.certificates import render_certificate

# A complete Tier 3 application, the same shape sample_stro_application.pdf has.
COMPLETE = {
    "host_name": "Elena Moreau",
    "contact_email": "elena.moreau@example.com",
    "contact_phone": "619-555-0182",
    "property_address": "3355 University Ave, San Diego, CA 92104",
    "unit_type": "single_family",
    "tier": "tier3",
    "host_resides_onsite": False,
    "nights_offered_per_year": 180,
    "owner_or_agent": "owner",
    "tot_certificate_number": "TOT-2026-114502",
    "rental_unit_btc_number": "RUBT-2026-33871",
    "local_contact_name": "Marcus Webb",
    "local_contact_phone": "619-555-0198",
    "attestation_accepted": True,
}


class FakeSession:
    """Enough of an AsyncSession for the address lookup the validator does."""

    def __init__(self, row=None):
        self.row = row

    async def execute(self, statement, *args, **kwargs):
        row = self.row

        class _Result:
            def scalars(self_inner):
                return self_inner

            def first(self_inner):
                return row

        return _Result()


async def validate(fields: dict) -> validators.ValidationResult:
    """Run only the STRO branch, the way engine._on_validating would."""
    result = validators.ValidationResult(missing=validators.missing_required("stro", fields))
    await validators._validate_stro(FakeSession(), result, fields)
    return result


# ------------------------------------------------------------------ the schema


def test_stro_is_a_registered_form_type():
    assert schemas.FIELD_MODELS["stro"] is schemas.StroFields
    assert "Short-Term Residential Occupancy" in schemas.TITLES["stro"]


def test_required_list_omits_the_conditional_fields():
    """Tier decides whether nights and on-site residence are required, so the
    flat list cannot carry them — the validator adds them once it sees a tier."""
    required = set(schemas.required_for("stro"))
    assert "tier" in required and "attestation_accepted" in required
    assert "host_resides_onsite" not in required
    assert "nights_offered_per_year" not in required


def test_missing_required_lists_every_gap():
    missing = validators.missing_required("stro", {"host_name": "Elena", "property_address": " "})
    assert missing == [
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
    ]


def test_form_schema_renders_the_tier_and_the_attestation():
    fields = {f["name"]: f for f in schemas.form_schema("stro")["fields"]}
    assert fields["tier"]["type"] == "select"
    assert fields["tier"]["options"] == schemas.STRO_TIERS
    assert fields["unit_type"]["options"] == schemas.STRO_UNIT_TYPES
    assert fields["attestation_accepted"]["type"] == "checkbox"
    assert fields["attestation_accepted"]["required"] is True
    assert fields["nights_offered_per_year"]["type"] == "number"
    assert fields["contact_email"]["type"] == "email"


def test_forms_endpoint_serves_the_stro_schema():
    """GET /api/forms/stro reads this dict, rendered once at import."""
    schema = FORM_SCHEMAS["stro"]
    assert schema["form_type"] == "stro"
    assert schema["title"] == schemas.TITLES["stro"]
    assert {f["name"] for f in schema["fields"]} == set(schemas.StroFields.model_fields)


def test_extraction_narrows_to_the_missing_fields_only():
    """The needs_info loop asks a small model for the gaps, not the whole form."""
    model = schemas.missing_fields_model("stro", ["tier", "nights_offered_per_year", "nope"])
    assert set(model.model_fields) == {"tier", "nights_offered_per_year"}
    assert model.model_validate({"tier": "tier1"}).nights_offered_per_year is None


def test_the_tier_is_displayed_in_words():
    assert schemas.display_value("tier", "tier3").startswith("Tier 3")
    assert schemas.display_value("host_name", "Elena Moreau") == "Elena Moreau"


# --------------------------------------------------------------- the fee rule


@pytest.mark.parametrize(
    "tier,total_cents",
    [("tier1", 22600), ("tier2", 31700), ("tier3", 117000), ("tier4", 117000)],
)
def test_fee_is_the_application_fee_plus_the_licence_fee(tier, total_cents):
    breakdown = stro_fee_breakdown(tier)
    assert breakdown["total_cents"] == total_cents
    assert breakdown["total_usd"] == round(total_cents / 100, 2)
    assert sum(line["amount_usd"] for line in breakdown["line_items"]) == breakdown["total_usd"]
    assert "estimate" in breakdown["summary"]
    assert breakdown["review_sla_days"] == STRO_REVIEW_SLA_DAYS


def test_an_unknown_tier_is_not_priced():
    """The tiers differ by more than $900, so guessing is worse than asking."""
    breakdown = stro_fee_breakdown(None)
    assert breakdown["total_cents"] is None
    assert "tier" in breakdown["error"]


# ------------------------------------------------------- the validation rules


async def test_a_complete_tier3_application_routes_to_the_treasurer():
    result = await validate(COMPLETE)
    assert result.complete
    assert result.department == validators.TREASURER
    assert result.fee_cents == 117000


async def test_tier2_requires_the_host_to_live_on_site():
    fields = {**COMPLETE, "tier": "tier2", "host_resides_onsite": False}
    result = await validate(fields)
    assert "host_resides_onsite" in result.missing
    assert any("home-sharing" in w for w in result.warnings)


async def test_tier2_with_the_host_on_site_is_complete():
    fields = {**COMPLETE, "tier": "tier2", "host_resides_onsite": True}
    result = await validate(fields)
    assert result.complete
    assert result.fee_cents == 31700


async def test_tier1_needs_a_night_count_and_is_capped_at_twenty():
    no_nights = await validate({**COMPLETE, "tier": "tier1", "nights_offered_per_year": None})
    assert "nights_offered_per_year" in no_nights.missing

    too_many = await validate({**COMPLETE, "tier": "tier1", "nights_offered_per_year": 45})
    assert "tier" in too_many.missing
    assert any("20 nights" in w for w in too_many.warnings)


async def test_a_whole_home_tier_under_ninety_nights_is_only_a_warning():
    """It is a condition of keeping the licence, not a reason to refuse it."""
    result = await validate({**COMPLETE, "nights_offered_per_year": 30})
    assert result.complete
    assert any("90 nights" in w for w in result.warnings)


async def test_a_whole_home_host_who_lives_there_is_flagged():
    result = await validate({**COMPLETE, "host_resides_onsite": True})
    assert result.complete
    assert any("does not occupy" in w for w in result.warnings)


async def test_mission_beach_and_tier4_have_to_agree():
    tier4_elsewhere = await validate({**COMPLETE, "tier": "tier4"})
    assert any("Mission Beach Community Planning Area only" in w for w in tier4_elsewhere.warnings)

    tier3_in_mission_beach = await validate(
        {**COMPLETE, "property_address": "3800 Mission Blvd, Mission Beach, San Diego, CA 92109"}
    )
    assert any("Tier 4 licence, not Tier 3" in w for w in tier3_in_mission_beach.warnings)


async def test_an_unticked_attestation_is_a_gap_even_though_false_is_a_value():
    """missing_required only catches None and blanks; False has to be caught here."""
    result = await validate({**COMPLETE, "attestation_accepted": False})
    assert "attestation_accepted" in result.missing
    assert result.missing.count("attestation_accepted") == 1


async def test_an_adu_is_flagged_as_ineligible():
    result = await validate({**COMPLETE, "unit_type": "accessory_dwelling_unit"})
    assert any("accessory dwelling units are not eligible" in w for w in result.warnings)


def test_the_address_field_for_stro_is_the_property_address():
    assert validators.ADDRESS_FIELD["stro"] == "property_address"


# ------------------------------------------------- tracking numbers and the PDF


def test_stro_has_its_own_prefix_and_sequence():
    assert store.PREFIXES["stro"] == "STR"
    assert store.SEQUENCES["stro"] == "tracking_stro_seq"
    assert set(store.SEQUENCES) == set(store.PREFIXES)


def test_migration_008_creates_that_sequence_idempotently():
    from pathlib import Path

    sql = (Path(__file__).resolve().parents[1] / "app/db/migrations/008_stro.sql").read_text()
    assert "CREATE SEQUENCE IF NOT EXISTS tracking_stro_seq" in sql
    # Above the seeded fixtures (STR-2026-000401/000402) so nothing collides.
    assert "499" in sql
    assert "ALTER TABLE" not in sql and "DROP" not in sql


def test_a_str_tracking_number_short_circuits_the_classifier():
    """`SR` inside `STR-` used to be the trap: STR comes first in the alternation."""
    from app.llm import router

    match = router.TRACKING_RE.search("What's the status of STR-2026-000401?")
    assert match is not None
    assert match.group(1).upper() == "STR"
    # Housing has no intent of its own, so a STRO licence question is `general`.
    assert router.PREFIX_INTENT["STR"] == "general"
    assert set(router.PREFIX_INTENT) == {p.upper() for p in store.PREFIXES.values()}


def test_the_licence_pdf_names_the_licence_and_its_tier():
    data = render_certificate(
        "stro",
        "STR-2026-000401",
        COMPLETE,
        department="Office of the City Treasurer",
        fee_cents=117000,
    )
    assert data[:4] == b"%PDF"
    text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages)
    assert "Short-Term Residential Occupancy" in text
    assert "STR-2026-000401" in text
    # The enum "tier3" on a licence tells the holder nothing; the words do.
    assert "Tier 3" in text
    assert "$1,170.00" in text
    assert "Office of the City Treasurer" in text
