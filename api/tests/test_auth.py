"""The staff login: hashing, the cookie round trip, the guard and the throttle.

There is no Postgres in the test environment, so the four storage functions in
app.auth are replaced with an in-memory fake and the routes are exercised through
httpx's ASGI transport (which skips the lifespan, so no migrations run). What is
under test is the HTTP contract the browser sees, not SQLAlchemy.
"""

import httpx
import pytest
from fastapi import Depends, FastAPI

from app import auth
from app.api import applications
from app.db.engine import get_session
from app.main import create_app
from app.workflows import engine

# --------------------------------------------------------------- passwords


def test_password_round_trip():
    encoded = auth.hash_password("correct horse")
    assert encoded.startswith("scrypt$")
    assert "correct horse" not in encoded
    assert auth.verify_password("correct horse", encoded)
    assert not auth.verify_password("Correct horse", encoded)
    assert not auth.verify_password("", encoded)


def test_each_hash_gets_its_own_salt():
    a = auth.hash_password("same")
    b = auth.hash_password("same")
    assert a != b
    assert auth.verify_password("same", a) and auth.verify_password("same", b)


def test_a_malformed_hash_is_a_failed_login_not_a_crash():
    assert not auth.verify_password("x", "not-a-hash")
    assert not auth.verify_password("x", "bcrypt$12$whatever")


def test_session_tokens_are_random_and_stored_only_as_a_digest():
    token = auth.new_session_token()
    assert token != auth.new_session_token()
    digest = auth.hash_token(token)
    assert len(digest) == 64 and token not in digest


# ------------------------------------------------------------------ fakes


class FakeUser:
    """Stands in for models.StaffUser; the routes only read three attributes."""

    def __init__(self, username="staff", password="staff", display_name="City Staff"):
        self.id = 1
        self.username = username
        self.display_name = display_name
        self.password_hash = auth.hash_password(password)


class FakeStore:
    """The three tables' worth of state the auth routes actually touch."""

    def __init__(self, user: FakeUser):
        self.user = user
        self.sessions: dict[str, int] = {}  # token hash -> user id

    async def get_user_by_username(self, session, username):
        return self.user if username == self.user.username else None

    async def create_session(self, session, user):
        token = auth.new_session_token()
        self.sessions[auth.hash_token(token)] = user.id
        return token

    async def resolve_session(self, session, token):
        if token and auth.hash_token(token) in self.sessions:
            return self.user
        return None

    async def revoke_session(self, session, token):
        self.sessions.pop(auth.hash_token(token or ""), None)


@pytest.fixture
def store(monkeypatch):
    """Patch the storage layer and make a wrong password fast in tests."""
    fake = FakeStore(FakeUser())
    for name in ("get_user_by_username", "create_session", "resolve_session", "revoke_session"):
        monkeypatch.setattr(auth, name, getattr(fake, name))
    monkeypatch.setattr(auth, "FAILED_LOGIN_DELAY_S", 0)
    auth.reset_failures()
    yield fake
    auth.reset_failures()


@pytest.fixture
def client(store):
    """The real app, with the database dependency stubbed out."""
    app = create_app()
    app.dependency_overrides[get_session] = lambda: None
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


# ------------------------------------------------------------ login / me


async def test_login_sets_an_httponly_cookie_and_me_answers(client):
    async with client:
        res = await client.post("/api/auth/login", json={"username": "staff", "password": "staff"})
        assert res.status_code == 200
        assert res.json()["display_name"] == "City Staff"

        cookie = res.headers["set-cookie"]
        assert "staff_session=" in cookie
        assert "HttpOnly" in cookie and "SameSite=lax" in cookie
        # http://testserver is not https, so the cookie must not be Secure or
        # the browser would drop it on the demo machine.
        assert "Secure" not in cookie

        me = await client.get("/api/auth/me")
        assert me.status_code == 200 and me.json()["username"] == "staff"


async def test_me_is_401_without_a_cookie(client):
    async with client:
        assert (await client.get("/api/auth/me")).status_code == 401


async def test_logout_ends_the_session(client, store):
    async with client:
        await client.post("/api/auth/login", json={"username": "staff", "password": "staff"})
        assert (await client.post("/api/auth/logout")).status_code == 200
        assert store.sessions == {}
        assert (await client.get("/api/auth/me")).status_code == 401


async def test_wrong_password_is_a_generic_401(client):
    async with client:
        res = await client.post("/api/auth/login", json={"username": "staff", "password": "nope"})
        assert res.status_code == 401
        assert res.json()["detail"] == "Incorrect username or password."
        assert "set-cookie" not in res.headers


async def test_an_unknown_username_gets_the_same_message(client):
    async with client:
        res = await client.post("/api/auth/login", json={"username": "ghost", "password": "nope"})
        assert res.status_code == 401
        assert res.json()["detail"] == "Incorrect username or password."


async def test_five_failures_in_a_minute_lock_the_username_out(client):
    async with client:
        for _ in range(auth.MAX_FAILURES):
            res = await client.post("/api/auth/login", json={"username": "staff", "password": "nope"})
            assert res.status_code == 401
        # The sixth attempt is refused before the password is even checked, so a
        # correct password does not get through either.
        res = await client.post("/api/auth/login", json={"username": "staff", "password": "staff"})
        assert res.status_code == 429


async def test_a_successful_login_clears_the_counter(client):
    async with client:
        await client.post("/api/auth/login", json={"username": "staff", "password": "nope"})
        assert auth.failures_in_window("staff") == 1
        await client.post("/api/auth/login", json={"username": "staff", "password": "staff"})
        assert auth.failures_in_window("staff") == 0


# ------------------------------------------------------------ the guard


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/applications"),
        ("GET", "/api/applications/PRM-2026-000123"),
        ("POST", "/api/applications/PRM-2026-000123/advance"),
        ("GET", "/api/applications/PRM-2026-000123/certificate"),
        ("GET", "/api/traces"),
        ("GET", "/api/traces/1"),
    ],
)
async def test_staff_routes_are_401_without_a_session(client, method, path):
    async with client:
        res = await client.request(method, path, json={"to": "approved"})
        assert res.status_code == 401, f"{method} {path} was {res.status_code}"


async def test_require_staff_returns_the_signed_in_user(store):
    """The dependency itself, wired to a route that echoes the username back."""
    app = FastAPI()

    @app.get("/whoami")
    async def whoami(user=Depends(auth.require_staff)):
        return {"username": user.username}

    app.dependency_overrides[get_session] = lambda: None
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as c:
        token = await store.create_session(None, store.user)
        c.cookies.set(auth.COOKIE_NAME, token)
        assert (await c.get("/whoami")).json() == {"username": "staff"}


# ------------------------------------------------------------ actor on advance


async def test_advance_records_the_staff_username_as_the_actor(client, store, monkeypatch):
    """The audit row must name the account, not the literal string "staff"."""
    store.user.username = "jdoe"
    seen: dict = {}

    class FakeApp:
        id = 7
        tracking_number = "PRM-2026-000123"
        status = "in_review"
        type = "permit"
        fields: dict = {}
        missing_fields: list = []
        warnings: list = []
        department = "DSD"
        fee_cents = 1000
        resident_session_id = None
        document_id = None
        certificate_s3_key = None
        created_at = None
        updated_at = None

    async def fake_find(session, id_or_tracking):
        return FakeApp()

    async def fake_advance(session, app, to, actor, note=None):
        seen.update(to=to, actor=actor, note=note)
        return app

    monkeypatch.setattr(applications, "_find", fake_find)
    monkeypatch.setattr(engine, "advance", fake_advance)

    async with client:
        token = await store.create_session(None, store.user)
        client.cookies.set(auth.COOKIE_NAME, token)
        res = await client.post(
            "/api/applications/PRM-2026-000123/advance",
            json={"to": "approved", "note": "plans ok"},
        )
        assert res.status_code == 200
        assert seen == {"to": "approved", "actor": "jdoe", "note": "plans ok"}
