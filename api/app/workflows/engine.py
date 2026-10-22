"""The state machine: the only place an application's status changes.

Called by the intake path (app/workflows/intake.py), the worker
(app/workflows/worker.py) and the staff API (app/api/applications.py). Depends
on: app.workflows.store (row creation), validators (the `validating` hook) and
certificates (the `issued` hook). Every transition writes an application_events
row, so the staff timeline is a byproduct of the engine rather than extra work.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models
from app.workflows import certificates, store, validators

log = logging.getLogger(__name__)


class InvalidTransition(Exception):
    """Raised when a caller asks for a status the spine does not allow.

    Also raised when the row moved underneath us between the read and the write:
    from the caller's point of view the transition is illegal either way, and
    the API answers 409 for both.
    """


class HookFailed(Exception):
    """A pre-commit entry hook could not do its job, so the status did not move.

    Today that only means "the certificate could not be stored". The API turns it
    into a 503: the request failed, nothing was written, and retrying is the fix.
    """


# The status spine, shared by all three application types (PLAN.md §6).
TRANSITIONS: dict[str, list[str]] = {
    "draft": ["submitted"],
    "submitted": ["validating"],
    "validating": ["needs_info", "routed"],
    "needs_info": ["submitted"],
    "routed": ["in_review"],
    "in_review": ["approved", "rejected"],
    "approved": ["issued"],
    "issued": ["closed"],
    "rejected": ["closed"],
    "closed": [],
}

# Statuses the worker moves on by itself. `validating` has no fixed target:
# the validator decides between needs_info and routed.
AUTO: dict[str, str | None] = {
    "submitted": "validating",
    "validating": None,
    "routed": "in_review",
}

# Everything else needs a person (or the API) to push it.
MANUAL: dict[str, list[str]] = {
    status: targets for status, targets in TRANSITIONS.items() if status not in AUTO
}


def allowed_transitions(app: models.Application) -> list[str]:
    """Statuses this application may move to right now."""
    return list(TRANSITIONS.get(app.status, []))


async def _on_validating(session: AsyncSession, app: models.Application) -> None:
    """Run the validator, persist its findings, and route or ask for more.

    This hook decides the next status itself, which is why AUTO["validating"] is
    None: the worker must not guess.
    """
    result = await validators.validate(session, app)
    await session.execute(
        update(models.Application)
        .where(models.Application.id == app.id)
        .values(
            missing_fields=result.missing,
            warnings=result.warnings,
            fee_cents=result.fee_cents,
            department=result.department,
        )
    )
    await session.commit()
    await session.refresh(app)
    target = "needs_info" if result.missing else "routed"
    note = f"missing: {', '.join(result.missing)}" if result.missing else f"routed to {result.department}"
    await advance(session, app, target, "system", note)


async def _certificate_key(app: models.Application) -> str:
    """Render the PDF, put it in object storage, return the key to persist.

    Called *before* the status commit (see BEFORE_COMMIT). Stopping SeaweedFS and
    advancing approved -> issued used to leave the row `issued` for ever with a
    NULL certificate key, i.e. a status the staff page could not act on and a
    download that 404s. Now the transition simply fails and can be retried.

    `to_thread`, because reportlab's render and boto3's PUT are both synchronous
    and this runs while the application row is held under SELECT … FOR UPDATE: on
    the event loop it stalled every in-flight SSE stream and /health for the
    duration of a slow object store, with the row locked the whole time.
    """
    try:
        return await asyncio.to_thread(
            certificates.store_certificate,
            app.type,
            app.tracking_number,
            app.fields or {},
            department=app.department,
            fee_cents=app.fee_cents,
        )
    except Exception as exc:  # noqa: BLE001 - boto3/reportlab raise many types
        raise HookFailed(
            f"{app.tracking_number}: the certificate could not be stored, so the "
            "application is still approved. Try issuing it again in a moment."
        ) from exc


async def _prepare_issued(session: AsyncSession, app: models.Application) -> dict:
    """BEFORE_COMMIT hook for `issued`: the certificate key goes in the same UPDATE."""
    return {"certificate_s3_key": await _certificate_key(app)}


# Hooks that must succeed *before* the status is committed, and whose return
# value is merged into the same UPDATE. Keyed by the status being entered.
BEFORE_COMMIT: dict[str, Callable[[AsyncSession, models.Application], Awaitable[dict]]] = {
    "issued": _prepare_issued,
}

# Hooks that run *after* the commit, because they decide the next transition
# themselves and so must see a settled row.
ON_ENTER: dict[str, Callable[[AsyncSession, models.Application], Awaitable[None]]] = {
    "validating": _on_validating,
}


async def backfill_certificate(session: AsyncSession, app: models.Application) -> str | None:
    """Store a missing certificate for a row that is already `issued`.

    Only reachable for rows issued before the BEFORE_COMMIT hook existed, or if
    someone sets the status by hand. The worker calls this on every tick; it is
    a no-op once the key is set.
    """
    if app.status != "issued" or app.certificate_s3_key:
        return None
    key = await _certificate_key(app)
    await session.execute(
        update(models.Application)
        .where(models.Application.id == app.id, models.Application.certificate_s3_key.is_(None))
        .values(certificate_s3_key=key)
    )
    await session.commit()
    await session.refresh(app)
    log.info("backfilled certificate for %s", app.tracking_number)
    return key


async def advance(
    session: AsyncSession,
    app: models.Application,
    to: str,
    actor: str,
    note: str | None = None,
) -> models.Application:
    """Move `app` to `to` under a row lock, audit it, then run the entry hook.

    The lock plus the `status == from_status` guard on the UPDATE is what makes a
    double-click (or the worker racing a staff button) produce exactly one event
    row: the loser sees no rows updated and raises InvalidTransition, which the
    API answers 409.
    """
    if to not in TRANSITIONS.get(app.status, []):
        raise InvalidTransition(
            f"{app.tracking_number}: cannot go from '{app.status}' to '{to}' "
            f"(allowed: {', '.join(TRANSITIONS.get(app.status, [])) or 'none'})"
        )
    from_status = app.status

    # SELECT ... FOR UPDATE: the second caller blocks here until the first
    # commits, then reads the new status and gives up below.
    locked = (
        await session.execute(
            select(models.Application.status).where(models.Application.id == app.id).with_for_update()
        )
    ).scalar_one_or_none()
    if locked != from_status:
        await session.rollback()
        raise InvalidTransition(
            f"{app.tracking_number}: cannot go from '{from_status}' to '{to}' — "
            f"the application is now '{locked or 'gone'}'"
        )

    values: dict = {"status": to, "updated_at": datetime.now(UTC)}
    prepare = BEFORE_COMMIT.get(to)
    if prepare is not None:
        try:
            values.update(await prepare(session, app))
        except HookFailed:
            # Nothing has been written yet; drop the lock and let the caller 503.
            await session.rollback()
            raise

    result = await session.execute(
        update(models.Application)
        .where(models.Application.id == app.id, models.Application.status == from_status)
        .values(**values)
    )
    # Belt and braces with the lock above: on a database that ignored the lock,
    # the conditional UPDATE still lets exactly one caller through.
    if getattr(result, "rowcount", 1) == 0:
        await session.rollback()
        raise InvalidTransition(
            f"{app.tracking_number}: '{from_status}' -> '{to}' lost a concurrent "
            "transition; nothing was changed"
        )
    await session.execute(
        insert(models.ApplicationEvent).values(
            application_id=app.id,
            from_status=from_status,
            to_status=to,
            actor=actor,
            note=note,
        )
    )
    await session.commit()
    await session.refresh(app)
    log.info("%s %s -> %s by %s", app.tracking_number, from_status, to, actor)

    hook = ON_ENTER.get(to)
    if hook is not None:
        await hook(session, app)
    return app


async def run_auto(session: AsyncSession, app: models.Application) -> models.Application:
    """One automatic step for the worker: AUTO's target, or re-run the validator.

    An application only sits in `validating` if a previous hook died mid-flight,
    so re-running it is both the normal path and the recovery path.
    """
    if app.status == "validating":
        await _on_validating(session, app)
        return app
    target = AUTO.get(app.status)
    if target is None:
        return app
    return await advance(session, app, target, "system")


async def submit(
    session: AsyncSession,
    app_type: str,
    fields: dict,
    resident_session_id: str | None = None,
    document_id: int | None = None,
    idempotency_key: str | None = None,
) -> models.Application:
    """Create an application already in `submitted`, with its opening event."""
    return await store.create_application(
        session,
        app_type,
        fields,
        department=None,
        status="submitted",
        actor="resident",
        resident_session_id=resident_session_id,
        document_id=document_id,
        idempotency_key=idempotency_key,
    )


async def latest_for_session(
    session: AsyncSession, resident_session_id: str, status: str
) -> models.Application | None:
    """Most recent application for a chat session in `status` (for gap-filling)."""
    return (
        (
            await session.execute(
                select(models.Application)
                .where(
                    models.Application.resident_session_id == resident_session_id,
                    models.Application.status == status,
                )
                .order_by(models.Application.id.desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )
