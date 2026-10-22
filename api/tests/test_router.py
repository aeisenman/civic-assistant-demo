"""Tier selection rules and the tracking-number override — no model calls."""

import pytest

from app.llm.client import Tier
from app.llm.router import Classification, classify, select_tier


def make(**kwargs) -> Classification:
    base = {"intent": "permits", "confidence": 0.9, "complexity": "low", "secondary_intents": []}
    return Classification(**{**base, **kwargs})


def test_confident_single_intent_uses_smart():
    tier, reason = select_tier(make())
    assert tier is Tier.SMART
    assert "permits" in reason


def test_low_confidence_escalates():
    tier, reason = select_tier(make(confidence=0.4))
    assert tier is Tier.ESCALATE
    assert "confidence" in reason


def test_high_complexity_escalates():
    assert select_tier(make(complexity="high"))[0] is Tier.ESCALATE


def test_any_secondary_intent_escalates():
    tier, reason = select_tier(make(secondary_intents=["trash"]))
    assert tier is Tier.ESCALATE
    assert "trash" in reason


def test_smalltalk_stays_smart_even_when_unsure():
    tier, reason = select_tier(make(intent="smalltalk", confidence=0.1, complexity="high"))
    assert tier is Tier.SMART
    assert "smalltalk" in reason


@pytest.mark.parametrize(
    "message,intent",
    [
        ("What's the status of PRM-2026-000102?", "permits"),
        ("check btc-2026-000201 please", "business"),
        ("SR-2026-000301 status?", "service_request"),
    ],
)
async def test_tracking_number_overrides_without_a_model_call(message, intent):
    # No network here: the regex short-circuits before chat_json is reached.
    result = await classify(message, [])
    assert result.intent == intent
    assert result.confidence == 1.0
    assert result.complexity == "low"


def test_partial_tracking_number_is_not_an_override():
    from app.llm.router import _override

    assert _override("my permit PRM-2026-12 is stuck") is None
