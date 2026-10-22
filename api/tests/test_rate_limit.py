"""M26a: the per-IP token bucket — the maths, the 429, and the off switch.

Tests app.rate_limit directly and through one route, with the RETURNING row
mocked so there is no Postgres. Depends on: app.rate_limit, app.config and
starlette's TestClient. conftest sets RATE_LIMIT_ENABLED=false for the rest of
the suite; every test here turns it back on for itself.
"""

import pytest
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient

from app import auth, rate_limit
from app.api import chat as chat_api
from app.config import settings
from app.db.engine import get_session
from app.main import app

GOOD_SESSION = "abcd1234-efgh"


class _Answer:
    def __init__(self, value):
        self._value = value

    def scalar_one(self):
        return self._value


class _BucketSession:
    """One statement, one row back: whatever the test says the bucket now holds."""

    def __init__(self, tokens: float):
        self.tokens = tokens
        self.statements: list[str] = []
        self.committed = False

    async def execute(self, statement, params=None, *args, **kwargs):
        self.statements.append(str(statement))
        self.params = params
        return _Answer(self.tokens)

    async def commit(self):
        self.committed = True

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _request(host: str = "203.0.113.7") -> Request:
    """The minimum ASGI scope `client_key` reads."""
    return Request({"type": "http", "client": (host, 1234), "headers": [], "path": "/api/chat"})


@pytest.fixture
def limit_on(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    return settings


# --------------------------------------------------------------- bucket maths
async def test_a_bucket_with_tokens_left_allows_the_request(monkeypatch):
    session = _BucketSession(tokens=12.0)
    monkeypatch.setattr(rate_limit, "SessionLocal", lambda: session)
    allowed, left = await rate_limit.take_token("ip:1.2.3.4")
    assert allowed is True
    assert left == 12.0
    assert session.committed


async def test_an_empty_bucket_refuses(monkeypatch):
    """The floor is -1, and -1 is what "you just asked with nothing left" means."""
    session = _BucketSession(tokens=-1.0)
    monkeypatch.setattr(rate_limit, "SessionLocal", lambda: session)
    allowed, left = await rate_limit.take_token("ip:1.2.3.4")
    assert allowed is False
    assert left == -1.0


async def test_the_statement_refills_by_elapsed_time_and_caps_at_the_burst(monkeypatch):
    session = _BucketSession(tokens=5.0)
    monkeypatch.setattr(rate_limit, "SessionLocal", lambda: session)
    await rate_limit.take_token("ip:1.2.3.4")
    sql = session.statements[0]
    # One statement, atomic: insert-or-update with the arithmetic inside Postgres.
    assert "INSERT INTO rate_limits" in sql
    assert "ON CONFLICT (key) DO UPDATE" in sql
    assert "RETURNING tokens" in sql
    assert "EXTRACT(EPOCH FROM (now() - rate_limits.updated_at))" in sql
    assert "LEAST(" in sql and "GREATEST(" in sql
    assert session.params["capacity"] == float(settings.rate_limit_burst)
    assert session.params["refill_per_second"] == settings.rate_limit_per_minute / 60.0


def test_the_defaults_are_a_burst_of_twenty_and_thirty_a_minute():
    assert settings.rate_limit_burst == 20
    assert settings.rate_limit_per_minute == 30.0


def test_retry_after_is_whole_seconds_and_never_zero():
    # 30/minute is one token every two seconds; from -1 that is two tokens away.
    assert rate_limit.retry_after_seconds(-1.0) == 4
    assert rate_limit.retry_after_seconds(0.9) == 1


# ------------------------------------------------------------------ the key
def test_the_key_is_the_client_ip_uvicorn_resolved():
    """`--proxy-headers` already rewrote request.client from X-Forwarded-For.

    Reading the header here instead would let any caller choose their own bucket
    by sending one, which is a rate limiter that limits nobody.
    """
    assert rate_limit.client_key(_request("198.51.100.4")) == "ip:198.51.100.4"


def test_a_client_less_request_still_gets_a_key():
    scope = {"type": "http", "headers": [], "path": "/api/chat"}
    assert rate_limit.client_key(Request(scope)) == "ip:unknown"


# ------------------------------------------------------------ the dependency
async def test_the_dependency_raises_a_429_with_a_retry_after(monkeypatch, limit_on):
    monkeypatch.setattr(rate_limit, "SessionLocal", lambda: _BucketSession(tokens=-1.0))
    with pytest.raises(HTTPException) as caught:
        await rate_limit.rate_limit(_request())
    assert caught.value.status_code == 429
    assert caught.value.detail == rate_limit.TOO_MANY
    assert int(caught.value.headers["Retry-After"]) >= 1


async def test_the_dependency_is_a_no_op_when_disabled(monkeypatch):
    """conftest turns it off for the suite; this proves "off" means no query."""
    monkeypatch.setattr(settings, "rate_limit_enabled", False)

    def must_not_run():  # pragma: no cover - the failure itself
        raise AssertionError("a disabled limiter must not touch the database")

    monkeypatch.setattr(rate_limit, "SessionLocal", must_not_run)
    assert await rate_limit.rate_limit(_request()) is None


async def test_a_broken_limiter_lets_the_request_through(monkeypatch, limit_on):
    """A dead rate-limit table must not become a closed front door."""

    def boom():
        raise OSError("database unreachable")

    monkeypatch.setattr(rate_limit, "SessionLocal", boom)
    assert await rate_limit.rate_limit(_request()) is None


# ------------------------------------------------------------- through a route
class _Session:
    async def execute(self, statement=None, *args, **kwargs):
        if "EXISTS" in str(statement).upper():
            return _Answer(False)
        return _Answer(0)


class _SessionCM:
    async def __aenter__(self):
        return _Session()

    async def __aexit__(self, *exc):
        return False


def test_a_throttled_chat_turn_is_a_429_and_never_reaches_the_model(monkeypatch, limit_on):
    seen: list[str] = []

    async def fake_handle_chat(session, session_id, message, document_ids):  # pragma: no cover
        seen.append(message)
        return chat_api.ChatResponse(reply="ok", citations=[], actions=[], trace={"id": 1})

    async def _fake_session():
        yield _Session()

    monkeypatch.setattr(chat_api, "handle_chat", fake_handle_chat)
    monkeypatch.setattr(chat_api, "SessionLocal", _SessionCM)
    monkeypatch.setattr(rate_limit, "SessionLocal", lambda: _BucketSession(tokens=-1.0))
    app.dependency_overrides[get_session] = _fake_session
    app.dependency_overrides[auth.require_staff] = lambda: object()
    try:
        client = TestClient(app)
        response = client.post("/api/chat", json={"session_id": GOOD_SESSION, "message": "hi"})
        assert response.status_code == 429
        assert response.json()["detail"] == rate_limit.TOO_MANY
        assert response.headers["Retry-After"]
        assert seen == []
    finally:
        app.dependency_overrides.clear()
