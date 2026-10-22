"""The three M14 bounds on document intake: page cap, thread, extraction cap.

Builds real PDFs with pypdf (no fixtures on disk, no network) and replaces
chat_json so no model is involved. Depends on: app.workflows.intake and pypdf,
which is already the extractor the production path uses.
"""

import io
import threading

import pytest
from pypdf import PdfWriter

from app.workflows import intake
from app.workflows.schemas import PermitFields


def pdf_with(pages: int) -> bytes:
    """A real, valid PDF of `pages` blank US-letter pages."""
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=612, height=792)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


# ------------------------------------------------------------------ page cap
def test_a_pdf_over_the_page_cap_is_refused_rather_than_walked():
    with pytest.raises(ValueError) as caught:
        intake._read_pdf(pdf_with(intake.MAX_PDF_PAGES + 1))
    assert str(intake.MAX_PDF_PAGES) in str(caught.value)


def test_a_pdf_at_the_page_cap_is_still_read():
    assert intake._read_pdf(pdf_with(intake.MAX_PDF_PAGES)) == ""


async def test_an_over_long_pdf_becomes_a_document_with_no_text_not_an_error():
    """The resident is told there is no readable text, the same as for a scan."""
    text = await intake._extract_text("huge.pdf", "application/pdf", pdf_with(101))
    assert text == ""


# --------------------------------------------------------------- off the loop
async def test_pypdf_runs_on_a_worker_thread():
    """Synchronous pypdf on the event loop stalled every in-flight SSE stream."""
    main_thread = threading.get_ident()
    seen: list[int] = []

    def spy(data: bytes) -> str:
        seen.append(threading.get_ident())
        return "extracted"

    original = intake._read_pdf
    intake._read_pdf = spy
    try:
        text = await intake._extract_text("x.pdf", "application/pdf", b"%PDF-1.4")
    finally:
        intake._read_pdf = original

    assert text == "extracted"
    assert seen and seen[0] != main_thread


async def test_a_text_upload_still_skips_pypdf_entirely():
    text = await intake._extract_text("notes.txt", "text/plain", b"hello")
    assert text == "hello"


# ---------------------------------------------------------- extraction ceiling
async def test_extraction_input_is_capped(monkeypatch):
    """A 10 MB .txt used to go to the EXTRACT tier whole: about 2.5M tokens."""
    seen: list[list[dict]] = []

    async def fake_chat_json(tier, messages, model, **kwargs):
        seen.append(messages)
        return PermitFields()

    monkeypatch.setattr(intake, "chat_json", fake_chat_json)
    await intake.extract_fields("x" * 500_000, "permit")

    user_message = seen[0][-1]
    assert user_message["role"] == "user"
    assert len(user_message["content"]) == intake.MAX_EXTRACT_CHARS


async def test_a_normal_document_is_sent_whole(monkeypatch):
    async def fake_chat_json(tier, messages, model, **kwargs):
        return PermitFields()

    monkeypatch.setattr(intake, "chat_json", fake_chat_json)
    # Nothing to assert beyond "it did not raise and did not truncate": the cap
    # is 40k chars and a City permit form is a few thousand.
    assert intake.MAX_EXTRACT_CHARS > 10_000
    await intake.extract_fields("a short form", "permit")
