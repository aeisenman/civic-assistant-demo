"""POST /api/documents — the upload half of document intake.

Called by the chat composer's file drop; the returned document_id is passed back
to POST /api/chat as `document_ids`. Depends on: app.workflows.intake for the
storage + text extraction. Kept separate from applications.py because uploading
a file and filing an application are two different resident actions.
"""

import posixpath
import re

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_session
from app.rate_limit import rate_limit
from app.resident_session import SESSION_ID_PATTERN, require_or_mint
from app.workflows import intake

router = APIRouter(tags=["documents"])

PREVIEW_CHARS = 300
# The whole upload is read into memory and stored, so it needs a ceiling: a
# City application PDF is tens of kilobytes and 20 MB of anything was accepted.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
# Read in 64 KB bites with a running total, so a 2 GB body is refused after the
# first chunk instead of after 2 GB has landed in RSS.
UPLOAD_CHUNK_BYTES = 64 * 1024
# Everything intake.py can actually read. An allow-list rather than a deny-list:
# a .exe renamed .pdf still has to claim one of these, and a claim of
# application/pdf that is not a PDF simply extracts to no text.
ALLOWED_CONTENT_TYPES = ("application/pdf", "text/plain", "text/markdown")
MAX_FILENAME_CHARS = 120
FALLBACK_FILENAME = "upload"
# Control characters, including the NULs and newlines that make a filename look
# like two lines in a log or a staff table.
CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


def safe_filename(raw: str | None) -> str:
    """The stored, echoed-back name: a basename, printable, at most 120 chars.

    The S3 key was already sanitised, but the row and the API response kept
    whatever the client sent — `../../../../etc/passwd` came straight back out
    (red-team finding 20). Nothing downstream opens this name as a path, so this
    is about not handing a staff screen or a log a string that lies about what
    was uploaded. The extension is preserved when the name has to be shortened,
    because that is what tells a reviewer it is a PDF.
    """
    name = CONTROL_CHARS.sub("", raw or "").strip()
    # Both separators: a Windows client sends backslashes, posixpath ignores them.
    name = posixpath.basename(name.replace("\\", "/")).strip(" .")
    if not name:
        return FALLBACK_FILENAME
    if len(name) <= MAX_FILENAME_CHARS:
        return name
    stem, dot, ext = name.rpartition(".")
    if not dot or len(ext) > 10:  # no usable extension: just cut it short
        return name[:MAX_FILENAME_CHARS]
    return stem[: MAX_FILENAME_CHARS - len(ext) - 1] + "." + ext


def base_content_type(raw: str | None) -> str:
    """'text/plain; charset=utf-8' -> 'text/plain', lower-cased, for the allow-list."""
    return (raw or "").split(";", 1)[0].strip().lower()


def _too_big(filename: str, byte_count: int) -> HTTPException:
    """The one 413 message, so a declared size and a measured size read the same."""
    return HTTPException(
        status_code=413,
        detail=(
            f"{filename} is {byte_count / 1_048_576:.1f} MB; the limit "
            f"is {MAX_UPLOAD_BYTES // 1_048_576} MB. Upload the application form only."
        ),
    )


async def read_bounded(file: UploadFile, filename: str) -> bytes:
    """Read the upload in chunks, giving up the moment the running total is over.

    `await file.read()` with no argument used to pull the whole body into memory
    and only then compare it to the limit, so a 2 GB upload cost 2 GB of RSS to
    earn its 413 (audit row 2).
    """
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(UPLOAD_CHUNK_BYTES):
        total += len(chunk)
        if total > MAX_UPLOAD_BYTES:
            raise _too_big(filename, total)
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/api/documents", dependencies=[Depends(rate_limit)])
async def upload_document(
    request: Request,
    response: Response,
    file: UploadFile = File(...),
    # Part of the multipart body, not a query string: the browser is already
    # sending a form, and a session id in a URL ends up in access logs and
    # referrers. Optional so a caller that predates M20 (an older smoke script)
    # still uploads; when it is present the upload joins that conversation and
    # is bound to it like a chat turn.
    session_id: str | None = Form(default=None, pattern=SESSION_ID_PATTERN),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Store one upload and return the id the chat turn quotes as `document_ids`."""
    if session_id:
        await require_or_mint(session, session_id, request, response)

    filename = safe_filename(file.filename)

    content_type = base_content_type(file.content_type)
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=415,
            detail=(
                f"{filename} is '{content_type or 'unknown'}'. Upload a PDF, a text file or a markdown file."
            ),
        )

    # Cheapest check first: what the client says it is sending, before a byte of
    # it is read. `file.size` is what starlette measured while spooling the part;
    # Content-Length covers the whole multipart body, so it is only ever an
    # over-estimate of this part and is used only when there is no size.
    declared = file.size
    if declared is None:
        try:
            declared = int(request.headers.get("content-length") or 0)
        except ValueError:
            declared = 0
    if declared and declared > MAX_UPLOAD_BYTES:
        raise _too_big(filename, declared)

    data = await read_bounded(file, filename)
    doc = await intake.store_document(session, filename, content_type, data, session_id)
    return {
        "document_id": doc.id,
        "filename": doc.filename,
        "content_type": doc.content_type,
        "size": doc.size,
        "text_preview": (doc.text or "")[:PREVIEW_CHARS],
        # False for a scanned PDF: no OCR in the demo, so the chat says so.
        "has_text": bool(doc.text),
    }
