"""Generates the sample application PDFs the demo uploads into the chat.

Run by hand (`uv run python forms/generate_samples.py`); the PDFs it writes are
committed next to it so a fresh clone can demo without reportlab bookkeeping.
Depends on: reportlab only. The layout imitates a City form — title block,
labeled fields, drawn checkboxes — so the extractor has to read a real document
rather than a tidy key/value list. `sample_permit_incomplete.pdf` deliberately
leaves permit type and valuation blank so the demo reaches `needs_info`.
"""

from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

OUT_DIR = Path(__file__).resolve().parent
LEFT = 0.85 * inch
RIGHT = letter[0] - 0.85 * inch
LABEL_X = LEFT
VALUE_X = LEFT + 2.5 * inch
LINE = 0.28 * inch


class Form:
    """Tiny drawing helper: a cursor plus the four marks these forms need."""

    def __init__(self, path: Path, title: str, subtitle: str):
        self.pdf = canvas.Canvas(str(path), pagesize=letter)
        self.y = letter[1] - 0.9 * inch
        self.pdf.setFont("Helvetica-Bold", 13)
        self.pdf.drawString(LEFT, self.y, title)
        self.y -= 0.24 * inch
        self.pdf.setFont("Helvetica", 10)
        self.pdf.drawString(LEFT, self.y, subtitle)
        self.y -= 0.12 * inch
        self.pdf.line(LEFT, self.y, RIGHT, self.y)
        self.y -= 0.34 * inch

    def section(self, text: str) -> None:
        self.y -= 0.10 * inch
        self.pdf.setFont("Helvetica-Bold", 10)
        self.pdf.drawString(LEFT, self.y, text)
        self.y -= 0.06 * inch
        self.pdf.line(LEFT, self.y, RIGHT, self.y)
        self.y -= 0.24 * inch

    def field(self, label: str, value: str = "") -> None:
        self.pdf.setFont("Helvetica", 9)
        self.pdf.drawString(LABEL_X, self.y, f"{label}:")
        self.pdf.setFont("Helvetica-Bold", 9)
        self.pdf.drawString(VALUE_X, self.y, value)
        # The rule under the answer is what makes it look like a paper form.
        self.pdf.setLineWidth(0.3)
        self.pdf.line(VALUE_X, self.y - 0.05 * inch, RIGHT, self.y - 0.05 * inch)
        self.y -= LINE

    def paragraph(self, label: str, text: str) -> None:
        self.pdf.setFont("Helvetica", 9)
        self.pdf.drawString(LABEL_X, self.y, f"{label}:")
        self.pdf.setFont("Helvetica-Bold", 9)
        words, line = text.split(), ""
        x = VALUE_X
        for word in words:
            candidate = f"{line} {word}".strip()
            if len(candidate) > 52:
                self.pdf.drawString(x, self.y, line)
                self.y -= 0.20 * inch
                line = word
            else:
                line = candidate
        self.pdf.drawString(x, self.y, line)
        self.y -= LINE

    def checkbox(self, label: str, checked: bool) -> None:
        """A drawn box whose mark and label are one text run.

        Two separate drawString calls extract as two lines and the "X" ends up
        floating between labels, so the extractor cannot tell which box is
        ticked. One run keeps "X   Limited liability company (LLC)" together.
        """
        size = 0.13 * inch
        self.pdf.setLineWidth(0.7)
        self.pdf.rect(LABEL_X, self.y - 0.02 * inch, size, size)
        self.pdf.setFont("Helvetica", 9)
        self.pdf.drawString(LABEL_X + 0.03 * inch, self.y, f"{'X' if checked else ' '}      {label}")
        self.y -= 0.26 * inch

    def save(self, footer: str) -> None:
        self.pdf.setFont("Helvetica-Oblique", 8)
        self.pdf.drawString(LEFT, 0.8 * inch, footer)
        self.pdf.showPage()
        self.pdf.save()


PERMIT_TITLE = "City of San Diego Development Services — General Application (DS-3032) — DEMO"
BTC_TITLE = "City of San Diego Office of the City Treasurer — Business Tax Application — DEMO"
STRO_TITLE = (
    "City of San Diego Office of the City Treasurer — Short-Term Residential Occupancy "
    "(STRO) Licence Application — DEMO"
)
FOOTER = "Demonstration form. Fictional data; not a City of San Diego record."


def permit_form(path: Path, *, address: str, description: str, complete: bool) -> None:
    """The DS-3032-style permit application; `complete=False` omits two fields."""
    form = Form(path, PERMIT_TITLE, "Combination Building Permit Application — Page 1 of 1")
    form.section("1. APPLICANT")
    form.field("Applicant name", "Maria Lopez")
    form.field("Email", "maria.lopez@example.com")
    form.field("Phone", "619-555-0142")
    form.section("2. PROJECT")
    form.field("Project address", address)
    form.field("Assessor's Parcel Number (APN)", "533-421-08-00")
    form.field("Permit type", "Building Permit with Plans" if complete else "")
    form.paragraph("Scope of work", description)
    form.field("Project valuation (USD)", "$45,000.00" if complete else "")
    form.field("Affected floor area (sq ft)", "220")
    form.section("3. CONTRACTOR")
    form.field("Contractor business name", "Pacific Coast Remodeling")
    form.field("California licence number", "B-778899")
    form.section("4. DECLARATIONS")
    form.checkbox("Owner-builder (DS-3042 attached)", False)
    form.checkbox("Licensed contractor declaration signed", True)
    form.checkbox("Structure is 45 years or older (historic review)", False)
    form.save(FOOTER)


def business_tax_form(path: Path) -> None:
    form = Form(path, BTC_TITLE, "Business Tax Certificate Application — Parts 1-5")
    form.section("PART 1. BUSINESS")
    form.field("Legal business name", "Adams Avenue Coffee LLC")
    form.field("Doing business as (DBA)", "Ridgeline Coffee")
    form.field("Business address", "4521 Adams Ave, San Diego, CA 92116")
    form.field("Mailing address", "Same as business address")
    form.section("PART 2. OWNERSHIP")
    form.field("Owner / officer name", "Daniel Okafor")
    form.checkbox("Sole proprietor", False)
    form.checkbox("Partnership", False)
    form.checkbox("Limited liability company (LLC)", True)
    form.checkbox("Corporation", False)
    form.section("PART 3. ACTIVITY")
    form.field("Business start date", "2026-09-15")
    form.field("Type of business", "Coffee shop / cafe")
    form.field("NAICS code", "722515")
    form.field("Number of employees", "4")
    form.field("Seller's permit number", "101-234567")
    form.section("PART 4-5. CONTACT AND REGULATED ACTIVITY")
    form.field("Contact email", "daniel@example.com")
    form.field("Contact phone", "619-555-0177")
    form.checkbox("Police-regulated activity (Part 4)", False)
    form.checkbox("Fire-permit activity (Part 5)", False)
    form.save(FOOTER)


def stro_form(path: Path) -> None:
    """A complete Tier 3 whole-home STRO application.

    Complete on purpose: the incomplete path already has a sample
    (`sample_permit_incomplete.pdf`), and this one is what `scripts/smoke.sh`
    files to prove the fourth type reaches `in_review` unaided. The tier is
    written both as a ticked box and as the words the ordinance uses, because
    the extractor has to return the enum value `tier3`, not a sentence.
    """
    form = Form(path, STRO_TITLE, "STRO Licence Application — Page 1 of 1")
    form.section("1. HOST")
    form.field("Host name", "Elena Moreau")
    form.field("Email", "elena.moreau@example.com")
    form.field("Phone", "619-555-0182")
    form.checkbox("Applying as the owner", True)
    form.checkbox("Applying as an authorized agent", False)
    form.section("2. PROPERTY")
    form.field("Property address", "3355 University Ave, San Diego, CA 92104")
    form.checkbox("Single-family home", True)
    form.checkbox("Condominium", False)
    form.checkbox("Apartment", False)
    form.checkbox("Duplex", False)
    form.checkbox("Accessory dwelling unit (ADU)", False)
    form.section("3. LICENCE TIER")
    form.checkbox("Tier 1 — part-time, 20 nights a year or fewer", False)
    form.checkbox("Tier 2 — home-sharing, host lives on site", False)
    form.checkbox("Tier 3 — whole-home, more than 20 nights a year, citywide", True)
    form.checkbox("Tier 4 — whole-home, Mission Beach only", False)
    form.field("Nights offered per year", "180")
    form.field("Is this the host's primary residence?", "No")
    form.section("4. TAX CERTIFICATES")
    form.field("Transient Occupancy Tax (TOT) certificate no.", "TOT-2026-114502")
    form.field("Rental Unit Business Tax certificate no.", "RUBT-2026-33871")
    form.section("5. LOCAL CONTACT (24 HOURS)")
    form.field("Local contact name", "Marcus Webb")
    form.field("Local contact phone", "619-555-0198")
    form.section("6. ATTESTATION")
    form.checkbox("I attest this is true and I will comply with the STRO ordinance", True)
    form.save(FOOTER)


def main() -> None:
    permit_form(
        OUT_DIR / "sample_permit_application.pdf",
        address="1234 Cedar St, San Diego, CA 92101",
        description=(
            "Kitchen remodel with a new island and a relocated sink, including new "
            "plumbing and electrical rough-in."
        ),
        complete=True,
    )
    permit_form(
        OUT_DIR / "sample_permit_incomplete.pdf",
        address="555 Market St, San Diego, CA 92101",
        description="Detached garage conversion to an accessory dwelling unit (ADU).",
        complete=False,
    )
    business_tax_form(OUT_DIR / "sample_business_tax_application.pdf")
    stro_form(OUT_DIR / "sample_stro_application.pdf")
    for path in sorted(OUT_DIR.glob("*.pdf")):
        print(f"wrote {path.name} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
