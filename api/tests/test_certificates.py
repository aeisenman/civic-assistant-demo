"""The issued-status artifact: a real one-page PDF, generated without I/O.

render_certificate() is deliberately separate from store_certificate() so this
runs with no SeaweedFS and no database.
"""

import io
from datetime import date

from pypdf import PdfReader

from app.workflows.certificates import render_certificate


def text_of(data: bytes) -> str:
    return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages)


FIELDS = {
    "applicant_name": "Maria Lopez",
    "project_address": "1234 Cedar St, San Diego, CA 92101",
    "permit_type": "Building Permit with Plans",
    "project_description": "Kitchen remodel with a new island and a relocated sink.",
    "valuation_usd": 45000.0,
    "contractor_license": None,
}


def test_certificate_is_a_pdf():
    data = render_certificate("permit", "PRM-2026-000400", FIELDS, fee_cents=41102)
    assert data[:4] == b"%PDF"
    assert len(data) > 500


def test_certificate_carries_the_tracking_number_and_the_demo_footer():
    data = render_certificate(
        "permit",
        "PRM-2026-000400",
        FIELDS,
        department="Development Services Department",
        fee_cents=41102,
        issued_on=date(2026, 9, 2),
    )
    text = text_of(data)
    assert "PRM-2026-000400" in text
    assert "City of San Diego — DEMO" in text
    assert "Building Permit" in text
    assert "2026-09-02" in text
    assert "Development Services Department" in text
    assert "$411.02" in text
    assert "demonstration document generated from fictional data" in text
    # A null field is dropped rather than printed as "None".
    assert "None" not in text


def test_every_type_renders():
    for app_type in ("permit", "business_tax", "service_request", "stro"):
        assert render_certificate(app_type, f"X-{app_type}", {"a": "b"})[:4] == b"%PDF"


def test_empty_fields_and_no_fee_still_render():
    data = render_certificate("service_request", "SR-2026-000400", {}, fee_cents=None)
    assert data[:4] == b"%PDF"
