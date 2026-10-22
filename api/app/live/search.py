"""Last-resort web search, restricted to sandiego.gov, with the pages fetched.

Registered as the `search_city_website` tool in app/tools/registry.py and offered
to every profile after the KB and the other tools. Depends on: app/live/http.py
and SEARCH_PROVIDER / SEARCH_API_KEY in app/config.py. The point is to turn a
search result into a *source* the model can cite, so a fetched City page is
evidence and the model's own memory still is not.
"""

import logging
from html.parser import HTMLParser

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.live import http

# Re-exported: the allow-list moved to app/live/http.py in M19 so `fetch` can
# re-check the host a redirect landed on, and the name stays importable here.
from app.live.http import ALLOWED_HOST_SUFFIX, is_city_url  # noqa: F401

log = logging.getLogger(__name__)

BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"
SITE_FILTER = "site:sandiego.gov"
MAX_RESULTS = 2  # pages actually fetched
MAX_CANDIDATES = 10  # results asked of the provider before filtering
MAX_TEXT_CHARS = 3000

NOT_CONFIGURED = "web search is not configured"
SKIP_TAGS = {"script", "style", "noscript", "template", "svg"}


class SearchArgs(BaseModel):
    query: str = Field(description="What to look up on sandiego.gov, in plain words")


class _TextExtractor(HTMLParser):
    """Body text only: stdlib html.parser, so no new dependency for one tool."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        """Start skipping when a script/style block opens."""
        if tag in SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        """Stop skipping when that block closes."""
        if tag in SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        """Collect visible text only; whitespace-only runs are noise."""
        if self._skip_depth:
            return
        text = data.strip()
        if text:
            self.parts.append(text)


def strip_tags(html: str, limit: int = MAX_TEXT_CHARS) -> str:
    """Readable text from an HTML page, collapsed to single spaces and truncated."""
    parser = _TextExtractor()
    try:
        parser.feed(html)
    except Exception as exc:  # noqa: BLE001 - malformed City HTML is not our crash
        log.warning("search: html parse failed: %s", exc)
    return " ".join(" ".join(parser.parts).split())[:limit]


async def brave_results(query: str) -> list[dict]:
    """Brave web results for `<query> site:sandiego.gov`, off-site hits dropped."""
    payload = await http.fetch_json(
        BRAVE_URL,
        {"q": f"{query} {SITE_FILTER}", "count": MAX_CANDIDATES},
        {"X-Subscription-Token": settings.search_api_key, "Accept": "application/json"},
    )
    results = ((payload or {}).get("web") or {}).get("results") or []
    return [
        {"title": r.get("title") or r.get("url"), "url": r.get("url")}
        for r in results
        if is_city_url(r.get("url") or "")
    ]


async def search_city_website(args: SearchArgs, session: AsyncSession) -> dict:
    """Search sandiego.gov and return the top pages' text as citable sources."""
    provider = (settings.search_provider or "none").strip().lower()
    if provider != "brave" or not settings.search_api_key:
        log.info("search: provider=%s, key=%s", provider, bool(settings.search_api_key))
        return {"error": NOT_CONFIGURED, "summary": NOT_CONFIGURED}

    hits = await brave_results(args.query)
    if not hits:
        message = f"No sandiego.gov page came back for '{args.query}'."
        return {"sources": [], "summary": message}

    sources: list[dict] = []
    for hit in hits[:MAX_RESULTS]:
        html = await http.fetch_text(hit["url"])
        if not html:
            continue
        sources.append({"title": hit["title"], "url": hit["url"], "text": strip_tags(html)})
    if not sources:
        message = f"I found sandiego.gov pages for '{args.query}' but none of them loaded."
        return {"sources": [], "summary": message}
    return {
        "sources": sources,
        "summary": "Fetched from sandiego.gov: " + "; ".join(s["url"] for s in sources),
    }
