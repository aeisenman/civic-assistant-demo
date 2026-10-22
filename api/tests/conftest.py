"""Test-wide settings: no live City calls unless a test asks for them.

Imported by pytest before any test module, so this runs before app.config builds
its module-level Settings singleton. Depends on: app.config and app.live.http.
The M8 tools would otherwise hit webmaps.sandiego.gov from a unit test.
"""

import os

# Set before app.config is imported anywhere: the Settings object is built at
# import time, so a monkeypatch inside a test would be too late.
os.environ.setdefault("LIVE_DATA_ENABLED", "false")
os.environ.setdefault("SEARCH_PROVIDER", "none")
os.environ.setdefault("SEARCH_API_KEY", "")
# The per-IP token bucket lives in Postgres, and the suite has no Postgres: every
# request through TestClient would take the "limiter unavailable, allow" branch
# and log a warning. tests/test_rate_limit.py turns it back on for itself.
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")

import pytest  # noqa: E402

from app.config import settings  # noqa: E402
from app.live import http  # noqa: E402


@pytest.fixture(autouse=True)
def _no_live_leakage():
    """Every test starts with an empty cache, live off and no mock transport."""
    http.clear_cache()
    http.set_transport(None)
    settings.live_data_enabled = False
    yield
    http.clear_cache()
    http.set_transport(None)
    settings.live_data_enabled = False


@pytest.fixture
def live_on(monkeypatch):
    """Turn live lookups on for a test that installs a mock httpx transport."""
    monkeypatch.setattr(settings, "live_data_enabled", True)
    return settings
