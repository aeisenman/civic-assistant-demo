"""M26a: filing an application twice files one application.

Drives POST /api/applications with a fake session that holds an in-memory list of
rows, so the replay and the 60-second dedupe are exercised end to end with no
Postgres. Depends on: app.api.applications, app.main and starlette's TestClient.
"""

import re
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app import auth
from app.api import applications as applications_api
from app.db.engine import get_session
from app.main import app

SESSION = "abcd1234-efgh"
PAYLOAD = {"type": "service_request", "fields": {"category": "pothole"}, "session_id": SESSION}


class _App:
    """Just enough of models.Application for `_as_dict`."""

    _next = 1

    def __init__(self, fields, session_id, idempotency_key, created_at=None):
        self.id = _App._next
        self.tracking_number = f"SR-2026-{_App._next:06d}"
        _App._next += 1
        self.type = "service_request"
        self.status = "submitted"
        self.fields = fields
        self.missing_fields = []
        self.warnings = []
        self.department = None
        self.fee_cents = None
        self.resident_session_id = session_id
        self.document_id = None
        self.certificate_s3_key = None
        self.idempotency_key = idempotency_key
        self.created_at = created_at or datetime.now(UTC)
        self.updated_at = self.created_at


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _Rows(self._rows)

    def scalar_one(self):
        return False


class _Store:
    """An in-memory applications table that answers the route's three queries."""

    def __init__(self):
        self.rows: list[_App] = []

    async def execute(self, statement=None, *args, **kwargs):
        sql = str(statement)
        if "EXISTS" in sql.upper():
            return _Result([])  # first contact: no history for this session id
        # Order matters: `select(Application)` names every column, idempotency_key
        # included, so the dedupe query is recognised by its WHERE clause first.
        if "applications.created_at >=" in sql:
            cutoff = datetime.now(UTC) - timedelta(seconds=applications_api.DEDUPE_WINDOW_S)
            recent = [r for r in self.rows if r.created_at >= cutoff]
            return _Result(sorted(recent, key=lambda r: -r.id))
        if "WHERE applications.idempotency_key" in sql:
            key = _literal(statement, "idempotency_key")
            return _Result([r for r in self.rows if r.idempotency_key == key])
        return _Result([])

    async def rollback(self):
        return None


def _literal(statement, column: str) -> str | None:
    """The value a `where(col == value)` clause was built with.

    Compiled with literal binds and read back out of the SQL: the fake has no
    driver to hand the parameters to, and this keeps the assertion about what the
    route actually asked the database.
    """
    sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
    found = re.search(rf"{column} = '([^']*)'", sql)
    return found.group(1) if found else None


@pytest.fixture
def store():
    _App._next = 1
    return _Store()


@pytest.fixture
def client(store, monkeypatch):
    async def fake_submit(session, type_, fields, session_id, idempotency_key=None):
        row = _App(fields, session_id, idempotency_key)
        store.rows.append(row)
        return row

    async def _fake_session():
        yield store

    monkeypatch.setattr(applications_api.engine, "submit", fake_submit)
    app.dependency_overrides[get_session] = _fake_session
    app.dependency_overrides[auth.require_staff] = lambda: object()
    yield TestClient(app)
    app.dependency_overrides.clear()


def file(client, key=None, payload=None):
    headers = {"Idempotency-Key": key} if key else {}
    return client.post("/api/applications", json=payload or PAYLOAD, headers=headers)


# ---------------------------------------------------------------- with a key
def test_a_replay_with_the_same_key_returns_the_original_tracking_number(client, store):
    """Finding #7: 30 double-clicks used to be 30 applications to cancel."""
    first = file(client, key="idem-aaa")
    second = file(client, key="idem-aaa")
    assert first.status_code == second.status_code == 200
    assert first.json()["tracking_number"] == second.json()["tracking_number"]
    assert len(store.rows) == 1


def test_a_different_key_files_a_second_application(client, store):
    """A resident who genuinely files twice is not blocked by the first filing."""
    first = file(client, key="idem-aaa")
    second = file(client, key="idem-bbb")
    assert first.json()["tracking_number"] != second.json()["tracking_number"]
    assert len(store.rows) == 2


def test_the_key_is_bounded(client):
    assert file(client, key="x" * 129).status_code == 422
    assert file(client, key="x" * 128).status_code == 200


# ------------------------------------------------------------- without a key
def test_an_identical_payload_within_the_window_is_the_same_filing(client, store):
    first = file(client)
    second = file(client)
    assert first.json()["tracking_number"] == second.json()["tracking_number"]
    assert len(store.rows) == 1
    assert applications_api.DEDUPE_WINDOW_S == 60


def test_a_different_payload_within_the_window_is_a_new_filing(client, store):
    file(client)
    other = dict(PAYLOAD, fields={"category": "streetlight"})
    second = file(client, payload=other)
    assert second.status_code == 200
    assert len(store.rows) == 2


def test_an_identical_payload_after_the_window_is_a_new_filing(client, store):
    file(client)
    store.rows[0].created_at = datetime.now(UTC) - timedelta(seconds=applications_api.DEDUPE_WINDOW_S + 5)
    assert file(client).status_code == 200
    assert len(store.rows) == 2


def test_a_key_wins_over_the_window(client, store):
    """With a key the payload is irrelevant: the key is the caller's own promise."""
    first = file(client, key="idem-ccc")
    other = dict(PAYLOAD, fields={"category": "streetlight"})
    second = file(client, key="idem-ccc", payload=other)
    assert first.json()["tracking_number"] == second.json()["tracking_number"]
    assert len(store.rows) == 1
