"""The single async SQLAlchemy engine and the FastAPI session dependency.

Imported by everything that touches Postgres (migrations, seed loader, routers).
Depends on: app.config for DATABASE_URL (postgresql+asyncpg://...).
"""

import asyncio
import logging
import time
from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

log = logging.getLogger(__name__)

# Module constants rather than settings: M14 owns app/config.py this round, and
# these are operational floors nobody should need to tune per environment.
# CONNECT_TIMEOUT_S: outside docker compose (which has a depends_on healthcheck)
# Postgres may still be starting, and a crash-looping API container is a much
# worse failure than waiting.
CONNECT_TIMEOUT_S = 30
CONNECT_RETRY_S = 1.0
# statement_timeout: one runaway query used to be able to hold a pool connection
# for ever; 15 s is far above the slowest thing the app does (a hybrid retrieval).
STATEMENT_TIMEOUT_MS = 15000

# pool_pre_ping: the DB container may restart under the API during a demo.
# pool_size/max_overflow: every SSE stream holds a session for the whole turn,
# and the 5+10 default meant the 16th concurrent stream blocked on the pool.
# pool_recycle: drop connections before any proxy or Postgres idle timeout does.
engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=10,
    pool_recycle=1800,
    connect_args={"server_settings": {"statement_timeout": str(STATEMENT_TIMEOUT_MS)}},
)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def wait_for_db(timeout_s: float = CONNECT_TIMEOUT_S) -> None:
    """Block until `SELECT 1` succeeds, or raise the last error after timeout_s.

    Called by run_migrations(), which is the first thing the lifespan does, so
    every startup path gets the retry without app/main.py knowing about it.
    """
    deadline = time.monotonic() + timeout_s
    attempt = 0
    while True:
        attempt += 1
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            if attempt > 1:
                log.info("database reachable after %d attempts", attempt)
            return
        except Exception:  # noqa: BLE001 - asyncpg raises a family of errors here
            if time.monotonic() >= deadline:
                log.error("database still unreachable after %.0fs", timeout_s)
                raise
            if attempt == 1:
                log.info("waiting up to %.0fs for the database", timeout_s)
            await asyncio.sleep(CONNECT_RETRY_S)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request, always closed."""
    async with SessionLocal() as session:
        yield session
