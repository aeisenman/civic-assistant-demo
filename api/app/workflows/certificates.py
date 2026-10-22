"""Generates the one-page PDF an application gets when it reaches `issued`.

Called by the `issued` hook in app/workflows/engine.py; the bytes are stored in
SeaweedFS and streamed back by GET /api/applications/{id}/certificate. Depends
on: reportlab and app.storage.s3. render_certificate() is pure (bytes in memory)
so it can be tested without object storage or a database.
"""

import logging
from datetime import date

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

from app import clock
from app.storage import s3
from app.workflows.schemas import display_value, label_for

log = logging.getLogger(__name__)

TITLES = {
    "permit": "Building Permit",
    "business_tax": "Business Tax Certificate",
    "service_request": "Service Request Confirmation",
    "stro": "Short-Term Residential Occupancy (STRO) Licence",
}
FOOTER = "This is a demonstration document generated from fictional data."
LEFT = 0.9 * inch
RIGHT = letter[0] - 0.9 * inch
LABEL_WIDTH = 2.4 * inch


def _wrap(value: str, width: int) -> list[str]:
    """Crude word wrap; reportlab has no paragraph flow on a bare canvas."""
    words, lines, current = value.split(), [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > width and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or [""]


def render_certificate(
    app_type: str,
    tracking_number: str,
    fields: dict,
    *,
    department: str | None = None,
    fee_cents: int | None = None,
    issued_on: date | None = None,
) -> bytes:
    """One page: header, identifiers, a two-column field table, fee, footer."""
    from io import BytesIO

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    y = letter[1] - 1.0 * inch

    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(LEFT, y, "City of San Diego — DEMO")
    y -= 0.28 * inch
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(LEFT, y, TITLES.get(app_type, "Application"))
    y -= 0.16 * inch
    pdf.line(LEFT, y, RIGHT, y)
    y -= 0.32 * inch

    header = [
        ("Tracking number", tracking_number),
        ("Issued", (issued_on or clock.today()).isoformat()),
        ("Department", department or "City of San Diego"),
    ]
    pdf.setFont("Helvetica", 10)
    for label, value in header:
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(LEFT, y, f"{label}:")
        pdf.setFont("Helvetica", 10)
        pdf.drawString(LEFT + LABEL_WIDTH, y, str(value))
        y -= 0.22 * inch

    y -= 0.14 * inch
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(LEFT, y, "Application details")
    y -= 0.22 * inch

    for name, value in (fields or {}).items():
        if value is None or value == "":
            continue
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawString(LEFT, y, label_for(name))
        pdf.setFont("Helvetica", 9)
        # display_value is what puts "Tier 3 — whole-home…" on a STRO licence
        # instead of the enum "tier3"; every other field passes through unchanged.
        for line in _wrap(display_value(name, value), 62):
            pdf.drawString(LEFT + LABEL_WIDTH, y, line)
            y -= 0.19 * inch
        if y < 1.6 * inch:  # one page only; the rest is on file with the City
            pdf.drawString(LEFT, y, "…")
            break

    y -= 0.12 * inch
    pdf.setFont("Helvetica-Bold", 10)
    fee = "$0.00" if not fee_cents else f"${fee_cents / 100:,.2f}"
    pdf.drawString(LEFT, y, f"Fee: {fee} (estimate)")

    pdf.setFont("Helvetica-Oblique", 8)
    pdf.drawString(LEFT, 0.85 * inch, FOOTER)
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def store_certificate(app_type: str, tracking_number: str, fields: dict, **kwargs) -> str:
    """Render and put the PDF in SeaweedFS; returns the key to persist."""
    data = render_certificate(app_type, tracking_number, fields, **kwargs)
    key = f"certificates/{tracking_number}.pdf"
    s3.put_bytes(key, data, "application/pdf")
    log.info("certificate stored at %s (%d bytes)", key, len(data))
    return key
