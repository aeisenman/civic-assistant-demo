"""Locks the M10 act-then-ask rules and the cross-domain tool allow-list.

Run by pytest. Depends on: app.agents.profiles and app.tools.registry only —
these are pure data, so no database, no network and no model.
"""

import json

import pytest

from app.agents import profiles
from app.agents.profiles import (
    CROSS_DOMAIN_TOOLS,
    PROFILES,
    SEARCH_RULE,
    SEARCH_TOOL,
    SHARED_PREAMBLE,
    profile_for,
    system_prompt_for,
    tools_for,
)
from app.config import settings
from app.seed import loader
from app.tools.registry import TOOLS

DOMAIN_INTENTS = ("permits", "business", "trash", "service_request", "events", "general")


@pytest.fixture
def search_provider(monkeypatch):
    """Set SEARCH_PROVIDER for one test and put it back afterwards."""

    def _set(value: str):
        monkeypatch.setattr(settings, "search_provider", value)

    return _set


def test_every_profile_tool_is_a_real_tool():
    for intent, profile in PROFILES.items():
        for name in profile.tools:
            assert name in TOOLS, f"{intent} allows unknown tool {name}"


def test_domain_profiles_carry_the_cross_domain_lookups():
    """A second request in the same message must not hit an empty allow-list."""
    for intent in DOMAIN_INTENTS:
        missing = [t for t in CROSS_DOMAIN_TOOLS if t not in profile_for(intent).tools]
        assert not missing, f"{intent} cannot answer a tacked-on request needing {missing}"


def test_the_cross_domain_list_is_exactly_these_tools():
    """Pinned on purpose: adding a tool here widens every profile at once.

    Read-only lookups and the two fee estimators only. Anything that writes —
    start_application, create_service_request — stays behind its own intent.
    """
    assert CROSS_DOMAIN_TOOLS == (
        "get_trash_schedule",
        "get_next_pickup",
        "search_events",
        "get_council_district",
        "get_application_status",
        "get_referral",
        "estimate_permit_fee",
        "estimate_business_tax",
    )
    assert "start_application" not in CROSS_DOMAIN_TOOLS
    assert "create_service_request" not in CROSS_DOMAIN_TOOLS


def test_a_trash_turn_can_still_quote_a_permit_fee():
    """Red-team finding 10: half a multi-intent message was lost to the allow-list."""
    for intent in DOMAIN_INTENTS:
        tools = profile_for(intent).tools
        assert "estimate_permit_fee" in tools
        assert "estimate_business_tax" in tools


def test_web_search_is_offered_only_when_a_provider_is_configured(search_provider):
    """Red-team finding 11: the shipped .env has SEARCH_PROVIDER=none."""
    search_provider("brave")
    assert SEARCH_TOOL in tools_for(PROFILES["general"])
    assert SEARCH_TOOL in tools_for(PROFILES["permits"])

    search_provider("none")
    for profile in PROFILES.values():
        assert SEARCH_TOOL not in tools_for(profile)


def test_the_strict_sources_rule_drops_the_search_line_when_search_is_off(search_provider):
    search_provider("brave")
    assert SEARCH_TOOL in system_prompt_for(PROFILES["general"])
    assert system_prompt_for(PROFILES["general"]) == PROFILES["general"].system_prompt

    search_provider("none")
    for profile in PROFILES.values():
        assert SEARCH_TOOL not in system_prompt_for(profile)
    # Only that rule goes; the rest of the preamble is untouched.
    trimmed = system_prompt_for(PROFILES["general"])
    assert "619-236-5555" in trimmed
    assert SEARCH_RULE not in trimmed


def test_smalltalk_still_has_no_tools():
    """Cross-domain does not mean universal: chit-chat calls nothing."""
    assert profile_for("smalltalk").tools == []


def test_no_profile_lists_a_tool_twice():
    for intent, profile in PROFILES.items():
        assert len(profile.tools) == len(set(profile.tools)), intent


def test_preamble_states_the_act_then_ask_rules():
    """The three M10 rules: finish every request, act before asking, name the number."""
    lowered = SHARED_PREAMBLE.lower()
    assert "more than one request" in lowered
    assert "never answer one part and defer the other" in lowered
    assert "ask for the optional extras" in lowered
    assert "state the tracking number" in lowered


def test_service_request_profile_does_not_block_filing_on_a_photo():
    """create_service_request takes no photo argument, so waiting for one is a dead end."""
    prompt = PROFILES["service_request"].system_prompt.lower()
    assert "the description is optional" in prompt
    assert "the tool takes no photo, so never wait for either before filing" in prompt
    assert "file the case first" in prompt
    assert "photo" not in TOOLS["create_service_request"].model.model_fields


def test_service_request_can_be_filed_with_only_a_category_and_an_address():
    """Rule (b) is only honest if the tool schema agrees: description is optional."""
    args = TOOLS["create_service_request"].model(category="pothole", address="3355 University Ave")
    assert args.description == ""


# ------------------------------------------- M27: the prompt reads the category table
def test_every_seeded_service_category_reaches_the_service_request_prompt():
    """M23 finding: the prompt listed eleven of the twenty-one categories by hand.

    A resident reporting an encampment, an STRO violation or an ADA barrier
    therefore got "other", because those three rows exist in the table but had
    never been typed into the prompt. The list is read from the seed file now, so
    what this test really asserts is that nobody has typed it back in.
    """
    rows = json.loads(profiles.SERVICE_CATEGORIES_JSON.read_text())
    prompt = system_prompt_for(PROFILES["service_request"])
    missing = [row["category"] for row in rows if row["category"] not in prompt]
    assert missing == [], f"the service_request prompt never offers {missing}"
    # The three the hand-written list forgot, named so the regression reads plainly.
    for category in ("homeless_encampment", "stro_code_enforcement", "ada_accessibility"):
        assert category in prompt


def test_the_category_list_comes_from_the_table_the_tool_validates_against():
    """The prompt and app/seed/loader.py must read one file, not two copies of it."""
    assert profiles.SERVICE_CATEGORIES_JSON == loader.SEED_DIR / "service_categories.json"
    assert profiles.SERVICE_CATEGORIES  # never silently empty
    assert len(profiles.SERVICE_CATEGORIES) == len(set(profiles.SERVICE_CATEGORIES))


def test_a_filing_reply_must_quote_the_tool_verbatim():
    """M23 finding: a reply named a department create_service_request never returned."""
    assert "word for word" in SHARED_PREAMBLE
    for phrase in ("department", "tracking number", "timeframe"):
        assert phrase in SHARED_PREAMBLE
    # Every domain profile inherits the rule, not just the two that file things.
    for intent in DOMAIN_INTENTS:
        assert "word for word" in system_prompt_for(PROFILES[intent])
