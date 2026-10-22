"""M20: a session id belongs to the browser that first used it.

Drives the four resident routes with starlette's TestClient over a fake session
that answers the first-contact EXISTS and the two cost aggregates, so there is
no Postgres and no model. Depends on: app.main, app.resident_session,
app.api.chat, app.api.documents, evals.run (the cookie-jar factory).
"""

import io

import httpx
import pytest
from fastapi.testclient import TestClient

from app import auth, resident_session
from app.api import chat as chat_api
from app.api import documents as documents_api
from app.db.engine import get_session
from app.main import app
from evals import run as eval_run

SESSION = "abcd1234-efgh"
OTHER = "zzzz9999-yyyy"


class _Rows:
    """An empty `.scalars()` result — nothing was filed a moment ago."""

    def all(self):
        return []

    def first(self):
        return None


class _Answer:
    """What `session.execute(...)` returns: the one scalar the caller asked for."""

    def __init__(self, value):
        self._value = value

    def scalar_one(self):
        return self._value

    def scalars(self):
        return _Rows()


class _Session:
    """Answers the resident-session EXISTS, then enforce_limits' two aggregates."""

    def __init__(self, has_history: bool = False):
        self.has_history = has_history
        self.limits = [0, 0.0]

    async def execute(self, statement=None, *args, **kwargs):
        sql = str(statement)
        if "EXISTS" in sql.upper():
            return _Answer(self.has_history)
        # M26a: the inline form looks for an idempotent replay before it files.
        if "applications" in sql.lower():
            return _Answer(None)
        return _Answer(self.limits.pop(0))

    async def rollback(self):
        return None


class _SessionCM:
    """`SessionLocal()`: the stream route opens its own session now, not a Depends."""

    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *exc):
        return False


@pytest.fixture
def db():
    """Fresh, with no history: every test that needs history flips the flag."""
    return _Session()


@pytest.fixture
def client(db, monkeypatch):
    """No `with` on purpose: that would run the lifespan (migrations, S3, seed)."""

    async def _fake_session():
        yield db

    async def fake_handle_chat(session, session_id, message, document_ids):
        return chat_api.ChatResponse(reply="ok", citations=[], actions=[], trace={"id": 1})

    async def fake_stream_chat(session, session_id, message, document_ids):
        yield {"type": "token", "text": "ok"}
        yield {"type": "done", "reply": "ok", "citations": [], "actions": [], "trace": {}}

    async def fake_store(session, filename, content_type, data, session_id=None):
        return type(
            "Doc",
            (),
            {
                "id": 1,
                "filename": filename,
                "content_type": content_type,
                "size": len(data),
                "text": "x",
            },
        )()

    monkeypatch.setattr(chat_api, "handle_chat", fake_handle_chat)
    monkeypatch.setattr(chat_api, "stream_chat", fake_stream_chat)
    monkeypatch.setattr(chat_api, "SessionLocal", lambda: _SessionCM(db))
    monkeypatch.setattr(documents_api.intake, "store_document", fake_store)
    app.dependency_overrides[get_session] = _fake_session
    app.dependency_overrides[auth.require_staff] = lambda: object()
    yield TestClient(app)
    app.dependency_overrides.clear()


def cookie(value: str) -> dict:
    """A Cookie header, rather than TestClient's per-request cookies argument."""
    return {"Cookie": f"{resident_session.COOKIE_NAME}={value}"}


def chat(client, session_id=SESSION, headers=None):
    return client.post("/api/chat", json={"session_id": session_id, "message": "hi"}, headers=headers or {})


def stream(client, session_id=SESSION, headers=None):
    return client.post(
        "/api/chat/stream", json={"session_id": session_id, "message": "hi"}, headers=headers or {}
    )


def upload(client, session_id=SESSION, headers=None):
    return client.post(
        "/api/documents",
        files={"file": ("form.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
        data={"session_id": session_id} if session_id else {},
        headers=headers or {},
    )


# ------------------------------------------------------------------ the HMAC


def test_the_cookie_is_an_hmac_of_the_session_id_under_the_secret():
    value = resident_session.mint(SESSION)
    assert len(value) == 64 and SESSION not in value
    assert resident_session.verify(SESSION, value)
    assert not resident_session.verify(OTHER, value)


def test_changing_the_secret_invalidates_every_cookie(monkeypatch):
    """Rotating SESSION_SECRET is the revoke-everything switch; nothing is stored."""
    value = resident_session.mint(SESSION)
    monkeypatch.setattr(resident_session.settings, "session_secret", "a-different-secret")
    assert not resident_session.verify(SESSION, value)


@pytest.mark.parametrize("bad", ["", None, "deadbeef", resident_session.mint(SESSION)[:-1] + "0"])
def test_an_absent_or_tampered_cookie_does_not_verify(bad):
    if bad == resident_session.mint(SESSION)[:-1] + "0":
        assert bad != resident_session.mint(SESSION), "the fixture must actually differ"
    assert not resident_session.verify(SESSION, bad)


async def test_first_contact_asks_about_both_chat_messages_and_documents(db):
    """The rule is "no chat turn and no upload": one table is not enough."""
    seen = []

    class _Recorder(_Session):
        async def execute(self, statement=None, *args, **kwargs):
            seen.append(str(statement))
            return await super().execute(statement, *args, **kwargs)

    assert await resident_session.has_history(_Recorder(), SESSION) is False
    assert "chat_messages" in seen[0] and "documents" in seen[0]


# ------------------------------------------------------- first contact mints


def test_chat_mints_the_cookie_on_first_contact(client):
    response = chat(client)
    assert response.status_code == 200
    assert response.cookies[resident_session.COOKIE_NAME] == resident_session.mint(SESSION)
    header = response.headers["set-cookie"]
    assert "HttpOnly" in header and "SameSite=lax" in header and "Path=/" in header
    assert "Max-Age=2592000" in header  # 30 days


def test_the_stream_route_sets_the_cookie_header_too(client):
    """It is set on the StreamingResponse itself, so it precedes the first token."""
    response = stream(client)
    assert response.status_code == 200
    assert response.cookies[resident_session.COOKIE_NAME] == resident_session.mint(SESSION)
    assert "data: " in response.text


def test_an_upload_mints_the_cookie_on_first_contact(client):
    response = upload(client)
    assert response.status_code == 200
    assert response.cookies[resident_session.COOKIE_NAME] == resident_session.mint(SESSION)


def test_the_inline_form_mints_the_cookie_on_first_contact(client, monkeypatch):
    async def fake_submit(session, type_, fields, session_id, **kwargs):
        return type(
            "App",
            (),
            {
                "id": 1,
                "tracking_number": "PRM-2026-000001",
                "type": type_,
                "status": "submitted",
                "fields": fields,
                "missing_fields": [],
                "warnings": [],
                "department": None,
                "fee_cents": None,
                "resident_session_id": session_id,
                "document_id": None,
                "certificate_s3_key": None,
                "created_at": None,
                "updated_at": None,
            },
        )()

    from app.api import applications as applications_api

    monkeypatch.setattr(applications_api.engine, "submit", fake_submit)
    response = client.post(
        "/api/applications",
        json={"type": "service_request", "fields": {}, "session_id": SESSION},
    )
    assert response.status_code == 200
    assert response.cookies[resident_session.COOKIE_NAME] == resident_session.mint(SESSION)


def test_an_upload_without_a_session_id_is_unbound_and_still_works(client):
    """The pre-M20 contract: no session id, no cookie, no claim on anything."""
    response = upload(client, session_id=None)
    assert response.status_code == 200
    assert resident_session.COOKIE_NAME not in response.cookies


def test_a_first_turn_that_is_retried_with_its_own_cookie_is_fine(client):
    """The client may retry before the first turn has written any row."""
    response = chat(client, headers=cookie(resident_session.mint(SESSION)))
    assert response.status_code == 200


# --------------------------------------------------------- a claimed session


def test_a_second_request_without_the_cookie_is_refused(client, db):
    assert chat(client).status_code == 200
    db.has_history = True  # the first turn wrote a chat_messages row
    db.limits = [0, 0.0]
    # The TestClient kept the cookie it was given, which is what a browser does;
    # emptying the jar is the second browser that only knows the session id.
    client.cookies.clear()
    refused = chat(client)
    assert refused.status_code == 403
    assert refused.json()["detail"] == resident_session.FOREIGN_SESSION


def test_a_valid_cookie_gets_a_claimed_session_through(client, db):
    db.has_history = True
    assert chat(client, headers=cookie(resident_session.mint(SESSION))).status_code == 200


def test_a_cookie_minted_for_another_id_is_refused(client, db):
    db.has_history = True
    response = chat(client, headers=cookie(resident_session.mint(OTHER)))
    assert response.status_code == 403


def test_a_tampered_cookie_is_refused(client, db):
    db.has_history = True
    forged = resident_session.mint(SESSION)[:-1] + ("0" if resident_session.mint(SESSION)[-1] != "0" else "1")
    assert chat(client, headers=cookie(forged)).status_code == 403


@pytest.mark.parametrize("call", [stream, upload])
def test_the_stream_and_upload_routes_refuse_a_claimed_session_too(client, db, call):
    db.has_history = True
    assert call(client).status_code == 403


def test_a_stale_cookie_from_the_previous_conversation_mints_a_new_one(client):
    """ "New conversation" rotates the id; the browser still holds the old cookie."""
    response = chat(client, headers=cookie(resident_session.mint(OTHER)))
    assert response.status_code == 200
    assert response.cookies[resident_session.COOKIE_NAME] == resident_session.mint(SESSION)


def test_the_identity_check_runs_before_the_cost_guards(client, db):
    """A turn on someone else's id must not spend their quota to earn its 403."""
    db.has_history = True
    db.limits = []  # popping one would raise IndexError, so a 403 proves the order
    assert chat(client).status_code == 403


# ------------------------------------------------- the eval runner's cookie jar


async def test_the_runner_client_carries_its_cookie_to_the_next_turn():
    """A multi-turn item is one browser: turn 2 must send what turn 1 was given."""
    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("cookie"))
        return httpx.Response(
            200,
            json={"reply": "ok"},
            headers={"set-cookie": "resident_session=abc123; Path=/"},
        )

    async with eval_run.session_client(transport=httpx.MockTransport(handler)) as client:
        await client.post("http://api.test/api/chat", json={})
        await client.post("http://api.test/api/chat", json={})

    assert seen == [None, "resident_session=abc123"]


def test_each_item_gets_its_own_jar():
    """One shared client would carry item 1's cookie onto item 2's session id."""
    first, second = eval_run.session_client(), eval_run.session_client()
    first.cookies.set("resident_session", "abc123", domain="api.test")
    assert not second.cookies.get("resident_session", domain="api.test")
