"""40 concurrent SSE turns against the CI stub model: the regression test for #1.

Marked `load` and deselected by `pytest -q` (see pyproject `addopts`); run it with
`uv run pytest -q -m load`. It starts `scripts/ci/stub_openai.py` on a free port
and finds a Postgres itself (see DB_CANDIDATES), so on a developer's machine with
the demo stack up it runs rather than skips. Depends on: app.main (in-process, via
httpx's ASGITransport), app.config, app.db and the stub — no real model, no money.

What it asserts is the shape of the cliff the reviewer found: before the fix, 20
concurrent streams pinned the whole pool (10 + 10) in yield-dependencies and
every request sat for 60 s before answering with the apology; 30 got an HTTP 500
out of `QueuePool limit ... reached`. Now the semaphore sheds at
MAX_CONCURRENT_STREAMS with a 429 and nothing waits on the pool.

Every 200 must be a complete turn: a `done` frame whose trace carries no
error. The first heartbeat wrapper drove the generator from a task per step and
reset the trace ContextVar from another context, so every stream ended in the
fallback reply; that is what the `error` field below catches (fixed 2026-09-15).
"""

import asyncio
import os
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.load

REPO = Path(__file__).resolve().parents[2]
STUB = REPO / "scripts" / "ci" / "stub_openai.py"

CONCURRENCY = 40
#: The reviewer's bar: no 500s, every stream finishes, p95 under two seconds.
P95_CEILING_S = 2.0

#: Where to look for a Postgres, in order. The default in app/config.py is the
#: compose hostname `db`, which resolves only inside the compose network — so on
#: the author's machine this test used to skip with "no Postgres on DATABASE_URL"
#: even under `-m load`, which is a green run that measured nothing. The same
#: server is published on loopback (docker-compose.yml binds 127.0.0.1:5433), and
#: CI sets DATABASE_URL properly, so trying both covers every way it is run.
#: LOAD_TEST_DATABASE_URL wins when it is set, for a server neither guess finds.
DB_CANDIDATES = ("postgresql+asyncpg://civic:civic@127.0.0.1:5433/civic",)

#: The 40 turns write chat_messages and traces rows. They go into a scratch
#: database of their own rather than the demo's, so a load run never shows up in
#: the staff dashboard's turn counts and never competes with a live demo for the
#: pool. It is created if missing and then reused; nothing is ever dropped.
SCRATCH_DB = "civic_load"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module")
def stub() -> str:
    """The stub model server, on its own port, for the life of this module."""
    if not STUB.exists():  # pragma: no cover - the stub lands with M26b
        pytest.skip(f"no stub model server at {STUB}")
    port = free_port()
    process = subprocess.Popen(
        [sys.executable, str(STUB), "--host", "127.0.0.1", "--port", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}/v1"
    try:
        for _ in range(100):
            try:
                if httpx.get(f"{base}/models", timeout=0.5).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.05)
        else:  # pragma: no cover - the stub failed to start
            pytest.skip("the stub model server did not come up")
        yield base
    finally:
        process.terminate()
        process.wait(timeout=5)


def with_database(url: str, name: str) -> str:
    """The same server, a different database name."""
    parts = urlsplit(url)
    return urlunsplit(parts._replace(path=f"/{name}"))


async def _answers(url: str) -> bool:
    """`SELECT 1` on its own engine, disposed either way.

    Its own engine matters: this runs on a throwaway event loop, and a pooled
    asyncpg connection left behind belongs to a loop that is gone — the first
    real request would then fail with "attached to a different loop".
    """
    probe = create_async_engine(url, pool_pre_ping=True)
    try:
        async with probe.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001 - any failure means "no database here"
        return False
    finally:
        await probe.dispose()


async def _ensure_scratch(admin_url: str) -> None:
    """CREATE DATABASE civic_load if it is not there yet. Never drops it.

    CREATE DATABASE cannot run inside a transaction, hence AUTOCOMMIT. The
    maintenance database is `postgres`, which the compose image always has.
    """
    admin = create_async_engine(with_database(admin_url, "postgres"), pool_pre_ping=True)
    try:
        async with admin.connect() as conn:
            conn = await conn.execution_options(isolation_level="AUTOCOMMIT")
            exists = (
                await conn.execute(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": SCRATCH_DB})
            ).scalar_one_or_none()
            if exists is None:
                await conn.execute(text(f'CREATE DATABASE "{SCRATCH_DB}"'))
    finally:
        await admin.dispose()


def resolve_scratch_url() -> str | None:
    """A reachable, migrated scratch database, or None if no Postgres answers."""
    override = os.environ.get("LOAD_TEST_DATABASE_URL")
    if override:
        return override

    from app.config import settings

    for candidate in (settings.database_url, *DB_CANDIDATES):
        if not asyncio.run(_answers(candidate)):
            continue
        asyncio.run(_ensure_scratch(candidate))
        return with_database(candidate, SCRATCH_DB)
    return None


@pytest.fixture(scope="module")
def app_under_load(stub):
    """The real app, pointed at the stub and at a scratch database.

    Configured before app.main is imported so the module-level Settings object
    picks it up; the lifespan is never run, so no seed and no ingest — the
    migrations are run here instead, because a scratch database starts empty.

    The engine is rebuilt rather than reconfigured: app/db/engine.py builds it at
    import time from settings.database_url, and several modules bound the names
    `engine` and `SessionLocal` into their own namespace with `from ... import`,
    so each of those bindings is patched too. Undone in the teardown.
    """
    os.environ.update(
        {
            "LLM_BASE_URL": stub,
            "EMBED_BASE_URL": stub,
            "LLM_PRICES_JSON": "{}",
            "SEED_ON_STARTUP": "false",
            "INGEST_KB_ON_STARTUP": "false",
            "WORKER_ENABLED": "false",
            "RATE_LIMIT_ENABLED": "false",
        }
    )
    from app.config import get_settings, settings

    get_settings.cache_clear()
    settings.llm_base_url = stub
    settings.embed_base_url = stub
    settings.llm_prices_json = {}

    scratch = resolve_scratch_url()
    if scratch is None:
        pytest.skip(
            "no Postgres answered on DATABASE_URL, 127.0.0.1:5433, or "
            "LOAD_TEST_DATABASE_URL; the load test needs a real pool"
        )

    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.api import chat as chat_api
    from app.api import health as health_api
    from app.db import engine as engine_module
    from app.db import migrations

    # The same pool shape the app ships with (app/db/engine.py): the 10 + 10 is
    # half of what the test is measuring, so it must not be a test-only number.
    loaded = create_async_engine(
        scratch,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=10,
        pool_recycle=1800,
        connect_args={"server_settings": {"statement_timeout": str(engine_module.STATEMENT_TIMEOUT_MS)}},
    )
    sessions = async_sessionmaker(loaded, expire_on_commit=False, class_=engine_module.AsyncSession)

    patch = pytest.MonkeyPatch()
    patch.setattr(settings, "database_url", scratch)
    patch.setattr(engine_module, "engine", loaded)
    patch.setattr(engine_module, "SessionLocal", sessions)
    patch.setattr(migrations, "engine", loaded)
    patch.setattr(chat_api, "SessionLocal", sessions)
    patch.setattr(health_api, "SessionLocal", sessions)

    asyncio.run(migrations.run_migrations())
    asyncio.run(loaded.dispose())

    from app.main import app

    try:
        yield app
    finally:
        asyncio.run(loaded.dispose())
        patch.undo()


async def one_stream(client: httpx.AsyncClient, run: str, index: int) -> dict:
    """One resident turn. Returns status, wall time, and whether it ended in `done`.

    A fresh session id per run, because a resident session belongs to the first
    browser that used it (M20): reusing `load-00001` from a previous run is a 403,
    not a load result.
    """
    started = time.perf_counter()
    body = {"session_id": f"load-{run}-{index:04d}", "message": "hello"}
    try:
        async with client.stream("POST", "/api/chat/stream", json=body) as response:
            status = response.status_code
            text = ""
            if status == 200:
                async for chunk in response.aiter_text():
                    text += chunk
    except Exception as exc:  # noqa: BLE001 - a transport failure is a result too
        return {"status": -1, "seconds": time.perf_counter() - started, "done": False, "error": repr(exc)}
    return {
        "status": status,
        "seconds": time.perf_counter() - started,
        "done": '"type": "done"' in text,
        # A done frame whose trace carries an error is a turn that produced its
        # tokens and then failed at the end; the heartbeat wrapper's first
        # version did exactly that (ContextVar reset from another task).
        "error": "trace error in done" if ('"type": "done"' in text and '"error": "' in text) else None,
    }


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(fraction * (len(ordered) - 1))))]


async def test_forty_concurrent_streams_shed_load_instead_of_deadlocking(app_under_load):
    run = uuid.uuid4().hex[:8]
    transport = httpx.ASGITransport(app=app_under_load)
    async with httpx.AsyncClient(transport=transport, base_url="http://load.test", timeout=60.0) as client:
        wall = time.perf_counter()
        results = await asyncio.gather(*(one_stream(client, run, i) for i in range(CONCURRENCY)))
        wall = time.perf_counter() - wall

    statuses = [r["status"] for r in results]
    seconds = [r["seconds"] for r in results]
    ok = [r for r in results if r["status"] == 200]
    busy = [r for r in results if r["status"] == 429]
    print(
        f"\n{CONCURRENCY} concurrent streams in {wall:.2f}s: "
        f"{len(ok)}x200 {len(busy)}x429 "
        f"p50={percentile(seconds, 0.50):.3f}s p95={percentile(seconds, 0.95):.3f}s "
        f"max={max(seconds):.3f}s"
    )

    assert 500 not in statuses, [r for r in results if r["status"] >= 500]
    assert -1 not in statuses, [r for r in results if r["status"] == -1]
    # Every stream is either a finished turn or honest backpressure.
    assert set(statuses) <= {200, 429}
    assert all(r["done"] for r in ok), "a 200 must end in a `done` event"
    assert not [r for r in ok if r["error"]], "a done frame must not carry a trace error"
    assert len(ok) + len(busy) == CONCURRENCY
    assert percentile(seconds, 0.95) < P95_CEILING_S, f"p95 {percentile(seconds, 0.95):.2f}s"
