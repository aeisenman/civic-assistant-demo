"""CORS is the whole cross-origin authority of this API, so it is asserted.

Drives the FastAPI app with starlette's TestClient; no database, no model.
Depends on: app.main and app.config. Audit finding 16 is the reason this file
exists — `allow_methods=["*"]` plus `allow_credentials=True` meant one typo'd
WEB_ORIGIN handed a stranger full credentialed access to every route.
"""

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


@pytest.fixture
def client():
    """No `with` on purpose: that would run the lifespan (migrations, S3, seed)."""
    return TestClient(app)


@pytest.fixture
def origin() -> str:
    return settings.web_origins[0]


def _preflight(client: TestClient, origin: str, method: str, headers: str = "content-type"):
    return client.options(
        "/api/chat",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": headers,
        },
    )


@pytest.mark.parametrize("method", ["GET", "POST", "DELETE"])
def test_the_three_methods_the_web_app_uses_are_allowed(client, origin, method):
    response = _preflight(client, origin, method)
    assert response.status_code == 200
    assert origin in response.headers["access-control-allow-origin"]
    assert method in response.headers["access-control-allow-methods"]


@pytest.mark.parametrize("method", ["PUT", "PATCH"])
def test_a_preflight_for_a_method_we_never_use_is_refused(client, origin, method):
    """Starlette answers a disallowed preflight with 400 and names the reason.

    It still echoes the allow-* headers on that 400 (they were built before the
    method was checked), so the assertion that matters is the status and the
    body: a browser refuses the real request on either.
    """
    response = _preflight(client, origin, method)
    assert response.status_code == 400
    assert "Disallowed CORS method" in response.text
    assert method not in response.headers.get("access-control-allow-methods", "")


def test_allowed_headers_are_the_three_the_client_actually_sends(client, origin):
    allowed = _preflight(client, origin, "POST", "content-type, x-request-id, idempotency-key")
    assert allowed.status_code == 200
    assert "access-control-allow-origin" in allowed.headers


def test_an_unexpected_request_header_is_refused(client, origin):
    response = _preflight(client, origin, "POST", "x-made-up-header")
    assert response.status_code == 400


def test_an_unknown_origin_gets_nothing(client):
    response = _preflight(client, "https://evil.example", "POST")
    assert "access-control-allow-origin" not in response.headers


def test_the_request_id_header_is_still_exposed(client, origin):
    response = client.get("/health", headers={"Origin": origin})
    assert response.headers["access-control-expose-headers"] == "X-Request-ID"
