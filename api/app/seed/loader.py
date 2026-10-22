"""Loads api/seed_data/*.json into the reference tables at startup.

Called by the lifespan in app/main.py when SEED_ON_STARTUP=true. Reference tables
are truncate-then-insert (editing a JSON file and restarting is the whole
workflow); anything a resident writes to is upserted, never truncated. Depends
on: app.db.models for the target tables and app.auth for the one staff account.
"""

import json
import logging
from datetime import date
from pathlib import Path

from sqlalchemy import Date, Integer, insert, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app import auth
from app.db import models
from app.db.engine import SessionLocal

log = logging.getLogger(__name__)

SEED_DIR = Path(__file__).resolve().parents[2] / "seed_data"

# filename -> model, for the reference tables. Order matters only for
# readability; there are no FKs here. Sample applications are NOT in this map:
# they are upserted below, because `applications` holds resident data.
FILES: dict[str, type] = {
    "trash_zones.json": models.TrashZone,
    "addresses.json": models.Address,
    "events.json": models.Event,
    "permit_types.json": models.PermitType,
    "service_categories.json": models.ServiceCategory,
    "referrals.json": models.Referral,
    "council_districts.json": models.CouncilDistrict,
}

# Tables this module must never TRUNCATE, whatever a future seed file says.
# `TRUNCATE applications ... CASCADE` on every restart (the default was
# SEED_ON_STARTUP=true) silently deleted every application a resident had filed
# and every event row pointing at it, leaving orphaned certificates in S3.
NEVER_TRUNCATE = {
    "applications",
    "application_events",
    "documents",
    "chat_messages",
    "traces",
    "staff_users",
    "staff_sessions",
}


def _coerce(model: type, row: dict) -> dict:
    """Keep only real columns and turn ISO date strings into date objects.

    The JSON files are written by hand, so be forgiving about extra keys but
    strict about types asyncpg cares about.
    """
    columns = model.__table__.columns
    clean: dict = {}
    for key, value in row.items():
        col = columns.get(key)
        if col is None:
            continue
        if isinstance(col.type, Date) and isinstance(value, str):
            value = date.fromisoformat(value)
        elif isinstance(col.type, Integer) and isinstance(value, str) and value.isdigit():
            value = int(value)
        clean[key] = value
    return clean


def _rows(path: Path) -> list[dict]:
    rows = json.loads(path.read_text())
    if not isinstance(rows, list):
        raise ValueError(f"{path.name}: expected a JSON array")
    return rows


async def _load_file(session: AsyncSession, path: Path, model: type) -> int:
    """Truncate-and-reload one reference table."""
    table = model.__table__
    if table.name in NEVER_TRUNCATE:
        raise ValueError(f"refusing to truncate {table.name}: it holds resident data")
    # RESTART IDENTITY so ids stay stable across restarts; CASCADE because a
    # reference row may already be referenced elsewhere.
    await session.execute(text(f"TRUNCATE TABLE {table.name} RESTART IDENTITY CASCADE"))
    payload = [_coerce(model, r) for r in _rows(path)]
    if payload:
        await session.execute(insert(table), payload)
    return len(payload)


async def _upsert_applications(session: AsyncSession, path: Path) -> int:
    """Insert the sample applications that are missing; leave every row alone.

    ON CONFLICT (tracking_number) DO NOTHING rather than DO UPDATE on purpose: if
    a reviewer has advanced PRM-2026-000101 to `issued`, a restart must not drag
    it back to `rejected`. Returns the number of rows actually inserted.
    """
    payload = [_coerce(models.Application, r) for r in _rows(path)]
    if not payload:
        return 0
    existing = set(
        (
            await session.execute(
                select(models.Application.tracking_number).where(
                    models.Application.tracking_number.in_([r["tracking_number"] for r in payload])
                )
            )
        )
        .scalars()
        .all()
    )
    inserted = 0
    for row in payload:
        if row["tracking_number"] in existing:
            continue
        await session.execute(
            pg_insert(models.Application.__table__)
            .values(**row)
            .on_conflict_do_nothing(index_elements=["tracking_number"])
        )
        inserted += 1
    return inserted


async def seed_all() -> dict[str, int]:
    """Reload every present reference file, upsert the samples; {filename: rows}."""
    result: dict[str, int] = {}
    async with SessionLocal() as session:
        for filename, model in FILES.items():
            path = SEED_DIR / filename
            if not path.exists():
                log.info("seed: %s absent, skipping", filename)
                continue
            count = await _load_file(session, path, model)
            result[filename] = count
            log.info("seed: %s -> %d rows", filename, count)

        samples = SEED_DIR / "sample_applications.json"
        if samples.exists():
            added = await _upsert_applications(session, samples)
            result["sample_applications.json"] = added
            log.info("seed: sample_applications.json -> %d new rows (existing kept)", added)

        await session.commit()
        # Upsert, never truncate: wiping staff_users would log every open
        # browser out (the sessions cascade) every time the demo restarts.
        await auth.ensure_staff_user(session)
        result["staff_user"] = 1
    return result
