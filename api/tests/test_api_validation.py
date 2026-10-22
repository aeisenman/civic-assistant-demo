"""Every bad request the red-team pass turned into a 500 must now be a 4xx.

Drives the FastAPI app with starlette's TestClient and a database session that
raises if it is ever touched, because each case must be rejected before any
query runs. Depends on: app.main, app.db.engine.get_session (overridden).
"""

import io

import pytest
from fastapi.testclient import TestClient

from app import auth
from app.db.engine import get_session
from app.main import app


class _NoDatabase:
    """Any use of the session in these tests is itself the failure."""

    async def execute(self, *args, **kwargs):  # pragma: no cover - must not run
        raise AssertionError("the request should have been rejected before the database")


async def _fake_session():
    yield _NoDatabase()


@pytest.fixture
def client():
    """No `with` on purpose: that would run the lifespan (migrations, S3, seed)."""
    app.dependency_overrides[get_session] = _fake_session
    # M11 guards the staff routes; validation must still run for a signed-in
    # client, so stand in for the session check rather than log in for real.
    app.dependency_overrides[auth.require_staff] = lambda: object()
    yield TestClient(app)
    app.dependency_overrides.clear()


# ------------------------------------------------------------------ list limits
@pytest.mark.parametrize(
    "url",
    ["/api/traces?limit=-1", "/api/applications?limit=-1", "/api/applications?limit=0"],
)
def test_a_negative_limit_is_a_422_not_a_500(client, url):
    # LIMIT -1 reached Postgres and came back "Internal Server Error".
    assert client.get(url).status_code == 422


@pytest.mark.parametrize("url", ["/api/traces?limit=100000", "/api/applications?limit=100000"])
def test_an_absurd_limit_is_refused_rather_than_silently_clamped(client, url):
    assert client.get(url).status_code == 422


# ------------------------------------------------------------------ ids
def test_an_id_larger_than_a_postgres_integer_is_a_404(client):
    response = client.get("/api/applications/9999999999999999999")
    assert response.status_code == 404
    assert "no application" in response.json()["detail"]


def test_the_same_bound_applies_to_the_certificate_route(client):
    assert client.get("/api/applications/9999999999999999999/certificate").status_code == 404


# ------------------------------------------------------------------ bodies
def test_a_field_of_the_wrong_type_is_a_422_not_a_500(client):
    response = client.post("/api/applications", json={"type": "permit", "fields": {"valuation_usd": "lots"}})
    assert response.status_code == 422
    assert response.json()["detail"]


def test_an_unknown_application_type_is_still_a_422(client):
    assert client.post("/api/applications", json={"type": "nope", "fields": {}}).status_code == 422


@pytest.mark.parametrize("message", ["", "   ", "\n\t"])
def test_a_blank_chat_message_is_refused_before_any_model_call(client, message):
    # It used to reach Bedrock, fail, and come back as "something went wrong on my side".
    response = client.post("/api/chat", json={"session_id": "s", "message": message})
    assert response.status_code == 422


# ------------------------------------------------------------------ uploads
def test_an_oversized_upload_is_a_413(client):
    from app.api.documents import MAX_UPLOAD_BYTES

    data = b"x" * (MAX_UPLOAD_BYTES + 1)
    response = client.post("/api/documents", files={"file": ("big.pdf", io.BytesIO(data), "application/pdf")})
    assert response.status_code == 413
    assert "limit" in response.json()["detail"]


# ------------------------------------------------------------- absurd id length
def test_an_id_of_four_thousand_digits_is_a_404_not_a_500(client):
    """CPython 3.12 refuses to int() a decimal string this long: it used to be a 500."""
    response = client.get("/api/applications/" + "9" * 4301)
    assert response.status_code == 404
    assert "no application" in response.json()["detail"]


def test_the_certificate_route_shares_that_guard(client):
    assert client.get("/api/applications/" + "9" * 4301 + "/certificate").status_code == 404


def test_the_certificate_route_is_staff_only(client):
    """A15: unauthenticated is a 401, so the id's existence is not leaked either."""
    app.dependency_overrides.pop(auth.require_staff)
    assert client.get("/api/applications/1/certificate").status_code == 401
