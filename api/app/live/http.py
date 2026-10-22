"""One httpx front door for every live City call: timeout, TTL cache, no raises.

Called by app/live/geocode.py, arcgis.py and search.py. Depends on: httpx and
app.config. A live lookup is a nice-to-have on a resident's turn, so a slow or
broken City server must degrade to `None` in a few seconds, never to a 500.

The sandiego.gov host allow-list lives here rather than in search.py because
`fetch` is where a redirect can move the goalposts; search.py re-exports it.
"""

import logging
import time
from typing import Any

import httpx

from app.config import settings

log = logging.getLogger(__name__)

CACHE_TTL_S = 600  # 10 minutes: City map layers change far more slowly than that.
MAX_CACHE_ENTRIES = 256

ALLOWED_HOST_SUFFIX = ".sandiego.gov"

# url (with query) -> (expires_at, payload). One dict per process; the demo runs
# a single uvicorn worker, and a stale entry is only ever 10 minutes old.
_cache: dict[str, tuple[float, Any]] = {}
# Overridable in tests so no test ever opens a socket.
_transport: httpx.AsyncBaseTransport | None = None


def set_transport(transport: httpx.AsyncBaseTransport | None) -> None:
    """Install a mock transport (tests) or clear it (production)."""
    global _transport
    _transport = transport


def clear_cache() -> None:
    """Empty the response cache; tests need each case to start from cold."""
    _cache.clear()


def _cache_get(key: str) -> Any | None:
    entry = _cache.get(key)
    if entry is None:
        return None
    expires_at, payload = entry
    if expires_at < time.monotonic():
        _cache.pop(key, None)
        return None
    return payload


def host_of(url: str) -> str:
    """The lowercase host of an http(s) URL, or "" for anything else.

    Hand-rolled rather than urlparse so a `javascript:` or `data:` URL can never
    look like a host: anything that is not plainly http(s) returns "".
    """
    lowered = (url or "").lower()
    if not lowered.startswith(("http://", "https://")):
        return ""
    return lowered.split("://", 1)[1].split("/", 1)[0].split("@")[-1].split(":")[0]


def is_city_url(url: str) -> bool:
    """True only for http(s) URLs whose host is sandiego.gov or a subdomain."""
    host = host_of(url)
    return host == "sandiego.gov" or host.endswith(ALLOWED_HOST_SUFFIX)


def same_site(requested: str, final: str) -> bool:
    """May a redirect from `requested` to `final` be trusted?

    Redirects stay ON, because several City pages 301 from `sandiego.gov` to
    `www.sandiego.gov` and the ArcGIS endpoints redirect within their own host;
    `follow_redirects=False` would have turned those into silent `None`s and
    broken live lookups the demo depends on. Instead the *final* host has to pass
    the same test the first one did (audit row 25): a sandiego.gov URL that 302s
    to evil.com is dropped, and the Brave search API may only redirect to itself.
    """
    if host_of(final) == host_of(requested) and host_of(final):
        return True
    return is_city_url(requested) and is_city_url(final)


def _cache_put(key: str, payload: Any) -> None:
    if len(_cache) >= MAX_CACHE_ENTRIES:
        _cache.clear()  # crude, but a demo never gets near this
    _cache[key] = (time.monotonic() + CACHE_TTL_S, payload)


async def fetch(
    url: str,
    params: dict | None = None,
    headers: dict | None = None,
    *,
    as_json: bool,
) -> Any | None:
    """GET `url`, cached for 10 minutes. Returns None on any failure.

    `as_json=False` returns the response text (RSS, HTML). Every failure is
    logged with the URL so a trace reader can see which City service was down.
    """
    if not settings.live_data_enabled:
        log.info("live: LIVE_DATA_ENABLED=false, skipping %s", url)
        return None

    request = httpx.Request("GET", url, params=params)
    key = str(request.url)
    cached = _cache_get(key)
    if cached is not None:
        return cached

    try:
        async with httpx.AsyncClient(
            timeout=settings.live_http_timeout_s,
            transport=_transport,
            follow_redirects=True,
        ) as client:
            response = await client.get(url, params=params, headers=headers)
            if not same_site(url, str(response.url)):
                log.warning("live: refusing off-site redirect %s -> %s", url, response.url)
                return None
            response.raise_for_status()
            payload = response.json() if as_json else response.text
    except Exception as exc:  # noqa: BLE001 - a dead City server is not our crash
        log.warning("live: fetch failed for %s: %s", key, exc)
        return None

    _cache_put(key, payload)
    return payload


async def fetch_json(url: str, params: dict | None = None, headers: dict | None = None) -> Any | None:
    """Parsed JSON from a City endpoint, or None when it did not answer."""
    return await fetch(url, params, headers, as_json=True)


async def fetch_text(url: str, params: dict | None = None, headers: dict | None = None) -> str | None:
    """Raw body text from a City page, or None when it did not answer."""
    return await fetch(url, params, headers, as_json=False)
