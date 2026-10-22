"""Turning an uploaded document (or a follow-up message) into an application.

Called by POST /api/documents and by app/agents/intake_turn.py. Depends on:
app.storage.s3 (bytes), pypdf (text), app.llm.client (detection + extraction at
the EXTRACT tier, which has the long context) and app.workflows.engine (the row
and its status). Nothing here decides a status by itself — the engine does.
"""

import asyncio
import io
import logging
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models
from app.llm.client import Tier, chat_json
from app.storage import s3
from app.workflows import engine
from app.workflows.schemas import FIELD_MODELS, missing_fields_model

log = logging.getLogger(__name__)

MIN_USEFUL_TEXT = 50  # below this a PDF is almost certainly a scan
DETECT_CHARS = 3000  # the first page or two is enough to tell the type apart
# Extraction is the one call that sees the whole document, at the EXTRACT tier.
# A 10 MB .txt is ~2.5M tokens; 40k chars is ~10k tokens, far more than any City
# form and small enough that a hostile upload cannot buy itself a large bill.
MAX_EXTRACT_CHARS = 40_000
# A City application is a handful of pages. PDF object streams compress about
# 1000:1, so a 9 MB file can claim 50,000 pages and pypdf will try them all.
MAX_PDF_PAGES = 100
TEXT_TYPES = ("text/plain", "text/markdown", "text/csv")

ApplicationType = Literal["permit", "business_tax", "service_request", "stro", "unknown"]


class DetectedType(BaseModel):
    """Classifier output for an uploaded document."""

    type: ApplicationType = Field(description="Which City application this document is")


def _read_pdf(data: bytes) -> str:
    """Blocking pypdf work, run on a worker thread by `_extract_text`.

    Raises on a document with more than MAX_PDF_PAGES pages rather than walking
    them: the caller treats an unreadable upload as "no text", which is the same
    thing the resident is told about a scan.
    """
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    pages = len(reader.pages)
    if pages > MAX_PDF_PAGES:
        raise ValueError(f"{pages} pages is over the {MAX_PDF_PAGES}-page limit")
    return "\n".join((page.extract_text() or "") for page in reader.pages).strip()


async def _extract_text(filename: str, content_type: str | None, data: bytes) -> str:
    """PDF text via pypdf; plain text and markdown are stored as they arrive.

    pypdf is synchronous and can take minutes on a large file. Run on the event
    loop it stalled every in-flight SSE stream and the health check with it, so
    it goes to a thread (audit row 2).
    """
    lowered = (filename or "").lower()
    if (content_type or "").startswith(TEXT_TYPES) or lowered.endswith((".txt", ".md")):
        return data.decode("utf-8", errors="replace")
    try:
        return await asyncio.to_thread(_read_pdf, data)
    except Exception as exc:  # noqa: BLE001 - an unreadable upload is still a row
        log.warning("could not extract text from %s: %s", filename, exc)
        return ""


async def store_document(
    session: AsyncSession,
    filename: str,
    content_type: str | None,
    data: bytes,
    session_id: str | None = None,
) -> models.Document:
    """Put the bytes in SeaweedFS, extract text, keep the row either way.

    A scanned PDF yields almost nothing; we store `text=""` so callers can tell
    the resident that OCR is out of scope for the demo (`bool(doc.text)` is the
    flag) rather than silently extracting nonsense.

    `session_id` is the conversation the upload belongs to (M20). It is what
    makes an upload count as first contact, so a resident who drops a form in
    before typing anything still owns the session that follows.
    """
    doc_id = (
        await session.execute(
            insert(models.Document)
            .values(
                s3_key="",
                filename=filename,
                content_type=content_type,
                size=len(data),
                session_id=session_id,
            )
            .returning(models.Document.id)
        )
    ).scalar_one()
    key = s3.key_for("documents", doc_id, filename)
    await s3.aput_bytes(key, data, content_type or "application/octet-stream")

    text = await _extract_text(filename, content_type, data)
    if len(text.strip()) < MIN_USEFUL_TEXT:
        log.info("document %s has %d chars of text; treating as scanned", filename, len(text))
        text = ""
    await session.execute(
        update(models.Document).where(models.Document.id == doc_id).values(s3_key=key, text=text)
    )
    await session.commit()
    return (
        (await session.execute(select(models.Document).where(models.Document.id == doc_id))).scalars().one()
    )


async def detect_type(text: str) -> ApplicationType:
    """Classify a document into one of the four workflow types, or unknown."""
    if not (text or "").strip():
        return "unknown"
    result = await chat_json(
        Tier.SMALL,
        [
            {
                "role": "system",
                "content": (
                    "You classify documents submitted to the City of San Diego. Answer with "
                    "exactly one type: 'permit' for a building/construction permit application, "
                    "'business_tax' for a business tax certificate or business registration "
                    "application, 'service_request' for a report of a problem in a public space, "
                    "'stro' for a Short-Term Residential Occupancy (STRO) licence application — a "
                    "short-term rental, vacation rental or home-sharing licence for a dwelling "
                    "unit — or 'unknown' if it is none of those."
                ),
            },
            {"role": "user", "content": text[:DETECT_CHARS]},
        ],
        DetectedType,
        temperature=0.0,
        max_tokens=64,
    )
    return result.type


def _checklist(model: type[BaseModel]) -> str:
    """The field names and their descriptions, spelled out for the extractor.

    The response_format JSON schema already carries these, but a 7B model reads
    the schema as a shape to fill and the prompt as the instructions: without the
    checklist it reliably filled the first section of a form and nulled the rest.
    """
    return "\n".join(f"- {name}: {field.description}" for name, field in model.model_fields.items())


async def extract_fields(text: str, app_type: str) -> dict:
    """Pull the type's fields out of the document text at the EXTRACT tier."""
    model = FIELD_MODELS[app_type]
    result = await chat_json(
        Tier.EXTRACT,
        [
            {
                "role": "system",
                "content": (
                    "You extract application fields from a City of San Diego form. Read the "
                    "whole document before answering and fill in every field you can find.\n\n"
                    "Fields to look for:\n" + _checklist(model) + "\n\n"
                    "Rules: copy values exactly as written in the document; a checkbox marked "
                    "with X is the selected option; return null for any field that is not in "
                    "the document. Never guess, infer or invent a value."
                ),
            },
            # Detection already truncates at DETECT_CHARS; extraction used to send
            # the whole document, which is how a 10 MB .txt became 2.5M tokens.
            {"role": "user", "content": text[:MAX_EXTRACT_CHARS]},
        ],
        model,
        temperature=0.0,
        max_tokens=1024,
    )
    return result.model_dump()


async def submit_from_document(
    session: AsyncSession, document: models.Document, resident_session_id: str | None
) -> tuple[models.Application | None, str]:
    """detect -> extract -> submit. Returns (application, detected type)."""
    text = document.text or ""
    app_type = await detect_type(text)
    if app_type == "unknown":
        return None, app_type
    fields = await extract_fields(text, app_type)
    app = await engine.submit(session, app_type, fields, resident_session_id, document_id=document.id)
    return app, app_type


async def fill_missing_from_message(
    session: AsyncSession, app: models.Application, message: str
) -> models.Application:
    """Read the missing fields out of the resident's reply and resubmit.

    The engine re-validates from `submitted`, so this never decides whether the
    application is now complete — it just adds what it found.
    """
    model = missing_fields_model(app.type, list(app.missing_fields or []))
    found = await chat_json(
        Tier.SMALL,
        [
            {
                "role": "system",
                "content": (
                    "The resident is supplying missing details for a City application. Extract "
                    "only the values they actually stated; return null for anything they did not "
                    "mention. Never guess."
                ),
            },
            {"role": "user", "content": message},
        ],
        model,
        temperature=0.0,
        max_tokens=512,
    )
    merged = dict(app.fields or {})
    supplied = {k: v for k, v in found.model_dump().items() if v not in (None, "")}
    merged.update(supplied)
    await session.execute(
        update(models.Application).where(models.Application.id == app.id).values(fields=merged)
    )
    await session.commit()
    await session.refresh(app)
    return await engine.advance(session, app, "submitted", "resident", "resident supplied missing fields")
