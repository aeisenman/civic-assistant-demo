"""The model client's timeout and retry budget, and the startup step wrapping.

Two M14 bounds that live outside a route: app/llm/client.py must not inherit the
SDK's 600s x 2 defaults, and app/main.py's lifespan must survive a failed step.
Depends on: app.llm.client, app.main, app.api.health — no network either way.
"""

import httpx
import pytest

from app import main as main_module
from app.api import health as health_api
from app.config import settings
from app.llm import client as llm


@pytest.fixture(autouse=True)
def fresh_clients():
    """The clients are module singletons; a test must not keep the next one's."""
    llm._chat_client = None
    llm._embed_client = None
    yield
    llm._chat_client = None
    llm._embed_client = None


# ------------------------------------------------------------------- timeouts
def test_the_timeout_comes_from_config_not_from_the_sdk_default():
    """openai's default is a 600-second read timeout: half an hour with retries."""
    timeout = llm.client_timeout()
    assert isinstance(timeout, httpx.Timeout)
    assert timeout.read == settings.llm_timeout_s
    assert timeout.connect == 5.0


def test_llm_timeout_s_defaults_to_forty_five_seconds():
    assert settings.llm_timeout_s == 45.0


@pytest.mark.parametrize("build", ["chat", "embed"])
def test_both_clients_are_built_with_that_budget_and_one_retry(build):
    client = llm.chat_client() if build == "chat" else llm.embed_client()
    assert client.timeout.read == settings.llm_timeout_s
    assert client.timeout.connect == 5.0
    # Two retries of a 45s timeout is 135 seconds of silence for the resident.
    assert client.max_retries == 1


def test_a_changed_setting_reaches_the_next_client(monkeypatch):
    """LLM_TIMEOUT_S is a knob, not a constant baked in at import."""
    monkeypatch.setattr(settings, "llm_timeout_s", 7.0)
    llm._chat_client = None
    assert llm.chat_client().timeout.read == 7.0


# ------------------------------------------------------------ startup wrapping
async def test_a_failing_startup_step_is_recorded_and_not_raised():
    health_api.clear_startup_errors()

    def explode():
        raise RuntimeError("seaweedfs refused the connection")

    await main_module._startup_step("s3_bucket", explode)
    assert "seaweedfs refused" in health_api.STARTUP_ERRORS["s3_bucket"]
    health_api.clear_startup_errors()


async def test_a_failing_kb_ingest_leaves_the_app_serving(monkeypatch):
    """The exact crash loop from the audit: bad Bedrock creds during ingest."""
    health_api.clear_startup_errors()

    async def ok():
        return None

    async def ingest_fails():
        raise RuntimeError("embeddings refused")

    monkeypatch.setattr(main_module, "run_migrations", ok)
    monkeypatch.setattr(main_module.s3, "ensure_bucket", lambda: None)
    monkeypatch.setattr(main_module, "seed_all", ok)
    monkeypatch.setattr(main_module, "ingest_kb", ingest_fails)
    monkeypatch.setattr(settings, "worker_enabled", False)

    # The lifespan completing at all is the assertion: it used to raise here,
    # which aborted startup and crash-looped the container.
    async with main_module.lifespan(main_module.app):
        assert "embeddings refused" in health_api.STARTUP_ERRORS["kb_ingest"]
    health_api.clear_startup_errors()


async def test_a_clean_startup_records_nothing(monkeypatch):
    health_api.record_startup_error("stale", RuntimeError("from a previous boot"))

    async def ok():
        return None

    async def ingest_ok():
        return {"chunks": 12}

    monkeypatch.setattr(main_module, "run_migrations", ok)
    monkeypatch.setattr(main_module.s3, "ensure_bucket", lambda: None)
    monkeypatch.setattr(main_module, "seed_all", ok)
    monkeypatch.setattr(main_module, "ingest_kb", ingest_ok)
    monkeypatch.setattr(settings, "worker_enabled", False)

    async with main_module.lifespan(main_module.app):
        assert health_api.STARTUP_ERRORS == {}
