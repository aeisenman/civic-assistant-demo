"""Every M14 bound on the HTTP surface, proved with no model and no Postgres.

Drives the FastAPI app with starlette's TestClient over a fake session that
answers only the two aggregates `enforce_limits` runs. Depends on: app.main,
app.api.chat, app.api.documents, app.api.health, app.db.engine.get_session.
"""

import io
import json

import pytest
from fastapi.testclient import TestClient

from app import auth
from app.api import chat as chat_api
from app.api import documents as documents_api
from app.api import health as health_api
from app.config import settings
from app.db.engine import get_session
from app.main import REQUEST_ID_HEADER, app

GOOD_SESSION = "abcd1234-efgh"  # 13 chars, inside ^[A-Za-z0-9_-]{8,64}$


class _Answer:
    """What `session.execute(...)` returns: one scalar the caller asked for."""

    def __init__(self, value):
        self._value = value

    def scalar_one(self):
        return self._value


class _SessionCM:
    """`SessionLocal()` for the stream route, which opens its own session in M26a.

    The route dropped `Depends(get_session)` because a yield-dependency is not
    released until a StreamingResponse has finished draining, so every stream
    pinned a pool connection for its whole life and deadlocked the pool at 20.
    """

    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *exc):
        return False


class _LimitSession:
    """Answers enforce_limits' two queries in order: turn count, then day spend.

    M20 added one more query ahead of them — the resident-session EXISTS, which
    every request without a valid cookie runs. It is answered by shape rather
    than by position so the ordered `answers` list in each test still reads as
    the two numbers that test is about.
    """

    def __init__(self, turns: int = 0, spend: float = 0.0, has_history: bool = False):
        self.answers = [turns, spend]
        self.has_history = has_history

    async def execute(self, statement=None, *args, **kwargs):
        if "EXISTS" in str(statement).upper():
            return _Answer(self.has_history)
        assert self.answers, "enforce_limits asked more questions than it should"
        return _Answer(self.answers.pop(0))


@pytest.fixture
def db():
    """The session every request in this module gets; tests set its answers."""
    return _LimitSession()


@pytest.fixture
def client(db, monkeypatch):
    """No `with` on purpose: that would run the lifespan (migrations, S3, seed)."""

    async def _fake_session():
        yield db

    monkeypatch.setattr(chat_api, "SessionLocal", lambda: _SessionCM(db))
    app.dependency_overrides[get_session] = _fake_session
    app.dependency_overrides[auth.require_staff] = lambda: object()
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def no_turn(monkeypatch):
    """Replace the orchestrator, so a request that passes the guards is free."""
    seen: list[dict] = []

    async def fake_handle_chat(session, session_id, message, document_ids):
        seen.append({"session_id": session_id, "message": message, "document_ids": document_ids})
        return chat_api.ChatResponse(reply="ok", citations=[], actions=[], trace={"id": 7})

    monkeypatch.setattr(chat_api, "handle_chat", fake_handle_chat)
    return seen


# --------------------------------------------------------------- message length
def test_a_message_over_the_cap_is_a_422_and_never_reaches_a_model(client, no_turn):
    body = {"session_id": GOOD_SESSION, "message": "x" * (settings.max_message_chars + 1)}
    assert client.post("/api/chat", json=body).status_code == 422
    assert no_turn == [], "the turn must be refused before the orchestrator"


def test_a_one_megabyte_message_is_a_422(client, no_turn):
    body = {"session_id": GOOD_SESSION, "message": "a" * 1_048_576}
    assert client.post("/api/chat", json=body).status_code == 422


def test_a_message_at_the_cap_is_accepted(client, no_turn):
    body = {"session_id": GOOD_SESSION, "message": "x" * settings.max_message_chars}
    assert client.post("/api/chat", json=body).status_code == 200


# ------------------------------------------------------------ session_id shape
@pytest.mark.parametrize(
    "session_id",
    [
        "s",  # too short
        "x" * 5000,  # A3: 5,000 chars
        "abcd1234\nefgh",  # A3: a newline, which would split a log line
        "../etc/passwd",  # A3: made to look like a path
        "abcd 1234",  # a space
        "abcd1234;drop",  # punctuation
    ],
)
def test_a_session_id_outside_the_pattern_is_a_422(client, no_turn, session_id):
    response = client.post("/api/chat", json={"session_id": session_id, "message": "hi"})
    assert response.status_code == 422
    assert no_turn == []


def test_a_browser_uuid_session_id_is_accepted(client, no_turn):
    """crypto.randomUUID() is what web/lib/session.ts actually mints."""
    body = {"session_id": "3f8c1e5a-2b47-4d9e-9f21-7c0b6a4d1e83", "message": "hi"}
    assert client.post("/api/chat", json=body).status_code == 200


# --------------------------------------------------------------- document_ids
def test_more_than_five_document_ids_is_a_422(client, no_turn):
    body = {"session_id": GOOD_SESSION, "message": "hi", "document_ids": list(range(50))}
    assert client.post("/api/chat", json=body).status_code == 422
    assert no_turn == []


def test_repeated_document_ids_are_deduped_before_the_turn(client, no_turn):
    """[7,7,7] used to be three detect calls and three extract calls."""
    body = {"session_id": GOOD_SESSION, "message": "hi", "document_ids": [7, 7, 7, 9, 7]}
    assert client.post("/api/chat", json=body).status_code == 200
    assert no_turn[0]["document_ids"] == [7, 9]


# ------------------------------------------------------------ per-session cap
def test_a_session_over_the_turn_cap_is_a_429(client, db, no_turn):
    db.answers = [settings.max_turns_per_session, 0.0]
    response = client.post("/api/chat", json={"session_id": GOOD_SESSION, "message": "hi"})
    assert response.status_code == 429
    assert str(settings.max_turns_per_session) in response.json()["detail"]
    assert no_turn == []


def test_a_session_one_turn_under_the_cap_still_answers(client, db, no_turn):
    db.answers = [settings.max_turns_per_session - 1, 0.0]
    assert client.post("/api/chat", json={"session_id": GOOD_SESSION, "message": "hi"}).status_code == 200


# ------------------------------------------------------------- daily cost cap
def test_the_daily_cost_breaker_returns_a_429_before_any_model_call(client, db, no_turn):
    db.answers = [0, settings.daily_cost_cap_usd]
    response = client.post("/api/chat", json={"session_id": GOOD_SESSION, "message": "hi"})
    assert response.status_code == 429
    assert "daily usage limit" in response.json()["detail"]
    assert no_turn == [], "the breaker must trip before classify()"


def test_spend_under_the_cap_lets_the_turn_through(client, db, no_turn):
    db.answers = [0, settings.daily_cost_cap_usd - 0.01]
    assert client.post("/api/chat", json={"session_id": GOOD_SESSION, "message": "hi"}).status_code == 200


def test_the_stream_endpoint_enforces_the_same_guards(client, db, no_turn):
    db.answers = [0, settings.daily_cost_cap_usd]
    response = client.post("/api/chat/stream", json={"session_id": GOOD_SESSION, "message": "hi"})
    assert response.status_code == 429


# -------------------------------------------------------------- stream slots
def test_the_stream_semaphore_is_sized_from_config():
    assert chat_api._stream_slots._value == settings.max_concurrent_streams


async def test_a_stream_holds_one_slot_and_gives_it_back():
    before = chat_api._stream_slots._value
    async with chat_api.stream_slot():
        assert chat_api._stream_slots._value == before - 1
    assert chat_api._stream_slots._value == before


def test_a_hung_model_still_ends_the_stream_with_one_done_event(client, monkeypatch):
    """A11: the SDK raises once LLM_TIMEOUT_S is up; the client must not be left open."""
    import httpx
    from openai import APITimeoutError

    async def times_out(session, session_id, message, document_ids):
        raise APITimeoutError(request=httpx.Request("POST", "http://gateway/v1/chat/completions"))
        yield  # pragma: no cover - makes this an async generator

    monkeypatch.setattr(chat_api, "stream_chat", times_out)
    response = client.post("/api/chat/stream", json={"session_id": GOOD_SESSION, "message": "hi"})
    assert response.status_code == 200
    events = [
        json.loads(line[len("data: ") :]) for line in response.text.splitlines() if line.startswith("data: ")
    ]
    assert [e["type"] for e in events] == ["done"]
    assert events[0]["reply"] == chat_api.FALLBACK_REPLY
    assert "APITimeoutError" in events[0]["trace"]["error"]


# ------------------------------------------------------------------- uploads
@pytest.mark.parametrize(
    "content_type",
    ["application/x-msdownload", "image/png", "application/zip", "", "application/octet-stream"],
)
def test_a_content_type_outside_the_allow_list_is_a_415(client, content_type):
    response = client.post(
        "/api/documents",
        files={"file": ("x.pdf", io.BytesIO(b"%PDF-1.4"), content_type)},
    )
    assert response.status_code == 415
    assert "Upload a PDF" in response.json()["detail"]


@pytest.mark.parametrize("content_type", ["application/pdf", "text/plain", "text/markdown"])
def test_the_allow_list_accepts_the_three_types_intake_can_read(content_type):
    assert documents_api.base_content_type(f"{content_type}; charset=utf-8") == content_type
    assert content_type in documents_api.ALLOWED_CONTENT_TYPES


def test_an_oversized_upload_is_refused_on_its_declared_size_before_any_read(client, monkeypatch):
    """The 413 used to cost one full copy of the body in memory first."""

    async def must_not_read(*args, **kwargs):  # pragma: no cover - the failure itself
        raise AssertionError("the body was read despite a declared size over the limit")

    monkeypatch.setattr(documents_api, "read_bounded", must_not_read)
    data = b"x" * (documents_api.MAX_UPLOAD_BYTES + 1)
    response = client.post("/api/documents", files={"file": ("big.pdf", io.BytesIO(data), "application/pdf")})
    assert response.status_code == 413
    assert "limit" in response.json()["detail"]


async def test_the_streaming_read_stops_as_soon_as_the_running_total_is_over():
    """A body with no declared size still cannot spend more than the limit + a chunk."""

    class _Endless:
        """An upload that would never stop giving, one chunk at a time."""

        size = None
        content_type = "application/pdf"
        filename = "endless.pdf"

        def __init__(self):
            self.reads = 0

        async def read(self, n: int = -1) -> bytes:
            self.reads += 1
            return b"y" * documents_api.UPLOAD_CHUNK_BYTES

    endless = _Endless()
    with pytest.raises(Exception) as caught:
        await documents_api.read_bounded(endless, "endless.pdf")
    assert caught.value.status_code == 413
    ceiling = documents_api.MAX_UPLOAD_BYTES // documents_api.UPLOAD_CHUNK_BYTES + 1
    assert endless.reads <= ceiling


# -------------------------------------------------------------------- /health
def _s3_says(status: str):
    """A stand-in for health._check_s3, which is a coroutine since M26a."""

    async def check() -> str:
        return status

    return check


@pytest.fixture
def healthy(monkeypatch):
    """db and s3 green, and the model probes wired to explode if touched."""

    async def db_ok():
        return "ok", 42

    async def must_not_run():  # pragma: no cover - the failure itself
        raise AssertionError("/health must not make a model call")

    monkeypatch.setattr(health_api, "_check_db", db_ok)
    monkeypatch.setattr(health_api, "_check_s3", _s3_says("ok"))
    monkeypatch.setattr(health_api, "_check_llm", must_not_run)
    monkeypatch.setattr(health_api, "_check_embed", must_not_run)
    health_api.clear_startup_errors()
    health_api.clear_deep_cache()
    yield monkeypatch
    health_api.clear_startup_errors()
    health_api.clear_deep_cache()


def test_health_is_green_and_makes_zero_model_calls(client, healthy):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert (body["db"], body["s3"], body["kb_chunks"]) == ("ok", "ok", 42)
    # The probes are gone from the free endpoint, not merely reported as error.
    assert "llm" not in body and "embed" not in body


def test_health_reports_a_half_ingested_knowledge_base_honestly(client, healthy, monkeypatch):
    """Probe A20: 60 of 120 chunks must read as 60, not be rounded up to "fine"."""

    async def half_ingested():
        return "ok", 60

    monkeypatch.setattr(health_api, "_check_db", half_ingested)
    assert client.get("/health").json()["kb_chunks"] == 60


def test_health_is_a_503_when_the_database_is_down(client, healthy, monkeypatch):
    async def db_down():
        return "error", None

    monkeypatch.setattr(health_api, "_check_db", db_down)
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json()["status"] == "degraded"


def test_health_is_a_503_when_s3_is_down(client, healthy, monkeypatch):
    monkeypatch.setattr(health_api, "_check_s3", _s3_says("error"))
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json()["status"] == "degraded"


def test_a_failed_startup_step_shows_in_health_without_stopping_the_app(client, healthy):
    health_api.record_startup_error("kb_ingest", RuntimeError("embeddings refused"))
    response = client.get("/health")
    assert response.status_code == 503
    assert "embeddings refused" in response.json()["startup_errors"]["kb_ingest"]


# --------------------------------------------------------------- /health/deep
def test_health_deep_needs_a_staff_session(db, healthy):
    """No require_staff override here: an anonymous caller must not pay for a probe.

    With no cookie, resolve_session short-circuits before any query, so the
    overridden session is never touched — the 401 costs nothing either.
    """

    async def _fake_session():
        yield db

    app.dependency_overrides[get_session] = _fake_session
    try:
        assert TestClient(app).get("/health/deep").status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_health_deep_probes_the_model_and_then_serves_a_cached_answer(client, healthy, monkeypatch):
    calls = {"llm": 0, "embed": 0}

    async def llm_ok():
        calls["llm"] += 1
        return "ok"

    async def embed_ok():
        calls["embed"] += 1
        return "ok"

    monkeypatch.setattr(health_api, "_check_llm", llm_ok)
    monkeypatch.setattr(health_api, "_check_embed", embed_ok)

    first = client.get("/health/deep").json()
    assert (first["status"], first["llm"], first["cached"]) == ("ok", "ok", False)
    second = client.get("/health/deep").json()
    assert second["cached"] is True
    assert calls == {"llm": 1, "embed": 1}, "the probe costs tokens; once a minute is enough"


# ------------------------------------------------------------- certificates
def test_a_certificate_whose_object_is_gone_is_a_404_not_a_500(monkeypatch):
    """A15: SeaweedFS lost the object, or the key is stale. Either way, not a 500."""
    from app.api import applications as applications_api
    from app.db import models

    issued = models.Application(
        id=1,
        tracking_number="PRM-2026-000104",
        type="permit",
        status="issued",
        certificate_s3_key="certificates/1/PRM-2026-000104.pdf",
    )

    class _Rows:
        def scalars(self):
            return self

        def first(self):
            return issued

    class _OneApplication:
        async def execute(self, *args, **kwargs):
            return _Rows()

    async def _fake_session():
        yield _OneApplication()

    def missing(key):
        raise KeyError("NoSuchKey")

    monkeypatch.setattr(applications_api.s3, "get_bytes", missing)
    app.dependency_overrides[get_session] = _fake_session
    app.dependency_overrides[auth.require_staff] = lambda: object()
    try:
        response = TestClient(app).get("/api/applications/1/certificate")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert "could not be read" in response.json()["detail"]


# ------------------------------------------------------------- request id
def test_every_response_carries_a_request_id(client, healthy):
    assert client.get("/health").headers[REQUEST_ID_HEADER]
    # Including a rejected one, which is the case a reporter is most likely to hit.
    rejected = client.post("/api/chat", json={"session_id": "s", "message": "hi"})
    assert rejected.status_code == 422
    assert rejected.headers[REQUEST_ID_HEADER]


def test_a_sane_incoming_request_id_is_echoed_back(client, healthy):
    response = client.get("/health", headers={REQUEST_ID_HEADER: "abc123"})
    assert response.headers[REQUEST_ID_HEADER] == "abc123"


def test_a_hostile_incoming_request_id_is_replaced(client, healthy):
    """It ends up in a log line, so a newline or 5 KB of it is not accepted."""
    response = client.get("/health", headers={REQUEST_ID_HEADER: "x" * 500})
    assert response.headers[REQUEST_ID_HEADER] != "x" * 500
    assert len(response.headers[REQUEST_ID_HEADER]) == 32
