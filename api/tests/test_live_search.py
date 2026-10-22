"""search_city_website: the sandiego.gov-only filter, the tag stripper, the off switch.

The Brave key is not available in this repo, so the provider is exercised with a
mocked httpx transport; the SEARCH_PROVIDER=none path is the one a fresh clone hits.
"""

import httpx

from app.agents.rendering import citations_for, source_entries
from app.live import http, search
from app.live.search import SearchArgs, is_city_url, search_city_website, strip_tags
from app.rag.retrieve import Hit

BRAVE_PAYLOAD = {
    "web": {
        "results": [
            {"title": "Library cards", "url": "https://www.sandiego.gov/public-library/card"},
            {"title": "Spam", "url": "https://sandiego.gov.evil.example/phish"},
            {"title": "Hours", "url": "https://library.sandiego.gov/hours"},
        ]
    }
}
PAGE_HTML = (
    "<html><head><style>.x{color:red}</style><script>var a=1;</script></head>"
    "<body><h1>Get a library card</h1><p>Bring photo ID &amp; proof of address.</p></body></html>"
)


def _handler(request: httpx.Request) -> httpx.Response:
    if "api.search.brave.com" in str(request.url):
        assert request.headers["X-Subscription-Token"] == "test-key"
        assert "site:sandiego.gov" in request.url.params["q"]
        return httpx.Response(200, json=BRAVE_PAYLOAD)
    return httpx.Response(200, text=PAGE_HTML)


# ------------------------------------------------------------------ pure helpers
def test_only_sandiego_gov_hosts_pass_the_filter():
    assert is_city_url("https://www.sandiego.gov/x")
    assert is_city_url("https://library.sandiego.gov/hours")
    assert is_city_url("https://sandiego.gov")
    # The lookalike domain is the one this filter exists for.
    assert not is_city_url("https://sandiego.gov.evil.example/phish")
    assert not is_city_url("https://notsandiego.gov/x")
    assert not is_city_url("javascript:alert(1)")
    assert not is_city_url("")


def test_tag_stripper_drops_script_and_style_and_decodes_entities():
    text = strip_tags(PAGE_HTML)
    assert text == "Get a library card Bring photo ID & proof of address."
    assert "var a=1" not in text
    assert "color:red" not in text


def test_tag_stripper_truncates():
    assert len(strip_tags("<p>" + ("word " * 5000) + "</p>")) == 3000


# ------------------------------------------------------------------ the off switch
async def test_unconfigured_provider_says_so(live_on):
    result = await search_city_website(SearchArgs(query="library card"), None)
    assert result["error"] == "web search is not configured"


async def test_brave_without_a_key_is_still_unconfigured(live_on, monkeypatch):
    monkeypatch.setattr(search.settings, "search_provider", "brave")
    monkeypatch.setattr(search.settings, "search_api_key", "")
    result = await search_city_website(SearchArgs(query="library card"), None)
    assert result["error"] == "web search is not configured"


# ------------------------------------------------------------------ the brave path
def _configure(monkeypatch):
    monkeypatch.setattr(search.settings, "search_provider", "brave")
    monkeypatch.setattr(search.settings, "search_api_key", "test-key")
    http.set_transport(httpx.MockTransport(_handler))


async def test_brave_results_are_fetched_and_returned_as_sources(live_on, monkeypatch):
    _configure(monkeypatch)
    result = await search_city_website(SearchArgs(query="how do I get a library card"), None)
    urls = [s["url"] for s in result["sources"]]
    # Two pages fetched, and the lookalike host never made the shortlist.
    assert urls == [
        "https://www.sandiego.gov/public-library/card",
        "https://library.sandiego.gov/hours",
    ]
    assert result["sources"][0]["text"].startswith("Get a library card")


async def test_no_city_results_is_an_honest_empty_answer(live_on, monkeypatch):
    monkeypatch.setattr(search.settings, "search_provider", "brave")
    monkeypatch.setattr(search.settings, "search_api_key", "test-key")
    http.set_transport(httpx.MockTransport(lambda r: httpx.Response(200, json={"web": {"results": []}})))
    result = await search_city_website(SearchArgs(query="unicorn permits"), None)
    assert result["sources"] == []
    assert "No sandiego.gov page" in result["summary"]


async def test_a_dead_provider_does_not_raise(live_on, monkeypatch):
    monkeypatch.setattr(search.settings, "search_provider", "brave")
    monkeypatch.setattr(search.settings, "search_api_key", "test-key")
    http.set_transport(httpx.MockTransport(lambda r: httpx.Response(503, text="down")))
    result = await search_city_website(SearchArgs(query="library card"), None)
    assert result["sources"] == []


# ------------------------------------------------------------------ citations
async def test_fetched_pages_are_numbered_after_the_kb_chunks(live_on, monkeypatch):
    _configure(monkeypatch)
    result = await search_city_website(SearchArgs(query="library card"), None)

    # One retrieved KB chunk owns [1], so the two fetched pages are [2] and [3].
    hit = Hit(chunk_id=7, doc_title="trash.md", source_url=None, topic="trash", text="…", score=1.0)
    entries = source_entries([hit], result["sources"])
    assert [e["chunk_id"] for e in entries] == [7, None, None]
    assert entries[1]["source_url"] == "https://www.sandiego.gov/public-library/card"

    cited = citations_for("You need photo ID [2].", [hit], result["sources"])
    assert len(cited) == 1
    assert cited[0]["n"] == 2
    assert cited[0]["doc_title"] == "Library cards"
    assert cited[0]["chunk_id"] is None
    assert cited[0]["implicit"] is False

    # A number past the end of the list is ignored, not turned into a fake source.
    assert citations_for("see [9]", [hit], result["sources"])[0]["implicit"] is True
