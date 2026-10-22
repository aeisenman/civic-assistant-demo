"""Creates applications rows and their first audit event, in one place.

Called by the create_service_request tool in M2; M3 routes the same function
through the workflow engine so form and document intake share it. Depends on:
app.db.models and the per-type sequences from migration 006_sequences.sql — no
LLM, no HTTP.
"""

import logging

from sqlalchemy import insert, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import clock
from app.db import models

log = logging.getLogger(__name__)

PREFIXES = {"permit": "PRM", "business_tax": "BTC", "service_request": "SR", "stro": "STR"}
# One Postgres sequence per type (006_sequences.sql). Reading MAX(tracking_number)
# and adding one was a read-check-write race: two simultaneous creates produced
# the same number and the loser got a UNIQUE violation, i.e. a 500 for a resident
# who did nothing wrong. nextval() is atomic and O(1) instead of O(rows).
SEQUENCES = {
    "permit": "tracking_permit_seq",
    "business_tax": "tracking_business_tax_seq",
    "service_request": "tracking_service_request_seq",
    # M24, migration 008_stro.sql.
    "stro": "tracking_stro_seq",
}


async def next_tracking_number(session: AsyncSession, app_type: str) -> str:
    """`<PREFIX>-<year>-<6 digits>`, the next value of this type's sequence.

    The year comes from the City's clock, not a constant and not UTC: a number
    minted in 2027 used to still read `-2026-` because YEAR was hard-coded, and
    after that `date.today()` in a UTC container minted `PRM-2027-…` from 4 pm
    Pacific on New Year's Eve.
    """
    prefix = PREFIXES[app_type]
    # The sequence name is a module constant, never caller input.
    value = (await session.execute(text(f"SELECT nextval('{SEQUENCES[app_type]}')"))).scalar_one()
    return f"{prefix}-{clock.today().year}-{int(value):06d}"


async def _insert_application(
    session: AsyncSession,
    tracking: str,
    app_type: str,
    fields: dict,
    department: str | None,
    status: str,
    actor: str,
    resident_session_id: str | None,
    document_id: int | None,
    fee_cents: int | None,
    note: str,
    idempotency_key: str | None,
) -> int:
    """One attempt at the insert pair; returns the new application id."""
    app_id = (
        await session.execute(
            insert(models.Application)
            .values(
                tracking_number=tracking,
                type=app_type,
                status=status,
                fields=fields,
                missing_fields=[],
                department=department,
                fee_cents=fee_cents,
                resident_session_id=resident_session_id,
                document_id=document_id,
                warnings=[],
                idempotency_key=idempotency_key,
            )
            .returning(models.Application.id)
        )
    ).scalar_one()
    await session.execute(
        insert(models.ApplicationEvent).values(
            application_id=app_id,
            from_status=None,
            to_status=status,
            actor=actor,
            note=note,
        )
    )
    await session.commit()
    return app_id


async def create_application(
    session: AsyncSession,
    app_type: str,
    fields: dict,
    department: str | None,
    *,
    status: str = "submitted",
    actor: str = "resident",
    resident_session_id: str | None = None,
    document_id: int | None = None,
    fee_cents: int | None = None,
    note: str = "created from chat",
    idempotency_key: str | None = None,
) -> models.Application:
    """Insert the application and its opening `None -> status` event, committed.

    Retried once on IntegrityError: the sequence makes a collision practically
    impossible, but a number seeded by hand into the fixtures could still occupy
    a sequence value, and a resident should see a tracking number rather than a
    500 in that case.

    `idempotency_key` is whatever the caller sent in `Idempotency-Key`. It is
    covered by a unique partial index (009_runtime.sql), so a replay that races
    the original raises IntegrityError here and the route reads the winner back —
    see app/api/applications.py.
    """
    app_id: int | None = None
    for attempt in (1, 2):
        tracking = await next_tracking_number(session, app_type)
        try:
            app_id = await _insert_application(
                session,
                tracking,
                app_type,
                fields,
                department,
                status,
                actor,
                resident_session_id,
                document_id,
                fee_cents,
                note,
                idempotency_key,
            )
            break
        except IntegrityError:
            await session.rollback()
            if attempt == 2:
                raise
            log.warning("tracking number %s was taken; retrying with the next one", tracking)

    log.info("created %s %s (%s)", app_type, tracking, status)
    return (
        (await session.execute(select(models.Application).where(models.Application.id == app_id)))
        .scalars()
        .one()
    )
