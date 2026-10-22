"""The applications REST surface: the staff queue, the form path, certificates.

Called by web/ (staff page and the inline form) and by scripts/smoke.sh.
Depends on: app.workflows.engine (every status change goes through it),
app.workflows.schemas (form validation), app.storage.s3 (certificate bytes) and
app.auth (the staff guard). Responses are plain dicts with ISO timestamps so the
UI needs no date parsing.

Who may call what (M11): reading the queue, reading one application, advancing
it and downloading its certificate are staff-only, because those are the
back-office actions. POST /api/applications stays open: it is the resident's own
inline form on the chat page, and the resident has no account.
"""

import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_staff
from app.db import models
from app.db.engine import get_session
from app.rate_limit import rate_limit
from app.resident_session import require_or_mint
from app.storage import s3
from app.workflows import engine
from app.workflows.schemas import FIELD_MODELS

log = logging.getLogger(__name__)

router = APIRouter(tags=["applications"])

MAX_LIMIT = 500
# Postgres `integer` tops out here; a bigger number in the path used to reach
# the driver and come back a 500, so it is treated as "no such application".
MAX_DB_INT = 2**31 - 1
# Longer than a bigint can be, so nothing real is refused by the length check.
MAX_ID_DIGITS = 19
# An Idempotency-Key is opaque to us — a UUID from the browser — but it is a
# database value and a log value, so it is bounded like every other input.
MAX_IDEMPOTENCY_KEY_CHARS = 128
# Without a key, an identical payload from the same conversation inside this
# window is treated as the same filing. Long enough to cover a double-click, a
# jittery touchscreen and one retry after a dropped connection; short enough that
# a resident who genuinely files the same service request twice in a minute (the
# same pothole reported from two photos, say) is a case nobody has.
DEDUPE_WINDOW_S = 60


class CreateApplication(BaseModel):
    type: str = Field(description="permit | business_tax | service_request | stro")
    fields: dict = Field(default_factory=dict)
    session_id: str | None = None


class AdvanceRequest(BaseModel):
    to: str
    note: str | None = None


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def _as_dict(app: models.Application) -> dict:
    return {
        "id": app.id,
        "tracking_number": app.tracking_number,
        "type": app.type,
        "status": app.status,
        "fields": app.fields or {},
        "missing_fields": app.missing_fields or [],
        "warnings": app.warnings or [],
        "department": app.department,
        "fee_cents": app.fee_cents,
        "fee_usd": round(app.fee_cents / 100, 2) if app.fee_cents is not None else None,
        "resident_session_id": app.resident_session_id,
        "document_id": app.document_id,
        "certificate_s3_key": app.certificate_s3_key,
        "created_at": _iso(app.created_at),
        "updated_at": _iso(app.updated_at),
    }


async def _find(session: AsyncSession, id_or_tracking: str) -> models.Application:
    """Look up by numeric id or by tracking number; 404 either way."""
    stmt = select(models.Application)
    if id_or_tracking.isdigit():
        # int() itself is the hazard above ~4300 digits: CPython 3.12 refuses to
        # parse it and raises ValueError, which reached the client as a 500.
        # Length first, then the Postgres integer range (audit row 3).
        if len(id_or_tracking) > MAX_ID_DIGITS:
            raise HTTPException(status_code=404, detail="no application")
        numeric = int(id_or_tracking)
        if numeric > MAX_DB_INT:
            raise HTTPException(status_code=404, detail=f"no application '{id_or_tracking}'")
        stmt = stmt.where(models.Application.id == numeric)
    else:
        stmt = stmt.where(func.lower(models.Application.tracking_number) == id_or_tracking.lower())
    app = (await session.execute(stmt)).scalars().first()
    if app is None:
        raise HTTPException(status_code=404, detail=f"no application '{id_or_tracking}'")
    return app


@router.get("/api/applications", dependencies=[Depends(require_staff)])
async def list_applications(
    status: str | None = None,
    type: str | None = None,
    # Bounded here rather than clamped in the query: LIMIT -1 is a 500 from the
    # driver, and a caller who asks for 100000 rows should be told the ceiling.
    limit: int = Query(default=100, ge=1, le=MAX_LIMIT),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """The staff queue. Newest first, because staff work the top of the list."""
    stmt = select(models.Application).order_by(desc(models.Application.id))
    if status:
        stmt = stmt.where(models.Application.status == status)
    if type:
        stmt = stmt.where(models.Application.type == type)
    rows = (await session.execute(stmt.limit(limit))).scalars().all()
    return [_as_dict(a) for a in rows]


@router.get("/api/applications/{id_or_tracking}", dependencies=[Depends(require_staff)])
async def get_application(id_or_tracking: str, session: AsyncSession = Depends(get_session)) -> dict:
    """One application with its full timeline: the staff detail panel's whole payload."""
    app = await _find(session, id_or_tracking)
    events = (
        (
            await session.execute(
                select(models.ApplicationEvent)
                .where(models.ApplicationEvent.application_id == app.id)
                .order_by(models.ApplicationEvent.id)
            )
        )
        .scalars()
        .all()
    )
    return {
        **_as_dict(app),
        "events": [
            {
                "id": e.id,
                "from_status": e.from_status,
                "to_status": e.to_status,
                "actor": e.actor,
                "note": e.note,
                "created_at": _iso(e.created_at),
            }
            for e in events
        ],
        "allowed_transitions": engine.allowed_transitions(app),
    }


async def _by_idempotency_key(session: AsyncSession, key: str) -> models.Application | None:
    """The application already filed under this key, if there is one."""
    return (
        (await session.execute(select(models.Application).where(models.Application.idempotency_key == key)))
        .scalars()
        .first()
    )


async def _recent_duplicate(
    session: AsyncSession, session_id: str, app_type: str, fields: dict
) -> models.Application | None:
    """The same payload from the same conversation inside DEDUPE_WINDOW_S, if any.

    The fallback for a client that sends no Idempotency-Key — which is every
    caller written before this endpoint had one, including the current smoke
    script. Identity is the whole normalised payload: same type, same fields,
    same conversation, a moment ago. Comparing the stored `fields` dict *is* the
    JSON hash, computed by Postgres on the way out rather than stored in a column
    nobody would otherwise read.
    """
    cutoff = func.now() - timedelta(seconds=DEDUPE_WINDOW_S)
    rows = (
        (
            await session.execute(
                select(models.Application)
                .where(
                    models.Application.resident_session_id == session_id,
                    models.Application.type == app_type,
                    models.Application.created_at >= cutoff,
                )
                .order_by(desc(models.Application.id))
                .limit(5)
            )
        )
        .scalars()
        .all()
    )
    return next((row for row in rows if (row.fields or {}) == fields), None)


@router.post("/api/applications", dependencies=[Depends(rate_limit)])
async def create_application(
    body: CreateApplication,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
        min_length=1,
        max_length=MAX_IDEMPOTENCY_KEY_CHARS,
    ),
) -> dict:
    """File an application from the inline form, through the same engine a PDF uses.

    Filing is not safe to repeat: the load test double-clicked Submit 30 times and
    got 30 tracking numbers, which in a real City is 30 inspections to cancel. Two
    guards, in order of how much the caller told us:

    1. `Idempotency-Key`: a replay returns the original row with a 200. The key is
       unique in the database, so two replays racing each other still produce one
       application — the loser reads the winner's row back.
    2. No key: the same `type` and the same normalised `fields` from the same
       `session_id` inside a minute is the same filing.

    Both return the original row rather than a 409, because from the resident's
    side nothing went wrong: they pressed Submit and their application exists.
    """
    # The inline form is part of a conversation, so it is bound to it like a chat
    # turn: filing under someone else's session id would attach the application
    # to their history. A body with no session id (a direct API caller, a seed
    # script) is unbound and unchanged.
    if body.session_id:
        await require_or_mint(session, body.session_id, request, response)

    if idempotency_key:
        existing = await _by_idempotency_key(session, idempotency_key)
        if existing is not None:
            log.info("idempotent replay of %s", existing.tracking_number)
            return _as_dict(existing)

    model = FIELD_MODELS.get(body.type)
    if model is None:
        raise HTTPException(status_code=422, detail=f"unknown application type '{body.type}'")
    # Validate against the same model the extractor fills, then store the
    # normalised dict so form and document intake produce identical rows. A bad
    # field type is the caller's mistake, so it is a 422 like any other body error.
    try:
        parsed = model.model_validate(body.fields).model_dump()
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors(include_url=False)) from exc

    if not idempotency_key and body.session_id:
        duplicate = await _recent_duplicate(session, body.session_id, body.type, parsed)
        if duplicate is not None:
            log.info("duplicate submit within %ss: %s", DEDUPE_WINDOW_S, duplicate.tracking_number)
            return _as_dict(duplicate)

    try:
        app = await engine.submit(
            session, body.type, parsed, body.session_id, idempotency_key=idempotency_key
        )
    except IntegrityError:
        # Two replays of the same key arrived at once and the unique index picked
        # a winner. Read it back rather than answering 500 for a request that in
        # fact did exactly what it asked.
        await session.rollback()
        existing = await _by_idempotency_key(session, idempotency_key) if idempotency_key else None
        if existing is None:
            raise
        log.info("idempotent replay raced, returning %s", existing.tracking_number)
        return _as_dict(existing)
    return _as_dict(app)


@router.post("/api/applications/{id_or_tracking}/advance")
async def advance_application(
    id_or_tracking: str,
    body: AdvanceRequest,
    session: AsyncSession = Depends(get_session),
    staff: models.StaffUser = Depends(require_staff),
) -> dict:
    """Move one application along the status spine; 409 when the spine forbids it."""
    app = await _find(session, id_or_tracking)
    try:
        # The timeline names a person, not the string "staff": the audit row is
        # the only record of who issued a certificate.
        await engine.advance(session, app, body.to, staff.username, body.note)
    except engine.InvalidTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except engine.HookFailed as exc:
        # Object storage is down: the status did not move, so this is a
        # try-again-later, not a bad request and not an unexplained 500.
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return _as_dict(app)


@router.get("/api/applications/{id_or_tracking}/certificate", dependencies=[Depends(require_staff)])
async def get_certificate(id_or_tracking: str, session: AsyncSession = Depends(get_session)) -> Response:
    """The issued certificate PDF inline, so a reviewer can eyeball it in the browser."""
    app = await _find(session, id_or_tracking)
    if not app.certificate_s3_key:
        raise HTTPException(
            status_code=404,
            detail=f"{app.tracking_number} has no certificate yet (status '{app.status}')",
        )
    try:
        data = await s3.aget_bytes(app.certificate_s3_key)
    except Exception as exc:  # noqa: BLE001 - a missing object is a 404, not a 500
        log.warning("certificate %s unreadable: %s", app.certificate_s3_key, exc)
        raise HTTPException(
            status_code=404,
            detail=f"{app.tracking_number} has a certificate on record but it could not be read",
        ) from exc
    filename = f"{app.tracking_number}.pdf"
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )
