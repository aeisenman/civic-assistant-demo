"""The background task that moves applications through their automatic statuses.

Started as an asyncio task by the lifespan in app/main.py when WORKER_ENABLED,
cancelled on shutdown. Depends on: app.workflows.engine (AUTO and run_auto) and
its own database session — it is not tied to a request. A polling loop rather
than Celery: one process, no broker, and the whole thing fits on a slide.
"""

import asyncio
import logging

from sqlalchemy import select, text

from app import clock
from app.config import settings
from app.db import models
from app.db.engine import SessionLocal
from app.workflows import engine

log = logging.getLogger(__name__)

# submitted -> validating, routed -> in_review, plus validating itself, which the
# validator resolves into needs_info or routed.
AUTO_STATUSES = [s for s, target in engine.AUTO.items() if target is not None] + ["validating"]
BATCH = 25

#: Claim one row, in its own transaction, and skip it if another worker already
#: holds it. Without SKIP LOCKED a second replica does not error — it *blocks*
#: on the row lock and then runs the same transition a moment later, which is
#: how one application ends up with two identical timeline entries. With it, the
#: second worker sees no row and moves on to the next one.
CLAIM_SQL = text(
    """
    SELECT id FROM applications
    WHERE id = :id AND status = ANY(:statuses)
    FOR UPDATE SKIP LOCKED
    """
)

#: Retention sweep. Two statements because the FK from chat_messages to traces is
#: ON DELETE SET NULL: deleting the messages first means Postgres never has to
#: rewrite rows it is about to delete anyway.
RETENTION_SQL = (
    text("DELETE FROM chat_messages WHERE created_at < now() - make_interval(days => :days)"),
    text("DELETE FROM traces WHERE created_at < now() - make_interval(days => :days)"),
)

#: The City day the sweep last ran on, so it runs once a day rather than every
#: three seconds. Process-local on purpose: a second replica sweeping the same
#: rows a second time deletes nothing new.
_swept_on = None


async def _recover_missing_certificates(session) -> int:
    """Store certificates for rows that are `issued` with no certificate key.

    The issued hook now stores the PDF before the status commits, so this can only
    find rows issued before that change (or set by hand in the database). Keeping
    the sweep means such a row heals itself within three seconds instead of
    returning a 404 from the certificate download for ever.
    """
    stranded = (
        (
            await session.execute(
                select(models.Application)
                .where(
                    models.Application.status == "issued",
                    models.Application.certificate_s3_key.is_(None),
                )
                .order_by(models.Application.id)
                .limit(BATCH)
            )
        )
        .scalars()
        .all()
    )
    healed = 0
    for app in stranded:
        try:
            if await engine.backfill_certificate(session, app):
                healed += 1
        except Exception:  # noqa: BLE001 - object storage may still be down
            log.exception("worker: no certificate for issued %s", app.tracking_number)
    return healed


async def _candidate_ids() -> list[int]:
    """The ids currently sitting on an automatic status, oldest first."""
    async with SessionLocal() as session:
        rows = await session.execute(
            select(models.Application.id)
            .where(models.Application.status.in_(AUTO_STATUSES))
            .order_by(models.Application.id)
            .limit(BATCH)
        )
        return [row[0] for row in rows]


async def _advance_one(app_id: int) -> bool:
    """Claim one application and run its automatic transition. True if it moved.

    One session, one transaction per row. The claim is `FOR UPDATE SKIP LOCKED`,
    so with two API replicas each row is worked by exactly one of them instead of
    both of them queueing on the same lock and writing the same transition twice.
    Re-checking `status` inside the claim also drops a row that another worker
    already moved between the id listing and here.

    `engine.run_auto` commits as it goes (it writes an audit row per transition),
    which ends this transaction and releases the claim — the guarantee that
    survives after that is `advance()`'s own SELECT … FOR UPDATE plus its
    status-conditional UPDATE, which M15 added for exactly this reason. The claim
    is what stops two workers *starting* the same row.
    """
    async with SessionLocal() as session:
        claimed = (
            await session.execute(CLAIM_SQL, {"id": app_id, "statuses": AUTO_STATUSES})
        ).scalar_one_or_none()
        if claimed is None:
            return False
        app = await session.get(models.Application, app_id)
        if app is None:
            return False
        before = app.status
        try:
            await engine.run_auto(session, app)
        except Exception:  # noqa: BLE001 - one bad row must not stop the loop
            log.exception("worker: %s stuck in %s", app.tracking_number, before)
            return False
        if app.status != before:
            log.info("worker advanced %s %s -> %s", app.tracking_number, before, app.status)
            return True
        return False


async def tick() -> int:
    """Advance every application on an automatic status, then heal stranded ones."""
    moved = 0
    for app_id in await _candidate_ids():
        moved += await _advance_one(app_id)
    async with SessionLocal() as session:
        try:
            moved += await _recover_missing_certificates(session)
        except Exception:  # noqa: BLE001 - the sweep must not stop the loop either
            log.exception("worker: certificate recovery sweep failed")
    return moved


async def retention_sweep() -> dict[str, int]:
    """Delete traces and chat messages past TRACE_RETENTION_DAYS. Once per City day.

    Off by default (0 = keep everything), because the demo's whole point is that a
    reviewer can open /staff/traces and read the turn they just had. A real City
    sets a number — and the number is a records-retention decision, not a privacy
    one: California keeps records of a resident interaction for at least two
    years, so 730 is the floor rather than the 30 or 90 that feels tidy.

    Returns the rows deleted per table, `{}` when the sweep did not run, so the
    caller can log it and a test can assert the no-op.
    """
    global _swept_on
    days = settings.trace_retention_days
    if days <= 0:
        return {}
    day = clock.today()
    if _swept_on == day:
        return {}
    _swept_on = day
    deleted: dict[str, int] = {}
    async with SessionLocal() as session:
        for statement in RETENTION_SQL:
            result = await session.execute(statement, {"days": days})
            table = "chat_messages" if "chat_messages" in str(statement) else "traces"
            deleted[table] = int(getattr(result, "rowcount", 0) or 0)
        await session.commit()
    log.info("retention sweep (>%d days): %s", days, deleted)
    return deleted


async def run_forever(interval: float = 3) -> None:
    """Poll every `interval` seconds until the task is cancelled."""
    log.info("workflow worker started (every %ss)", interval)
    try:
        while True:
            try:
                await tick()
            except Exception:  # noqa: BLE001 - a dead DB should not kill the loop
                log.exception("worker tick failed")
            try:
                await retention_sweep()
            except Exception:  # noqa: BLE001 - nor should a failed sweep
                log.exception("worker retention sweep failed")
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        log.info("workflow worker stopped")
        raise
