"""M26a: the SSE route holds no pool connection, sheds load, and keeps alive.

Drives /api/chat/stream with starlette's TestClient over a fake session, the same
mock pattern as test_api_bounds. Depends on: app.api.chat, app.main and
fastapi.dependency.utils for the dependant inspection — no Postgres, no model.
"""

import asyncio

import pytest
from fastapi.testclient import TestClient

from app import auth
from app.api import chat as chat_api
from app.db.engine import get_session
from app.main import app

GOOD_SESSION = "abcd1234-efgh"


class _Answer:
    def __init__(self, value):
        self._value = value

    def scalar_one(self):
        return self._value


class _Session:
    """The resident-session EXISTS, then the turn count, then the day's spend."""

    async def execute(self, statement=None, *args, **kwargs):
        if "EXISTS" in str(statement).upper():
            return _Answer(False)
        return _Answer(0)


class _SessionCM:
    async def __aenter__(self):
        return _Session()

    async def __aexit__(self, *exc):
        return False


@pytest.fixture
def client(monkeypatch):
    """No `with`: running the lifespan would mean migrations, S3 and a seed."""

    async def _fake_session():
        yield _Session()

    monkeypatch.setattr(chat_api, "SessionLocal", _SessionCM)
    app.dependency_overrides[get_session] = _fake_session
    app.dependency_overrides[auth.require_staff] = lambda: object()
    yield TestClient(app)
    app.dependency_overrides.clear()


def post(client, message="hi"):
    return client.post("/api/chat/stream", json={"session_id": GOOD_SESSION, "message": message})


def _routes(router):
    """Every leaf route, flattening the wrappers `include_router` builds.

    Recent FastAPI wraps an included router in `_IncludedRouter`, which keeps the
    real one on `.original_router` and has no `.routes` of its own.
    """
    for route in getattr(router, "routes", []):
        if hasattr(route, "dependant"):
            yield route
        elif hasattr(route, "original_router"):
            yield from _routes(route.original_router)
        else:
            yield from _routes(route)


def _dependency_calls(path: str) -> set:
    """Every callable in one route's dependency tree, sub-dependencies included."""
    route = next(r for r in _routes(app) if getattr(r, "path", "") == path)

    def walk(dependant):
        yield dependant
        for sub in dependant.dependencies:
            yield from walk(sub)

    return {d.call for d in walk(route.dependant)}


# ------------------------------------------------------- no pool connection held
def test_the_stream_route_does_not_depend_on_get_session():
    """Finding #1: a yield-dependency is not released until the body has drained.

    Taking `Depends(get_session)` therefore pinned one pool connection for the
    whole stream and the generator asked for a second — a hard deadlock at
    pool_size + max_overflow = 20 concurrent streams. This asserts the shape of
    the fix rather than the fix's effect, because the effect needs 20 real
    connections to see.
    """
    assert get_session not in _dependency_calls("/api/chat/stream")
    # The buffered route still takes it: it is a request, not a stream.
    assert get_session in _dependency_calls("/api/chat")


# ------------------------------------------------------------------ backpressure
def test_a_full_semaphore_is_a_429_before_any_body(client, monkeypatch):
    """Finding #2: the cap used to be taken *after* the 200 and the headers."""
    started = []

    async def must_not_run(session, session_id, message, document_ids):
        started.append(message)
        yield {"type": "done", "reply": "ok", "citations": [], "actions": [], "trace": {}}

    monkeypatch.setattr(chat_api, "stream_chat", must_not_run)
    # Drain every slot, as a fleet of concurrent residents would.
    taken = 0
    while chat_api.take_stream_slot():
        taken += 1
    try:
        response = post(client)
        assert response.status_code == 429
        assert response.json()["detail"] == chat_api.BUSY
        assert response.headers["Retry-After"] == "2"
        assert started == [], "the turn must be refused before the orchestrator"
    finally:
        for _ in range(taken):
            chat_api._stream_slots.release()


def test_a_finished_stream_gives_its_slot_back(client, monkeypatch):
    async def one_event(session, session_id, message, document_ids):
        yield {"type": "done", "reply": "ok", "citations": [], "actions": [], "trace": {}}

    monkeypatch.setattr(chat_api, "stream_chat", one_event)
    before = chat_api._stream_slots._value
    response = post(client)
    assert response.status_code == 200
    assert "done" in response.text
    assert chat_api._stream_slots._value == before


def test_a_failed_stream_gives_its_slot_back_too(client, monkeypatch):
    async def explode(session, session_id, message, document_ids):
        raise RuntimeError("gateway fell over")
        yield  # pragma: no cover - makes this an async generator

    monkeypatch.setattr(chat_api, "stream_chat", explode)
    before = chat_api._stream_slots._value
    response = post(client)
    assert response.status_code == 200
    # The reply is JSON-escaped on the wire, so match the trace rather than the text.
    assert '"RuntimeError: gateway fell over"' in response.text
    assert '"type": "done"' in response.text
    assert chat_api._stream_slots._value == before


def test_a_refused_stream_does_not_leak_a_slot(client, monkeypatch):
    """A 422 happens before the slot is taken, so nothing has to give one back."""

    async def never(session, session_id, message, document_ids):  # pragma: no cover
        yield {}

    monkeypatch.setattr(chat_api, "stream_chat", never)
    before = chat_api._stream_slots._value
    assert post(client, message="   ").status_code == 422
    assert chat_api._stream_slots._value == before


# --------------------------------------------------------------------- heartbeat
def test_a_stalled_model_produces_a_heartbeat_comment(client, monkeypatch):
    """Finding #17: a silent SSE connection is dropped by an ALB at 60 s."""
    monkeypatch.setattr(chat_api, "HEARTBEAT_INTERVAL_S", 0.01)

    async def stalls(session, session_id, message, document_ids):
        await asyncio.sleep(0.05)
        yield {"type": "done", "reply": "ok", "citations": [], "actions": [], "trace": {}}

    monkeypatch.setattr(chat_api, "stream_chat", stalls)
    body = post(client).text
    assert ": heartbeat" in body
    # The turn still arrives, after the keep-alives.
    assert body.rstrip().endswith("}")
    assert '"type": "done"' in body


async def test_the_heartbeat_wrapper_passes_events_through_untouched():
    """No stall, no comment — a fast turn is byte-for-byte what it was."""

    async def two_events():
        yield {"type": "token", "text": "a"}
        yield {"type": "done", "reply": "a", "citations": [], "actions": [], "trace": {}}

    frames = [f async for f in chat_api._with_heartbeat(two_events(), 60.0)]
    assert len(frames) == 2
    assert all(f.startswith("data: ") for f in frames)


async def test_the_heartbeat_wrapper_does_not_cancel_the_turn_underneath_it():
    """The pending __anext__ is shielded: the event survives the timeout."""

    async def slow():
        await asyncio.sleep(0.03)
        yield {"type": "done", "reply": "late", "citations": [], "actions": [], "trace": {}}

    frames = [f async for f in chat_api._with_heartbeat(slow(), 0.005)]
    assert chat_api.HEARTBEAT in frames
    assert any("late" in f for f in frames)


async def test_the_heartbeat_wrapper_keeps_the_turn_in_one_context():
    """A generator that sets and resets a ContextVar must see its own token.

    Driving the generator step by step from separate tasks put each step in a
    different context, and `ContextVar.reset(token)` raised ValueError at the
    end of every real turn. The wrapper must run the whole generator in one task.
    """
    import contextvars

    var: contextvars.ContextVar[int] = contextvars.ContextVar("probe", default=0)

    async def turn():
        token = var.set(1)
        yield {"type": "token", "text": "a"}
        await asyncio.sleep(0)
        yield {"type": "token", "text": "b"}
        var.reset(token)  # raises ValueError if this runs in another context
        yield {"type": "done", "reply": "ab"}

    frames = [f async for f in chat_api._with_heartbeat(turn(), 60.0)]
    assert len(frames) == 3
    assert '"done"' in frames[-1]


async def test_the_heartbeat_wrapper_raises_the_turns_error_in_the_consumer():
    async def turn():
        yield {"type": "token", "text": "a"}
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        _ = [f async for f in chat_api._with_heartbeat(turn(), 60.0)]
