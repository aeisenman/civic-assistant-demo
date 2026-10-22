"""The one definition of a form: field widgets, required flags, and gap-filling.

If these drift, /api/forms, the extractor's JSON schema and the validator stop
agreeing, which is the whole reason the models live in one module.
"""

import pytest

from app.workflows import schemas


def fields_by_name(form_type: str) -> dict[str, dict]:
    return {f["name"]: f for f in schemas.form_schema(form_type)["fields"]}


def test_every_field_is_optional_on_the_model():
    """Extraction misses fields; "required" is a validation answer, not a parse one."""
    for model in schemas.FIELD_MODELS.values():
        for name, field in model.model_fields.items():
            assert not field.is_required(), f"{model.__name__}.{name} must be optional"


def test_permit_form_shape():
    form = schemas.form_schema("permit")
    assert form["form_type"] == "permit"
    assert form["title"] == "Building Permit Application"
    fields = fields_by_name("permit")
    assert fields["valuation_usd"]["type"] == "number"
    assert fields["square_feet"]["type"] == "number"
    assert fields["owner_builder"]["type"] == "checkbox"
    assert fields["applicant_email"]["type"] == "email"
    assert fields["project_description"]["type"] == "textarea"
    assert fields["applicant_name"]["required"] is True
    assert fields["contractor_name"]["required"] is False


def test_business_tax_ownership_type_renders_as_a_select():
    field = fields_by_name("business_tax")["ownership_type"]
    assert field["type"] == "select"
    assert field["options"] == schemas.OWNERSHIP_TYPES
    assert fields_by_name("business_tax")["start_date"]["type"] == "date"


def test_required_flags_match_required_fields():
    for form_type in schemas.FIELD_MODELS:
        required = {f["name"] for f in schemas.form_schema(form_type)["fields"] if f["required"]}
        assert required == set(schemas.required_for(form_type))


def test_every_field_carries_a_placeholder_from_its_description():
    for form_type in schemas.FIELD_MODELS:
        for field in schemas.form_schema(form_type)["fields"]:
            assert field["placeholder"], f"{form_type}.{field['name']} has no description"


def test_missing_fields_model_holds_only_the_gaps():
    model = schemas.missing_fields_model("permit", ["permit_type", "valuation_usd"])
    assert set(model.model_fields) == {"permit_type", "valuation_usd"}
    parsed = model.model_validate({"permit_type": "Building Permit with Plans"})
    assert parsed.valuation_usd is None
    assert "valuation_usd" in model.model_json_schema()["properties"]


def test_missing_fields_model_ignores_unknown_names():
    model = schemas.missing_fields_model("service_request", ["category", "not_a_field"])
    assert set(model.model_fields) == {"category"}


def test_missing_fields_model_falls_back_to_the_whole_form():
    """An empty list would produce a model with no fields, which no LLM can fill."""
    model = schemas.missing_fields_model("service_request", [])
    assert set(model.model_fields) == set(schemas.ServiceRequestFields.model_fields)


@pytest.mark.parametrize(
    "name,expected",
    [("apn", "APN (Assessor's Parcel Number)"), ("applicant_name", "Applicant name")],
)
def test_labels_are_human_readable(name, expected):
    assert schemas.label_for(name) == expected
