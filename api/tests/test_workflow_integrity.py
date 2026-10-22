"""The M15 concurrency and data-integrity guarantees, with a simulated database.

The suite has no real Postgres fixture, so `FakeDatabase` below models the two
things the guarantees rest on: a row lock that a second caller waits on, and an
UPDATE whose WHERE clause carries the expected status and reports how many rows
it changed. Everything else (nextval, ON CONFLICT DO NOTHING, pg_advisory_lock)
is asserted at the level of "the statement the code sends", and the end-to-end
proof is the reviewer restarting the live stack after merge.
"""

import asyncio
import itertools
from types import SimpleNamespace

import pytest
from sqlalchemy import Insert, Select, Update
from sqlalchemy.exc import IntegrityError

from app.agents import intake_turn
from app.workflows import engine, store, worker


# ------------------------------------------------------------------ fake database
class FakeDatabase:
    """One applications row, its event rows, and a row lock."""

    def __init__(self, status: str, *, locking: bool = True):
        self.status = status
        self.certificate_s3_key: str | None = None
        self.events: list[dict] = []
        self.locking = locking
        self.lock = asyncio.Lock()


class _Result:
    """The two bits of a SQLAlchemy Result the engine actually uses."""

    def __init__(self, value=None, rowcount: int = 1):
        self._value = value
        self.rowcount = rowcount

    def scalar_one_or_none(self):
        return self._value

    def scalar_one(self):
        return self._value


class LockingSession:
    """Session over a FakeDatabase: SELECT ... FOR UPDATE really does block.

    With locking=False the lock is a no-op, which is how the `rowcount == 0`
    branch is exercised: both callers read the old status and the conditional
    UPDATE is the only thing standing between them.
    """

    def __init__(self, db: FakeDatabase):
        self.db = db
        self.holds_lock = False

    async def execute(self, statement, *args, **kwargs):
        if isinstance(statement, Select):
            if self.db.locking:
                await self.db.lock.acquire()
                self.holds_lock = True
                return _Result(self.db.status)
            # No lock: both callers read the same stale status, which is exactly
            # the condition the rowcount guard exists for.
            stale = self.db.status
            await asyncio.sleep(0)
            return _Result(stale)
        if isinstance(statement, Update):
            params = statement.compile().params
            expected = params.get("status_1")
            if expected is not None and expected != self.db.status:
                return _Result(rowcount=0)
            if "status" in params:
                self.db.status = params["status"]
            if params.get("certificate_s3_key"):
                self.db.certificate_s3_key = params["certificate_s3_key"]
            return _Result(rowcount=1)
        if isinstance(statement, Insert):
            self.db.events.append(statement.compile().params)
            return _Result()
        return _Result()

    def _release(self):
        if self.holds_lock:
            self.db.lock.release()
            self.holds_lock = False

    async def commit(self):
        self._release()

    async def rollback(self):
        self._release()

    async def refresh(self, obj):
        obj.status = self.db.status
        obj.certificate_s3_key = self.db.certificate_s3_key


def make_app(status: str, **kwargs) -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        tracking_number="PRM-2026-000400",
        type="permit",
        status=status,
        fields={},
        department="Development Services Department",
        fee_cents=12300,
        certificate_s3_key=None,
        **kwargs,
    )


# ------------------------------------------------------------------ A12 concurrency
async def test_two_concurrent_advances_write_one_event_and_one_invalid_transition(monkeypatch):
    """A12: the loser waits on the row lock, re-reads, and refuses."""
    monkeypatch.setattr(engine, "BEFORE_COMMIT", {})
    monkeypatch.setattr(engine, "ON_ENTER", {})
    db = FakeDatabase("approved")

    async def caller():
        session = LockingSession(db)
        return await engine.advance(session, make_app("approved"), "issued", "staff")

    results = await asyncio.gather(caller(), caller(), return_exceptions=True)

    failures = [r for r in results if isinstance(r, engine.InvalidTransition)]
    assert len(failures) == 1, results
    assert "now 'issued'" in str(failures[0])
    assert db.status == "issued"
    assert len(db.events) == 1  # exactly one application_events row


async def test_the_conditional_update_alone_stops_the_second_advance(monkeypatch):
    """The same race with the lock disabled: rowcount == 0 is the second guard."""
    monkeypatch.setattr(engine, "BEFORE_COMMIT", {})
    monkeypatch.setattr(engine, "ON_ENTER", {})
    db = FakeDatabase("in_review", locking=False)
    sessions = [LockingSession(db), LockingSession(db)]
    apps = [make_app("in_review"), make_app("in_review")]

    results = await asyncio.gather(
        *(engine.advance(s, a, "approved", "staff") for s, a in zip(sessions, apps, strict=True)),
        return_exceptions=True,
    )
    failures = [r for r in results if isinstance(r, engine.InvalidTransition)]
    assert len(failures) == 1
    assert "lost a concurrent transition" in str(failures[0])
    assert len(db.events) == 1


# ------------------------------------------------------------------ A16 illegal jump
async def test_an_illegal_transition_raises_before_any_write(monkeypatch):
    """A16: issued -> submitted never reaches the database (the API answers 409)."""
    monkeypatch.setattr(engine, "BEFORE_COMMIT", {})
    db = FakeDatabase("issued")
    session = LockingSession(db)
    with pytest.raises(engine.InvalidTransition):
        await engine.advance(session, make_app("issued"), "submitted", "staff")
    assert db.events == []
    assert db.status == "issued"


def test_the_api_turns_an_illegal_transition_into_a_409():
    """The same refusal, seen the way a staff member sees it."""
    from fastapi.testclient import TestClient

    from app import auth
    from app.api import applications as applications_api
    from app.db.engine import get_session
    from app.main import app as fastapi_app

    row = make_app("issued")

    async def _fake_find(session, id_or_tracking):
        return row

    async def _fake_session():
        yield object()

    fastapi_app.dependency_overrides[get_session] = _fake_session
    fastapi_app.dependency_overrides[auth.require_staff] = lambda: SimpleNamespace(username="dispatcher")
    original_find = applications_api._find
    applications_api._find = _fake_find
    try:
        client = TestClient(fastapi_app)
        response = client.post("/api/applications/PRM-2026-000400/advance", json={"to": "submitted"})
    finally:
        applications_api._find = original_find
        fastapi_app.dependency_overrides.clear()

    assert response.status_code == 409
    assert "cannot go from 'issued' to 'submitted'" in response.json()["detail"]


# ------------------------------------------------------------------ issued hook
async def test_the_certificate_is_stored_before_the_status_commits(monkeypatch):
    """The key is set in the same UPDATE as the status, not a later one."""
    monkeypatch.setattr(engine, "ON_ENTER", {})
    monkeypatch.setattr(engine.certificates, "store_certificate", lambda *a, **k: "certificates/x.pdf")
    db = FakeDatabase("approved")
    session = LockingSession(db)
    await engine.advance(session, make_app("approved"), "issued", "staff")
    assert db.status == "issued"
    assert db.certificate_s3_key == "certificates/x.pdf"


async def test_a_storage_failure_leaves_the_application_approved(monkeypatch):
    """Object storage down: HookFailed (a 503), no status change, no event row."""
    monkeypatch.setattr(engine, "ON_ENTER", {})

    def boom(*args, **kwargs):
        raise OSError("seaweedfs is down")

    monkeypatch.setattr(engine.certificates, "store_certificate", boom)
    db = FakeDatabase("approved")
    session = LockingSession(db)
    with pytest.raises(engine.HookFailed) as caught:
        await engine.advance(session, make_app("approved"), "issued", "staff")
    assert "still approved" in str(caught.value)
    assert db.status == "approved"
    assert db.events == []
    assert db.certificate_s3_key is None


# ------------------------------------------------------------------ worker sweep
async def test_the_worker_backfills_a_certificate_for_a_stranded_issued_row(monkeypatch):
    """Rows issued before the pre-commit hook existed heal on the next tick."""
    monkeypatch.setattr(engine.certificates, "store_certificate", lambda *a, **k: "certificates/old.pdf")
    db = FakeDatabase("issued")
    session = LockingSession(db)
    stranded = make_app("issued")

    key = await engine.backfill_certificate(session, stranded)
    assert key == "certificates/old.pdf"
    assert db.certificate_s3_key == "certificates/old.pdf"

    # Idempotent: a row that already has a key is left alone.
    assert await engine.backfill_certificate(session, stranded) is None


async def test_the_worker_tick_runs_the_recovery_sweep(monkeypatch):
    """tick() sweeps `issued AND certificate_s3_key IS NULL` after the auto steps."""
    swept: list[str] = []

    class _Scalars:
        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return self._rows

    class _SweepSession:
        """Two sessions, in order: the AUTO id listing, then the stranded sweep.

        Since M26a `tick()` opens one session to list candidate ids (it iterates
        the result directly, one tuple per row) and another for the certificate
        sweep, which still goes through `.scalars().all()`.
        """

        def __init__(self, call: int):
            self.call = call

        async def execute(self, statement, *args, **kwargs):
            if self.call == 1:
                return iter([])  # no application is on an automatic status
            return SimpleNamespace(scalars=lambda: _Scalars([make_app("issued")]))

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    async def fake_backfill(session, app):
        swept.append(app.tracking_number)
        return "certificates/old.pdf"

    opened = itertools.count(1)
    monkeypatch.setattr(worker, "SessionLocal", lambda: _SweepSession(next(opened)))
    monkeypatch.setattr(worker.engine, "backfill_certificate", fake_backfill)

    healed = await worker.tick()
    assert swept == ["PRM-2026-000400"]
    assert healed == 1


# ------------------------------------------------------------------ A13 tracking numbers
class _SequenceSession:
    """A session whose nextval() is a real, shared counter."""

    def __init__(self, start: int = 400, fail_first_insert: bool = False):
        self.counter = start - 1
        self.issued: list[int] = []
        self.fail_first_insert = fail_first_insert
        self.inserts = 0
        self.rollbacks = 0
        self.last_sql = ""
        self.fetched = None

    async def execute(self, statement, *args, **kwargs):
        text_sql = str(statement)
        if "nextval" in text_sql:
            self.last_sql = text_sql
            # asyncio.sleep(0) so the two coroutines really interleave here.
            await asyncio.sleep(0)
            self.counter += 1
            self.issued.append(self.counter)
            return _Result(self.counter)
        if isinstance(statement, Insert):
            self.inserts += 1
            if self.fail_first_insert and self.inserts == 1:
                raise IntegrityError("insert", {}, Exception("duplicate key"))
            return _Result(7)
        if isinstance(statement, Select):
            # The read-back at the end of create_application.
            return SimpleNamespace(scalars=lambda: SimpleNamespace(one=lambda: self.fetched))
        return _Result()

    async def commit(self):
        pass

    async def rollback(self):
        self.rollbacks += 1


async def test_two_concurrent_creates_get_distinct_tracking_numbers():
    """A13: nextval is atomic, so the two callers cannot collide."""
    session = _SequenceSession()
    numbers = await asyncio.gather(
        store.next_tracking_number(session, "permit"),
        store.next_tracking_number(session, "permit"),
    )
    assert len(set(numbers)) == 2
    assert sorted(numbers) == ["PRM-2026-000400", "PRM-2026-000401"]


async def test_the_tracking_number_uses_this_years_date(monkeypatch):
    """The year is read from the City's clock, not the old hard-coded YEAR = 2026."""
    from datetime import date

    monkeypatch.setattr(store.clock, "today", lambda: date(2027, 1, 1))
    assert await store.next_tracking_number(_SequenceSession(), "business_tax") == ("BTC-2027-000400")


async def test_each_type_draws_from_its_own_sequence():
    """One sequence per type, named exactly as 006_sequences.sql creates them."""
    assert set(store.SEQUENCES) == set(store.PREFIXES)
    for app_type, prefix in (
        ("permit", "PRM"),
        ("business_tax", "BTC"),
        ("service_request", "SR"),
        ("stro", "STR"),
    ):
        session = _SequenceSession()
        number = await store.next_tracking_number(session, app_type)
        assert number.startswith(f"{prefix}-")
        assert store.SEQUENCES[app_type] in session.last_sql


async def test_an_integrity_error_is_retried_once():
    """A number already taken by hand-seeded data costs a retry, not a 500."""
    session = _SequenceSession(fail_first_insert=True)
    session.fetched = make_app("submitted")
    app = await store.create_application(session, "permit", {}, None)
    assert app.status == "submitted"
    assert session.rollbacks == 1
    assert session.issued == [400, 401]  # the collided number is not reused, a new one is drawn


def test_the_migration_creates_exactly_the_sequences_the_code_draws_from():
    """A rename in one place and not the other would only show up at runtime."""
    import pathlib

    # 006 created the first three; a new application type adds its own file
    # (M24's 008_stro.sql), so read whichever migrations mention a sequence.
    migrations = pathlib.Path(__file__).resolve().parents[1] / "app" / "db" / "migrations"
    sql = "\n".join(
        p.read_text() for p in sorted(migrations.glob("*.sql")) if "CREATE SEQUENCE" in p.read_text()
    )
    for name in store.SEQUENCES.values():
        assert f"CREATE SEQUENCE IF NOT EXISTS {name};" in sql
        assert f"setval(\n    '{name}'" in sql
    # setval above the highest existing number, so seeded fixtures are never reused.
    assert sql.count("GREATEST(") == len(store.SEQUENCES)


def test_the_migration_run_is_serialised_by_an_advisory_lock():
    """Two API instances starting together must not both apply the same file."""
    import inspect

    from app.db import migrations

    source = inspect.getsource(migrations.run_migrations)
    assert "pg_advisory_lock" in source
    assert "pg_advisory_unlock" in source
    assert isinstance(migrations.ADVISORY_LOCK_KEY, int)


# ------------------------------------------------------------------ seed loader
async def test_the_seed_loader_refuses_to_truncate_a_resident_table():
    from app.db import models
    from app.seed import loader

    assert "applications" in loader.NEVER_TRUNCATE
    assert "application_events" in loader.NEVER_TRUNCATE
    assert {"documents", "chat_messages", "traces"} <= loader.NEVER_TRUNCATE
    assert not any(m.__table__.name in loader.NEVER_TRUNCATE for m in loader.FILES.values())

    with pytest.raises(ValueError, match="resident data"):
        await loader._load_file(object(), loader.SEED_DIR / "x.json", models.Application)


async def test_the_seed_loader_leaves_an_existing_application_alone(tmp_path):
    """A row a resident (or a reviewer) already has keeps its status on restart."""
    import json

    from app.seed import loader

    path = tmp_path / "sample_applications.json"
    path.write_text(
        json.dumps(
            [
                {"tracking_number": "PRM-2026-000101", "type": "permit", "status": "rejected"},
                {"tracking_number": "PRM-2026-000999", "type": "permit", "status": "submitted"},
            ]
        )
    )

    inserted_rows: list[dict] = []

    class _Session:
        async def execute(self, statement, *args, **kwargs):
            if isinstance(statement, Select):
                # PRM-2026-000101 is already on the table.
                return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: ["PRM-2026-000101"]))
            inserted_rows.append(statement.compile().params)
            return _Result()

    added = await loader._upsert_applications(_Session(), path)
    assert added == 1
    assert [r["tracking_number"] for r in inserted_rows] == ["PRM-2026-000999"]


# ------------------------------------------------------------------ intake failure
async def test_a_failed_intake_says_so_instead_of_answering_something_else(monkeypatch):
    """The blanket except now owes the resident a reply, not a fall-through."""

    async def boom(*args, **kwargs):
        raise RuntimeError("object storage is down")

    monkeypatch.setattr(intake_turn, "_handle_documents", boom)
    payload = await intake_turn.handle_intake_turn(object(), "session-abc", "here it is", [7])

    assert payload is not None
    assert "could not file that document" in payload["reply"]
    assert payload["actions"] == []
    assert payload["trace"]["error"].startswith("RuntimeError")
    assert payload["trace"]["reason"] == "intake failed"


async def test_a_turn_that_is_not_intake_still_falls_through(monkeypatch):
    """None (fall through to Q&A) is still the answer when nothing was being filed."""

    async def no_pending(session, session_id, status):
        return None

    monkeypatch.setattr(intake_turn.engine, "latest_for_session", no_pending)
    assert await intake_turn.handle_intake_turn(object(), "s-1", "when is trash day?", []) is None
