"""M26a: the runtime fixes that are not the stream route — one test each.

Covers the Pacific-day cost breaker, boto3 timeouts and `to_thread`, the worker's
row claim, the retention sweep, the KB ingest lock and intake's re-raise of
infrastructure errors. Depends on: app.api.chat, app.storage.s3,
app.workflows.{engine,worker}, app.rag.ingest, app.agents.intake_turn — all with
fakes, no Postgres, no object store and no model.
"""

import logging
from datetime import date
from types import SimpleNamespace

import httpx
import pytest
from botocore.client import Config
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SATimeoutError

from app import clock
from app.agents import intake_turn
from app.api import chat as chat_api
from app.config import settings
from app.rag import ingest as ingest_mod
from app.storage import s3
from app.workflows import engine, worker


# ------------------------------------------------------- the daily cost breaker
class _Answer:
    def __init__(self, value):
        self._value = value

    def scalar_one(self):
        return self._value


class _SpendSession:
    """Turn count then day spend, and a record of the SQL the breaker ran."""

    def __init__(self, turns=0, spend=0.0):
        self.answers = [turns, spend]
        self.statements: list[str] = []

    async def execute(self, statement=None, *args, **kwargs):
        self.statements.append(str(statement))
        return _Answer(self.answers.pop(0))


def test_the_daily_cap_counts_the_pacific_day_not_the_utc_one():
    """Finding #5: the cap used to reset at 5 pm Pacific, and could not use the index."""
    sql = str(chat_api.DAILY_SPEND_SQL)
    assert "AT TIME ZONE 'America/Los_Angeles'" in sql
    assert "SUM(cost_usd)" in sql
    # The predicate is a range on the bare column, so traces_created_idx is usable.
    assert "date(created_at)" not in sql.lower()


async def test_the_breaker_still_trips_at_the_cap():
    session = _SpendSession(turns=0, spend=settings.daily_cost_cap_usd)
    with pytest.raises(Exception) as caught:
        await chat_api.enforce_limits(session, "abcd1234-efgh")
    assert caught.value.status_code == 429


async def test_the_eighty_percent_warning_fires_once_a_day(monkeypatch, caplog):
    """A line per turn would bury the one line an operator needs to see."""
    monkeypatch.setattr(chat_api, "_cap_warned_on", None)
    monkeypatch.setattr(clock, "today", lambda: date(2026, 9, 15))
    near = 0.85 * settings.daily_cost_cap_usd
    with caplog.at_level(logging.WARNING, logger="app.api.chat"):
        for _ in range(3):
            await chat_api.enforce_limits(_SpendSession(turns=0, spend=near), "abcd1234-efgh")
    warnings = [r for r in caplog.records if "% of the" in r.getMessage()]
    assert len(warnings) == 1
    assert "85%" in warnings[0].getMessage()


async def test_the_warning_fires_again_on_the_next_day(monkeypatch, caplog):
    monkeypatch.setattr(chat_api, "_cap_warned_on", None)
    near = 0.85 * settings.daily_cost_cap_usd
    with caplog.at_level(logging.WARNING, logger="app.api.chat"):
        for day in (date(2026, 9, 15), date(2026, 9, 16)):
            monkeypatch.setattr(clock, "today", lambda day=day: day)
            await chat_api.enforce_limits(_SpendSession(turns=0, spend=near), "abcd1234-efgh")
    assert len([r for r in caplog.records if "% of the" in r.getMessage()]) == 2


# --------------------------------------------------------- boto3 off the loop
def test_the_s3_client_has_timeouts_and_bounded_retries():
    """Finding #4: the defaults were 60s x 3, i.e. three minutes on one call."""
    assert (s3.CONNECT_TIMEOUT_S, s3.READ_TIMEOUT_S, s3.MAX_ATTEMPTS) == (3, 10, 2)
    s3.client.cache_clear()
    config = s3.client().meta.config
    assert isinstance(config, Config)
    assert config.connect_timeout == 3
    assert config.read_timeout == 10
    # botocore rewrites max_attempts into its own "total_max_attempts" (retries
    # plus the first try). The number that matters is that it is below the
    # legacy default of 5, so one wedged call cannot take minutes.
    assert config.retries["total_max_attempts"] == 3
    s3.client.cache_clear()


async def test_the_issued_hook_renders_the_certificate_in_a_thread(monkeypatch):
    """Finding #3: reportlab + a boto3 PUT ran on the loop, under a row lock."""
    handed_off: list = []

    async def fake_to_thread(fn, *args, **kwargs):
        handed_off.append(fn)
        return "certificates/PRM-2026-000400.pdf"

    monkeypatch.setattr(engine.asyncio, "to_thread", fake_to_thread)
    app = SimpleNamespace(
        type="permit",
        tracking_number="PRM-2026-000400",
        fields={},
        department="DSD",
        fee_cents=100,
    )
    values = await engine._prepare_issued(None, app)
    assert values == {"certificate_s3_key": "certificates/PRM-2026-000400.pdf"}
    assert handed_off == [engine.certificates.store_certificate]


async def test_a_failed_render_in_the_thread_is_still_a_hook_failure(monkeypatch):
    async def fake_to_thread(fn, *args, **kwargs):
        raise OSError("seaweedfs is down")

    monkeypatch.setattr(engine.asyncio, "to_thread", fake_to_thread)
    app = SimpleNamespace(
        type="permit", tracking_number="PRM-2026-000400", fields={}, department=None, fee_cents=None
    )
    with pytest.raises(engine.HookFailed):
        await engine._prepare_issued(None, app)


async def test_the_async_s3_wrappers_use_a_thread(monkeypatch):
    calls: list[str] = []

    async def fake_to_thread(fn, *args, **kwargs):
        calls.append(getattr(fn, "__name__", type(fn).__name__))
        return b"pdf"

    monkeypatch.setattr(s3.asyncio, "to_thread", fake_to_thread)
    assert await s3.aget_bytes("certificates/x.pdf") == b"pdf"
    await s3.aput_bytes("documents/1/x.pdf", b"x")
    await s3.ahead_bucket()
    assert calls[:2] == ["get_bytes", "put_bytes"]
    assert len(calls) == 3


# ------------------------------------------------------------- the worker claim
def test_the_worker_claims_a_row_with_for_update_skip_locked():
    """Two replicas must not both advance the same application."""
    sql = str(worker.CLAIM_SQL)
    assert "FOR UPDATE SKIP LOCKED" in sql
    assert "FROM applications" in sql


async def test_a_row_another_worker_already_holds_is_skipped(monkeypatch):
    """The claim comes back empty, so this worker does no work on that row."""

    class _NoClaim:
        async def execute(self, statement, params=None, *args, **kwargs):
            return SimpleNamespace(scalar_one_or_none=lambda: None)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    def must_not_run(*a, **k):  # pragma: no cover - the failure itself
        raise AssertionError("a row we did not claim must not be advanced")

    monkeypatch.setattr(worker, "SessionLocal", _NoClaim)
    monkeypatch.setattr(worker.engine, "run_auto", must_not_run)
    assert await worker._advance_one(7) is False


# ---------------------------------------------------------------- retention
async def test_retention_is_a_no_op_at_the_default(monkeypatch):
    """0 = keep everything, which is what the demo wants and the default is."""
    assert settings.trace_retention_days == 0

    def must_not_run():  # pragma: no cover - the failure itself
        raise AssertionError("the sweep must not open a session when it is off")

    monkeypatch.setattr(worker, "SessionLocal", must_not_run)
    monkeypatch.setattr(worker, "_swept_on", None)
    assert await worker.retention_sweep() == {}


async def test_the_sweep_deletes_both_tables_once_a_day(monkeypatch):
    statements: list[str] = []

    class _Sweep:
        async def execute(self, statement, params=None, *args, **kwargs):
            statements.append(str(statement))
            self.params = params
            return SimpleNamespace(rowcount=3)

        async def commit(self):
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(settings, "trace_retention_days", 90)
    monkeypatch.setattr(worker, "SessionLocal", _Sweep)
    monkeypatch.setattr(worker, "_swept_on", None)
    monkeypatch.setattr(clock, "today", lambda: date(2026, 9, 15))

    deleted = await worker.retention_sweep()
    assert deleted == {"chat_messages": 3, "traces": 3}
    assert any("DELETE FROM chat_messages" in s for s in statements)
    assert any("DELETE FROM traces" in s for s in statements)
    assert all("make_interval(days => :days)" in s for s in statements)

    # Second call on the same City day does nothing.
    assert await worker.retention_sweep() == {}
    assert len(statements) == 2


# ------------------------------------------------------------- the ingest lock
async def test_ingest_runs_under_an_advisory_lock(monkeypatch):
    """Finding #2: two replicas booting at once ingested the KB twice."""
    statements: list[str] = []

    class _LockConn:
        async def execute(self, statement, params=None, *args, **kwargs):
            statements.append((str(statement), params))
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    async def fake_locked(*, force=False):
        # The lock is taken before any work and released after it.
        assert statements and "pg_advisory_lock" in statements[0][0]
        return {"trash.md": 4}

    monkeypatch.setattr(ingest_mod, "engine", SimpleNamespace(connect=_LockConn))
    monkeypatch.setattr(ingest_mod, "_ingest_locked", fake_locked)

    assert await ingest_mod.ingest_kb() == {"trash.md": 4}
    assert "pg_advisory_lock" in statements[0][0]
    assert "pg_advisory_unlock" in statements[1][0]
    assert statements[0][1] == statements[1][1] == {"k": ingest_mod.INGEST_LOCK_KEY}
    # A different key from the migration lock, so the two never wait on each other.
    from app.db.migrations import ADVISORY_LOCK_KEY

    assert ingest_mod.INGEST_LOCK_KEY != ADVISORY_LOCK_KEY


async def test_the_lock_is_released_even_when_ingest_fails(monkeypatch):
    statements: list[str] = []

    class _LockConn:
        async def execute(self, statement, params=None, *args, **kwargs):
            statements.append(str(statement))
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    async def boom(*, force=False):
        raise RuntimeError("embedding endpoint is down")

    monkeypatch.setattr(ingest_mod, "engine", SimpleNamespace(connect=_LockConn))
    monkeypatch.setattr(ingest_mod, "_ingest_locked", boom)
    with pytest.raises(RuntimeError):
        await ingest_mod.ingest_kb()
    assert "pg_advisory_unlock" in statements[-1]


# --------------------------------------------------- intake: what is re-raised
@pytest.mark.parametrize(
    "error",
    [
        OperationalError("SELECT 1", {}, Exception("server closed the connection")),
        SATimeoutError("QueuePool limit of size 10 overflow 10 reached"),
        TimeoutError(),  # asyncio.TimeoutError is the builtin since 3.11
        httpx.ConnectError("connection refused"),
        httpx.ReadTimeout("gateway did not answer"),
    ],
    ids=["operational", "pool-timeout", "asyncio-timeout", "connect", "read-timeout"],
)
async def test_an_infrastructure_failure_is_re_raised_not_templated(monkeypatch, error):
    """Finding #13: a resident was told their filing failed when it never ran."""

    async def explode(session, session_id, document_ids):
        raise error

    monkeypatch.setattr(intake_turn, "_handle_documents", explode)
    with pytest.raises(type(error)):
        await intake_turn.handle_intake_turn(None, "abcd1234-efgh", "hi", [1])


async def test_an_extraction_failure_still_gets_the_templated_reply(monkeypatch):
    """The templated reply is a statement about the document, so it stays here."""

    async def explode(session, session_id, document_ids):
        raise ValueError("the extractor returned no fields")

    monkeypatch.setattr(intake_turn, "_handle_documents", explode)
    payload = await intake_turn.handle_intake_turn(None, "abcd1234-efgh", "hi", [1])
    assert payload["actions"] == []
    assert payload["trace"]["error"].startswith("ValueError")
    assert payload["trace"]["reason"] == "intake failed"


async def test_a_validation_failure_still_gets_the_templated_reply(monkeypatch):
    async def explode(session, session_id, document_ids):
        raise KeyError("address")

    monkeypatch.setattr(intake_turn, "_handle_documents", explode)
    payload = await intake_turn.handle_intake_turn(None, "abcd1234-efgh", "hi", [1])
    assert payload["trace"]["error"].startswith("KeyError")
