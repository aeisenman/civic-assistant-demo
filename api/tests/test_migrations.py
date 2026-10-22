"""The migration runner's two M26b guarantees: vector width, and --rollback.

Run by `uv run pytest`. Depends on: app.db.migrations only — there is no
Postgres in the suite, so `FakeEngine` below records the statements the runner
sends and hands back canned results, the same shape test_workflow_integrity.py
uses. The end-to-end proof is compose-smoke, which runs the real thing twice at
two different EMBED_DIMs.
"""

import pytest

from app.config import settings
from app.db import migrations


# ------------------------------------------------------------- fake database
class _Result:
    """The one bit of a SQLAlchemy Result these code paths use."""

    def __init__(self, value=None):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class FakeRaw:
    """`conn.get_raw_connection()` -> something with a driver_connection."""

    def __init__(self, recorder: list[str]):
        self.driver_connection = self

    async def execute(self, sql: str) -> None:
        RECORDED_SQL.append(sql)


RECORDED_SQL: list[str] = []


class FakeConn:
    """Records every statement; answers the width query with `width_reply`."""

    def __init__(self, calls: list, width_reply=None):
        self.calls = calls
        self.width_reply = width_reply

    async def execute(self, statement, params=None):
        self.calls.append((str(statement), params))
        if "format_type" in str(statement):
            return _Result(self.width_reply)
        return _Result()

    async def get_raw_connection(self):
        return FakeRaw(RECORDED_SQL)


class _Ctx:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *exc):
        return False


class FakeEngine:
    def __init__(self, conn):
        self.conn = conn

    def connect(self):
        return _Ctx(self.conn)

    def begin(self):
        return _Ctx(self.conn)


@pytest.fixture
def fake_db(monkeypatch):
    """Swap the real engine out and give the test the recorded call list."""
    calls: list = []
    RECORDED_SQL.clear()

    def _install(width_reply=None):
        conn = FakeConn(calls, width_reply)
        monkeypatch.setattr(migrations, "engine", FakeEngine(conn))

        async def _noop():
            return None

        monkeypatch.setattr(migrations, "wait_for_db", _noop)
        return calls

    return _install


# --------------------------------------------------------------- vector width
def test_declared_width_parses_the_type_modifier():
    assert migrations.declared_width("vector(1024)") == 1024
    assert migrations.declared_width("vector") is None
    assert migrations.declared_width(None) is None


@pytest.mark.asyncio
async def test_matching_width_passes(fake_db, monkeypatch):
    monkeypatch.setattr(settings, "embed_dim", 768)
    calls = fake_db("vector(768)")
    assert await migrations.check_embedding_width(_conn_from(calls)) == 768


@pytest.mark.asyncio
async def test_mismatched_width_names_reset_demo(fake_db, monkeypatch):
    """Finding 10: a 768-wide database and a 1024-wide model used to fail silently."""
    monkeypatch.setattr(settings, "embed_dim", 1024)
    calls = fake_db("vector(768)")
    with pytest.raises(RuntimeError) as exc:
        await migrations.check_embedding_width(_conn_from(calls))
    message = str(exc.value)
    assert "vector(768)" in message
    assert "EMBED_DIM=1024" in message
    assert "scripts/reset_demo.sh" in message


@pytest.mark.asyncio
async def test_missing_column_is_a_warning_not_a_crash(fake_db, monkeypatch):
    """A failed 002 is the error worth reporting; this check must not mask it."""
    monkeypatch.setattr(settings, "embed_dim", 768)
    calls = fake_db(None)
    assert await migrations.check_embedding_width(_conn_from(calls)) is None


@pytest.mark.asyncio
async def test_run_migrations_checks_the_width(fake_db, monkeypatch):
    monkeypatch.setattr(settings, "embed_dim", 768)
    calls = fake_db("vector(768)")

    async def _nothing_pending():
        return []

    monkeypatch.setattr(migrations, "_apply_pending", _nothing_pending)
    await migrations.run_migrations()
    assert any("format_type" in sql for sql, _ in calls)


# ------------------------------------------------------------------- rollback
def test_forward_migrations_exclude_down_files():
    """A .down.sql applied as a migration would undo the one above it."""
    names = [p.name for p in migrations.forward_migrations()]
    assert names == sorted(names)
    assert not any(n.endswith(".down.sql") for n in names)
    assert "006_sequences.sql" in names


def test_down_path_accepts_every_spelling_of_the_name():
    wanted = migrations.MIGRATIONS_DIR / "007_m19.down.sql"
    assert migrations.down_path("007_m19.sql") == wanted
    assert migrations.down_path("007_m19") == wanted
    assert migrations.down_path("007_m19.down.sql") == wanted


def test_every_migration_from_006_has_a_down_file():
    """From 006 on, every forward migration ships its own rollback.

    001-005 predate the --rollback flag and between them build the schema from
    nothing, so a down migration for those would only ever mean "drop the
    database" — the honest rollback there is scripts/restore.sh. 006 is where the
    line was drawn, and this test is what stops the next migration forgetting.
    """
    missing = [
        path.name
        for path in migrations.forward_migrations()
        if path.name >= "006" and not migrations.down_path(path.name).exists()
    ]
    assert missing == [], f"no down migration for {missing}"
    # The guard against the test passing because the glob found nothing.
    assert len([p for p in migrations.forward_migrations() if p.name >= "006"]) >= 5


@pytest.mark.asyncio
async def test_rollback_runs_the_down_sql_and_forgets_the_row(fake_db):
    calls = fake_db("vector(768)")
    assert await migrations.rollback("007_m19.sql") == "007_m19.sql"
    # The down file's own SQL went to the raw driver connection...
    assert any("DROP COLUMN IF EXISTS filename" in sql for sql in RECORDED_SQL)
    # ...and the tracking row was deleted in the same transaction, by the
    # forward filename, which is what schema_migrations stores.
    deletes = [(sql, params) for sql, params in calls if "DELETE FROM schema_migrations" in sql]
    assert deletes and deletes[0][1] == {"f": "007_m19.sql"}
    assert any("pg_advisory_lock" in sql for sql, _ in calls)
    assert any("pg_advisory_unlock" in sql for sql, _ in calls)


@pytest.mark.asyncio
async def test_rollback_of_a_migration_with_no_down_file_is_a_clear_error(fake_db):
    fake_db("vector(768)")
    with pytest.raises(FileNotFoundError) as exc:
        await migrations.rollback("001_init.sql")
    assert "001_init.down.sql" in str(exc.value)
    assert "007_m19.down.sql" in str(exc.value)  # names what *is* available


def _conn_from(calls: list):
    """The FakeConn the engine fixture installed, reached through the engine."""
    return migrations.engine.conn
