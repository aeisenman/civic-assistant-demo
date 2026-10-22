"""Applies app/db/migrations/*.sql in filename order, once each, and rolls one back.

Called by the lifespan in app/main.py before anything else touches the schema,
and by hand as `python -m app.db.migrations [--rollback <file>]`. Depends on:
app.db.engine and app.config (EMBED_DIM substitution). No Alembic: plain SQL
files are fewer concepts to explain in a demo.
"""

import argparse
import asyncio
import logging
import re
from pathlib import Path

from sqlalchemy import text

from app.config import settings
from app.db.engine import engine, wait_for_db

log = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

# An arbitrary but fixed key: any process running this module takes the same
# lock, so `docker compose up --scale api=2` serialises the migration run
# instead of both replicas reading an empty schema_migrations and racing.
ADVISORY_LOCK_KEY = 4815162342

# Down migrations live beside their forward file as <name>.down.sql. They end in
# .sql, so every glob for forward migrations has to filter them back out — a
# `007_m19.down.sql` applied as a migration would drop the columns 007 just made.
DOWN_SUFFIX = ".down.sql"

_TRACKING_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename   TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

# The declared width of the vector column, as Postgres itself reports it:
# format_type folds atttypmod back into the type name, so this comes back as
# the literal string "vector(768)". Reading pg_attribute rather than a sample
# row means the check works on an empty kb_chunks, which is the normal state in
# CI (INGEST_KB_ON_STARTUP=false).
_EMBEDDING_WIDTH_SQL = """
SELECT format_type(a.atttypid, a.atttypmod)
  FROM pg_attribute a
  JOIN pg_class c ON c.oid = a.attrelid
 WHERE c.relname = 'kb_chunks'
   AND a.attname = 'embedding'
   AND a.attnum > 0
   AND NOT a.attisdropped
"""


def forward_migrations() -> list[Path]:
    """Every forward .sql file in filename order, down migrations excluded."""
    return sorted(p for p in MIGRATIONS_DIR.glob("*.sql") if not p.name.endswith(DOWN_SUFFIX))


def _render(sql: str) -> str:
    """Substitute build-time placeholders. Only the vector width so far."""
    return sql.replace("{{EMBED_DIM}}", str(settings.embed_dim))


def declared_width(format_type: str | None) -> int | None:
    """Parse "vector(768)" into 768; None when the column or the modifier is absent."""
    found = re.search(r"\((\d+)\)", format_type or "")
    return int(found.group(1)) if found else None


async def check_embedding_width(conn) -> int | None:
    """Fail loudly when kb_chunks.embedding is not EMBED_DIM wide.

    Migration 002 bakes EMBED_DIM into the column when the database is *first*
    created and is then never re-run, so pointing an existing 768-wide database
    at a 1024-wide embedding model used to produce no error at all until the
    first INSERT, deep inside a KB ingest, hours later (audit finding 10). This
    turns that into a refusal at startup with the command that fixes it.
    """
    result = await conn.execute(text(_EMBEDDING_WIDTH_SQL))
    width = declared_width(result.scalar_one_or_none())
    if width is None:
        # No kb_chunks yet (a migration failed above) — that failure is the one
        # worth reporting, so say what we saw and let the caller surface it.
        log.warning("kb_chunks.embedding not found; skipping the vector width check")
        return None
    if width != settings.embed_dim:
        raise RuntimeError(
            f"kb_chunks.embedding is vector({width}) but EMBED_DIM={settings.embed_dim}. "
            "Migration 002 fixes the width when the database is created and is never re-run, "
            "so an existing database cannot follow a change of embedding model. "
            "Either set EMBED_DIM back to "
            f"{width}, or recreate the database with `scripts/reset_demo.sh` "
            "(it backs up first) so the schema is rebuilt at the new width."
        )
    log.info("kb_chunks.embedding is vector(%d), matching EMBED_DIM", width)
    return width


async def _apply_pending() -> list[str]:
    """Apply any unapplied .sql file. Caller holds the advisory lock."""
    applied: list[str] = []
    async with engine.begin() as conn:
        await conn.execute(text(_TRACKING_TABLE))
        rows = await conn.execute(text("SELECT filename FROM schema_migrations"))
        done = {r[0] for r in rows}

    for path in forward_migrations():
        if path.name in done:
            continue
        log.info("applying migration %s", path.name)
        # One transaction per file: a failed migration leaves no partial schema.
        async with engine.begin() as conn:
            # asyncpg refuses multi-statement *prepared* queries, so hand the
            # whole file to the raw driver connection, which allows them.
            raw = await conn.get_raw_connection()
            await raw.driver_connection.execute(_render(path.read_text()))
            await conn.execute(
                text("INSERT INTO schema_migrations (filename) VALUES (:f)"),
                {"f": path.name},
            )
        applied.append(path.name)
    return applied


async def run_migrations() -> list[str]:
    """Apply any unapplied .sql file; return the filenames applied this run.

    The whole run happens under a session-level `pg_advisory_lock`, which a second
    starting instance waits on: without it both instances read the same empty
    schema_migrations, both run 005, and the loser dies on the primary key.
    """
    await wait_for_db()
    async with engine.connect() as lock_conn:
        await lock_conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": ADVISORY_LOCK_KEY})
        try:
            applied = await _apply_pending()
        finally:
            # The lock is session-scoped, so closing the connection would release
            # it anyway; unlocking explicitly keeps that true if this connection
            # is ever pooled rather than closed.
            await lock_conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": ADVISORY_LOCK_KEY})
        # After the schema is settled, not before: on a brand new database
        # kb_chunks does not exist until 002 has run.
        await check_embedding_width(lock_conn)

    log.info("migrations up to date (%d applied this run)", len(applied))
    return applied


def down_path(name: str) -> Path:
    """The .down.sql file for a migration named either way round.

    `007_m19.sql`, `007_m19` and `007_m19.down.sql` all mean the same file, so an
    operator recovering at 2am can paste whichever name the log gave them.
    """
    stem = name[: -len(DOWN_SUFFIX)] if name.endswith(DOWN_SUFFIX) else name.removesuffix(".sql")
    return MIGRATIONS_DIR / f"{stem}{DOWN_SUFFIX}"


async def rollback(name: str) -> str:
    """Run one migration's .down.sql and delete its schema_migrations row.

    Both happen in a single transaction, so a down migration that fails halfway
    leaves the row in place and the schema untouched: the next `--rollback` is a
    retry, never a repair. Under the same advisory lock as the forward run so a
    rollback and a starting replica cannot interleave.
    """
    path = down_path(name)
    if not path.exists():
        available = ", ".join(sorted(p.name for p in MIGRATIONS_DIR.glob(f"*{DOWN_SUFFIX}"))) or "none"
        raise FileNotFoundError(f"no down migration at {path.name}. Available: {available}")
    forward = path.name[: -len(DOWN_SUFFIX)] + ".sql"

    await wait_for_db()
    async with engine.connect() as lock_conn:
        await lock_conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": ADVISORY_LOCK_KEY})
        try:
            async with engine.begin() as conn:
                log.info("rolling back %s with %s", forward, path.name)
                raw = await conn.get_raw_connection()
                await raw.driver_connection.execute(_render(path.read_text()))
                await conn.execute(
                    text("DELETE FROM schema_migrations WHERE filename = :f"),
                    {"f": forward},
                )
        finally:
            await lock_conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": ADVISORY_LOCK_KEY})
    log.info("rolled back %s", forward)
    return forward


def main() -> None:
    """`python -m app.db.migrations [--rollback <file>]` — forward by default."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Apply or roll back one SQL migration")
    parser.add_argument(
        "--rollback",
        metavar="FILENAME",
        help="run <name>.down.sql and forget the migration (e.g. 007_m19.sql)",
    )
    args = parser.parse_args()
    if args.rollback:
        print(f"rolled back {asyncio.run(rollback(args.rollback))}")
    else:
        applied = asyncio.run(run_migrations())
        print(f"applied {len(applied)}: {', '.join(applied) or 'nothing pending'}")


if __name__ == "__main__":
    main()
