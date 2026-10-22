"""The eval scorer's pure functions, and the shape of golden.json itself.

Run by `uv run pytest`; imports evals/run.py, which needs no API. These guard
the mechanical scoring rules (PLAN.md §14: no LLM judge) and the M9 additions —
turns, must_not_contain, must_contain_any, multiple tools, categories.
"""

import json

import pytest

from evals.run import (
    CATEGORIES,
    GOLDEN,
    category_of,
    expected_tools,
    guardrail_check,
    keyword_match,
    keywords,
    numbers_checked,
    numbers_from_tools,
    parse_ids,
    score_item,
    summarise,
    tool_match,
    turns_of,
)

INTENTS = {"permits", "business", "trash", "service_request", "events", "general", "smalltalk"}


def response(reply="", tools=(), intent=None, citations=0, cost=0.0, latency=0):
    """A minimal /api/chat response, so the scorer can be tested without a stack."""
    return {
        "reply": reply,
        "citations": [{"n": i} for i in range(citations)],
        "trace": {
            "intent": intent,
            "tool_calls": [{"name": t} for t in tools],
            "cost_usd": cost,
            "latency_ms": latency,
        },
    }


# ---------------------------------------------------------------- keywords


def test_keywords_drops_short_words_and_stopwords():
    assert keywords("The City of San Diego issues permits") == ["issues", "permits"]


def test_keyword_match_needs_two_significant_words():
    expected = "Recycling is collected biweekly on alternating weeks"
    ok, hits = keyword_match(expected, "your recycling is collected every other week")
    assert ok and hits >= 2
    assert keyword_match(expected, "sure, happy to help")[0] is False


def test_keyword_match_accepts_a_single_shared_number():
    # One matching number is enough: a fee answer is mostly digits.
    assert keyword_match("roughly $45.35 (estimate)", "that comes to about $45.35")[0] is True
    # Single digits do not count, or "1" would match nearly every reply.
    assert keyword_match("zone 1", "zone 4 collects on 1 Monday")[0] is False


def test_keyword_match_tolerates_thousands_separators():
    assert keyword_match("a $50,000 renovation", "a valuation of 50000 dollars")[0] is True


# ---------------------------------------------------------------- tools


def test_expected_tools_reads_the_single_tool_field():
    item = {"expect": "tool", "tool": "get_trash_schedule"}
    assert expected_tools(item) == ["get_trash_schedule"]


def test_expected_tools_prefers_the_plural_field():
    item = {"expect": "tool", "tool": None, "tools": ["a", "b"]}
    assert expected_tools(item) == ["a", "b"]


def test_rag_and_out_of_scope_items_require_no_tool():
    assert expected_tools({"expect": "rag", "tool": None}) == []
    assert expected_tools({"expect": "none", "tool": None}) == []
    assert tool_match({"expect": "rag", "tool": None}, []) is True


def test_tool_match_needs_every_named_tool():
    item = {"expect": "tool", "tool": None, "tools": ["search_events", "get_council_district"]}
    assert tool_match(item, ["search_events", "get_council_district"]) is True
    assert tool_match(item, ["search_events"]) is False
    # Extra tools are allowed; the check is "at least once", not "only these".
    assert tool_match(item, ["get_referral", "get_council_district", "search_events"]) is True


# ---------------------------------------------------------------- guardrails


def test_guardrail_is_vacuously_true_without_phrases():
    ok, reasons = guardrail_check({}, "anything at all")
    assert ok is True and reasons == []


def test_must_not_contain_is_case_insensitive():
    item = {"must_not_contain": ["generally speaking"]}
    ok, reasons = guardrail_check(item, "Generally Speaking, California law says...")
    assert ok is False and "generally speaking" in reasons[0]


def test_must_contain_any_needs_one_hit():
    item = {"must_contain_any": ["couldn't find", "no record"]}
    assert guardrail_check(item, "I have no record of that number.")[0] is True
    assert guardrail_check(item, "It is in review.")[0] is False


def test_both_phrase_lists_apply_together():
    item = {"must_not_contain": ["banana"], "must_contain_any": ["wednesday"]}
    assert guardrail_check(item, "Collection is Wednesday.")[0] is True
    assert guardrail_check(item, "Wednesday. BANANA")[0] is False
    assert len(guardrail_check({**item}, "nothing useful")[1]) == 1


# ---------------------------------------------------------------- turns


def test_turns_of_defaults_to_the_question():
    assert turns_of({"question": "hi"}) == ["hi"]


def test_turns_of_returns_the_turn_list_in_order():
    item = {"question": "a", "turns": ["a", "b"]}
    assert turns_of(item) == ["a", "b"]


def test_category_defaults_to_standard():
    assert category_of({}) == "standard"
    assert category_of({"category": "adversarial"}) == "adversarial"


# ---------------------------------------------------------------- score_item


BASE = {
    "id": 1,
    "split": "dev",
    "question": "q",
    "intent": "trash",
    "expect": "tool",
    "tool": "get_trash_schedule",
    "expected_answer": "zone Z06 collected Wednesday",
}


def test_score_item_scores_the_last_turn_but_unions_the_tools():
    item = {**BASE, "tool": None, "tools": ["get_trash_schedule"], "turns": ["a", "b"]}
    rows = [
        response(reply="Wednesday.", tools=["get_trash_schedule"], intent="trash", cost=0.01),
        response(reply="Recycling is on Wednesday in zone Z06.", intent="trash", cost=0.02),
    ]
    row = score_item(item, rows)
    assert row["turns_sent"] == 2
    assert row["actual_tools"] == ["get_trash_schedule"]
    assert row["tool_ok"] is True
    assert row["intent_ok"] is True
    assert row["keyword_ok"] is True
    assert row["reply"].startswith("Recycling")
    assert row["cost_usd"] == pytest.approx(0.03)  # summed over the whole item


def test_score_item_flags_a_guardrail_breach_without_touching_the_other_checks():
    item = {**BASE, "must_not_contain": ["banana"]}
    row = score_item(
        item,
        [response(reply="Zone Z06, Wednesday. BANANA", tools=["get_trash_schedule"], intent="trash")],
    )
    assert row["guardrail_ok"] is False
    assert row["intent_ok"] and row["tool_ok"] and row["keyword_ok"]


def test_score_item_requires_citations_only_for_rag_items():
    rag = {**BASE, "expect": "rag", "tool": None}
    assert score_item(rag, [response(reply="zone Z06 Wednesday", intent="trash")])["citations_ok"] is False
    assert score_item(rag, [response(reply="x", intent="trash", citations=2)])["citations_ok"] is True
    assert score_item(BASE, [response(reply="x", tools=["get_trash_schedule"])])["citations_ok"] is True


def test_score_item_survives_a_dead_api():
    row = score_item(BASE, [{"reply": "", "citations": [], "trace": {"error": "boom"}}])
    assert row["error"] == "boom"
    assert row["intent_ok"] is False and row["tool_ok"] is False and row["keyword_ok"] is False
    assert row["guardrail_ok"] is True  # no phrases on this item, so nothing to breach


def test_summarise_reports_five_metrics_and_handles_an_empty_split():
    hit = response(reply="zone Z06 Wednesday", tools=["get_trash_schedule"], intent="trash")
    rows = [score_item(BASE, [hit])]
    line = summarise(rows, "dev")
    for metric in ("intent=", "tool=", "citations=", "keywords=", "guardrail="):
        assert metric in line
    assert "n= 0" in summarise([], "holdout")


# -------------------------------------------------------- numbers_from_tools (M19)


def item_with(reply_numbers_from=(), category="hardening", **extra):
    """A golden item stub whose only interesting part is its category."""
    return {
        "id": 999,
        "question": "how much is it?",
        "intent": "permits",
        "expect": "tool",
        "expected_answer": "an estimate",
        "split": "dev",
        "category": category,
        **extra,
    }


def tool_response(reply, summary="", arguments=None, citations_text=""):
    """A /api/chat response whose trace carries one tool call, like the real one."""
    return {
        "reply": reply,
        "citations": [{"n": 1, "text": citations_text, "doc_title": "KB"}] if citations_text else [],
        "trace": {
            "intent": "permits",
            "tool_calls": [
                {"name": "estimate_permit_fee", "arguments": arguments or {}, "result_summary": summary}
            ],
        },
    }


def test_a_fee_the_tool_produced_is_accepted():
    ok, bad = numbers_from_tools(
        item_with(), [tool_response("The fee is about $1,234.50 (estimate).", "no-plan permit: $1,234.50")]
    )
    assert ok and bad == []


def test_a_fee_no_tool_produced_is_flagged():
    ok, bad = numbers_from_tools(
        item_with(), [tool_response("The fee is about $1,234.50 (estimate).", "no-plan permit: $560.00")]
    )
    assert not ok and bad == ["1234.50"]


def test_a_figure_the_tool_returned_in_cents_counts_as_support():
    """Tools carry money as fee_cents; the reply says dollars. Same fact."""
    ok, bad = numbers_from_tools(item_with(), [tool_response("That comes to $43.88.", '{"fee_cents": 4388}')])
    assert ok and bad == []


def test_a_number_the_resident_typed_is_not_an_invention():
    item = item_with(question="my budget is $85,000, what is the permit fee?")
    ok, bad = numbers_from_tools(item, [tool_response("On a $85,000 valuation the fee is an estimate.")])
    assert ok and bad == []


def test_dates_and_tracking_numbers_are_exempt():
    item = item_with(question="status of PRM-2026-000104?")
    reply = "PRM-2026-000104 is in review; the next hearing is 2026-12-31 (31/12/2026)."
    ok, bad = numbers_from_tools(item, [tool_response(reply, "in review")])
    assert ok and bad == []


def test_the_general_information_line_is_not_an_invented_number():
    ok, bad = numbers_from_tools(
        item_with(), [{"reply": "I don't have that — call 619-236-5555.", "citations": [], "trace": {}}]
    )
    assert ok and bad == []


def test_a_number_quoted_from_a_cited_source_is_supported():
    reply = "Plans are checked within 8,000 square feet under the 2026 code [1]."
    ok, bad = numbers_from_tools(
        item_with(), [tool_response(reply, "", citations_text="applies up to 8,000 square feet")]
    )
    assert ok and bad == []


def test_small_numbers_are_left_alone():
    """ "4 employees" and "every 2 weeks" are prose, not claims about an amount."""
    reply = "Recycling goes out every 2 weeks for 4 carts."
    ok, bad = numbers_from_tools(item_with(), [tool_response(reply)])
    assert ok and bad == []


def test_the_check_is_scored_for_hardening_and_only_reported_elsewhere():
    responses = [tool_response("The fee is $9,999.")]
    hardening = score_item(item_with(), responses)
    standard = score_item(item_with(category="standard"), responses)
    assert hardening["numbers_ok"] is False and hardening["numbers_checked"] is True
    # The offender is still recorded for the older categories, just not scored.
    assert standard["numbers_ok"] is True and standard["unsupported_numbers"] == ["9999"]


def test_an_item_can_opt_out_of_the_numbers_check():
    assert numbers_checked(item_with(check_numbers=False)) is False
    assert numbers_checked(item_with(category="standard", check_numbers=True)) is True


# ---------------------------------------------------------------- golden.json


def test_parse_ids_reads_a_comma_separated_list():
    """`--ids 56,57,58` re-runs three items instead of the whole fifty-four."""
    assert parse_ids("56,57,58") == {56, 57, 58}
    assert parse_ids(" 56 , 57 ,") == {56, 57}
    assert parse_ids("7") == {7}
    # No flag at all means "no id filter", which is not the same as an empty set.
    assert parse_ids(None) is None


def test_parse_ids_complains_instead_of_silently_running_everything():
    with pytest.raises(ValueError):
        parse_ids(",")
    with pytest.raises(ValueError):
        parse_ids("56,x")


def test_the_ids_the_red_team_added_are_all_in_the_golden_file():
    ids = {item["id"] for item in json.loads(GOLDEN.read_text())}
    assert parse_ids("56,57,58") <= ids


def test_golden_items_are_well_formed():
    items = json.loads(GOLDEN.read_text())
    seen = set()
    for item in items:
        assert item["id"] not in seen, f"duplicate id {item['id']}"
        seen.add(item["id"])
        assert item["intent"] in INTENTS, item
        assert item["expect"] in ("tool", "rag", "none"), item
        assert item["split"] in ("dev", "holdout"), item
        assert item["category"] in CATEGORIES, item
        assert item["expected_answer"], item
        assert turns_of(item)[0] == item["question"], item
        for phrase in (item.get("must_not_contain") or []) + (item.get("must_contain_any") or []):
            assert phrase == phrase.strip() and phrase, item


def test_golden_tool_names_all_exist():
    from app.tools.registry import TOOLS

    for item in json.loads(GOLDEN.read_text()):
        for name in expected_tools(item):
            assert name in TOOLS, f"item {item['id']} names unknown tool {name}"


def test_golden_covers_every_category_and_both_splits():
    items = json.loads(GOLDEN.read_text())
    by_category = {c: [i for i in items if category_of(i) == c] for c in CATEGORIES}
    assert all(by_category[c] for c in CATEGORIES)
    assert {i["split"] for i in items} == {"dev", "holdout"}
    # `multi_turn` items always send more than one message; `hardening` may (its
    # group 6 is multi-turn) and so may `production` — four of those ten are
    # reports whose research phrasing carries no address, so turn 1 is the
    # resident's own words and turn 2 supplies the location the tool requires.
    # Nothing else sends more than one message.
    for item in items:
        if item["category"] == "multi_turn":
            assert len(turns_of(item)) > 1, item["id"]
        elif item["category"] not in ("hardening", "production"):
            assert len(turns_of(item)) == 1, item["id"]
