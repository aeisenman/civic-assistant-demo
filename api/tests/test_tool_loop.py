"""The chat tool loop: duplicate calls are served from cache, and rounds are capped.

Drives app.agents.chat._tool_loop with a scripted model and a counting dispatch,
so no LLM and no database are involved. Depends on: monkeypatching the two names
the loop calls (`chat_stream` and `dispatch`) inside the app.agents.chat module.
Since M12 the loop is an async generator, so `drain` collects its events and
returns the (reply, calls, sources) the pre-streaming loop used to return.
"""

from dataclasses import dataclass, field
from typing import Any

import pytest

from app.agents import chat as chat_module
from app.agents.chat import MAX_TOOL_ROUNDS, _call_key, _tool_loop


@dataclass
class FakeResult:
    """The three attributes _tool_loop reads off an LLMResult."""

    text: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    raw_message: dict[str, Any] = field(default_factory=lambda: {"role": "assistant"})


def call(name: str, **arguments) -> dict:
    return {"id": f"call_{name}_{len(arguments)}", "name": name, "arguments": arguments}


@pytest.fixture
def spy(monkeypatch):
    """Record every dispatch; the loop must not reach the real tools."""
    dispatched: list[tuple[str, dict]] = []

    async def fake_dispatch(name, arguments, session):
        dispatched.append((name, arguments))
        return {"summary": f"{name} ran {len(dispatched)}"}

    monkeypatch.setattr(chat_module, "dispatch", fake_dispatch)
    return dispatched


def script(monkeypatch, rounds: list[FakeResult]):
    """Make the model return `rounds` in order, repeating the last one forever.

    Streamed: each round yields its text one word at a time, then the result,
    which is the contract chat_stream has with the loop.
    """
    seen: list[int] = []

    async def fake_chat_stream(tier, messages, tools=None):
        seen.append(len(seen))
        result = rounds[min(len(seen) - 1, len(rounds) - 1)]
        if not result.tool_calls:
            for word in result.text.split(" "):
                yield word + " "
        yield result

    monkeypatch.setattr(chat_module, "chat_stream", fake_chat_stream)
    return seen


async def drain(*args, **kwargs) -> tuple[str, list[dict], list[dict]]:
    """Run the loop to its private `_end` event and return what it carried."""
    reply, calls, sources = "", [], []
    async for event in _tool_loop(*args, **kwargs):
        if event["type"] == "_end":
            reply, calls, sources = event["reply"], event["calls"], event["tool_sources"]
    return reply, calls, sources


async def events_of(*args, **kwargs) -> list[dict]:
    """Every public event the loop emits, in order."""
    return [e async for e in _tool_loop(*args, **kwargs) if e["type"] != "_end"]


async def test_a_repeated_call_is_served_from_cache(monkeypatch, spy):
    same = call("get_trash_schedule", address="4521 Adams Ave")
    script(
        monkeypatch,
        [
            FakeResult("", [same]),
            FakeResult("", [dict(same, id="call_again")]),
            FakeResult("Your trash day is Wednesday."),
        ],
    )
    reply, calls, _sources = await drain(None, "smart", [], [])

    assert reply == "Your trash day is Wednesday."
    assert len(spy) == 1, "the second identical call must not re-execute the tool"
    assert [c["cached"] for c in calls] == [False, True]
    # The model still gets an answer for the duplicate — the first one.
    assert calls[0]["result_summary"] == calls[1]["result_summary"]


async def test_the_same_tool_with_different_arguments_runs_again(monkeypatch, spy):
    script(
        monkeypatch,
        [
            FakeResult(
                "",
                [
                    call("get_trash_schedule", address="4521 Adams Ave"),
                    call("get_trash_schedule", address="7890 Girard Ave"),
                ],
            ),
            FakeResult("done"),
        ],
    )
    _, calls, _sources = await drain(None, "smart", [], [])
    assert len(spy) == 2
    assert [c["cached"] for c in calls] == [False, False]


async def test_the_loop_stops_at_the_round_cap(monkeypatch, spy):
    # A model that never stops asking must not loop forever.
    seen = script(monkeypatch, [FakeResult("", [call("search_events", query="fair")])])
    await drain(None, "smart", [], [])
    assert len(seen) == MAX_TOOL_ROUNDS
    # Every round after the first repeats the same call, so only one dispatch runs.
    assert len(spy) == 1


async def test_every_tool_result_is_appended_for_the_model(monkeypatch, spy):
    same = call("get_referral", topic="dog license")
    script(monkeypatch, [FakeResult("", [same, same]), FakeResult("done")])
    messages: list[dict] = []
    await drain(None, "smart", messages, [])
    # One assistant message plus a tool message per call — a call left without a
    # tool reply is a protocol error at the provider, cached or not.
    assert [m.get("role") for m in messages] == ["assistant", "tool", "tool"]


def test_call_key_ignores_argument_order():
    assert _call_key("t", {"a": 1, "b": 2}) == _call_key("t", {"b": 2, "a": 1})
    assert _call_key("t", {"a": 1}) != _call_key("t", {"a": 2})
    assert _call_key("t", None) == _call_key("t", {})


async def test_tool_sources_are_numbered_after_the_retrieved_chunks(monkeypatch):
    """A page fetched by search_city_website becomes a citable [n] like a KB chunk."""

    async def fake_dispatch(name, arguments, session):
        return {
            "summary": "fetched",
            "sources": [
                {
                    "title": "Library cards",
                    "url": "https://www.sandiego.gov/card",
                    "text": "Bring ID",
                }
            ],
        }

    monkeypatch.setattr(chat_module, "dispatch", fake_dispatch)
    script(
        monkeypatch,
        [FakeResult("", [call("search_city_website", query="library card")]), FakeResult("[3]")],
    )
    messages: list[dict] = []
    # offset=2: two retrieved KB chunks already own [1] and [2] in the prompt.
    _, _calls, sources = await drain(None, "smart", messages, [], offset=2)
    assert [s["url"] for s in sources] == ["https://www.sandiego.gov/card"]
    tool_message = messages[-1]["content"]
    assert "These pages are now sources [3]" in tool_message
    assert "[3] Library cards (https://www.sandiego.gov/card)" in tool_message


async def test_a_cached_search_does_not_add_its_source_twice(monkeypatch):
    async def fake_dispatch(name, arguments, session):
        return {"summary": "fetched", "sources": [{"title": "A", "url": "https://sandiego.gov/a"}]}

    monkeypatch.setattr(chat_module, "dispatch", fake_dispatch)
    same = call("search_city_website", query="library card")
    script(monkeypatch, [FakeResult("", [same, same]), FakeResult("done")])
    _, _calls, sources = await drain(None, "smart", [], [])
    assert len(sources) == 1


async def test_the_answer_is_streamed_and_each_tool_call_announced(monkeypatch, spy):
    """The resident sees a tool event per call, then the answer word by word."""
    script(
        monkeypatch,
        [
            FakeResult("", [call("get_trash_schedule", address="4521 Adams Ave")]),
            FakeResult("Wednesday, weekly."),
        ],
    )
    events = await events_of(None, "smart", [], [])

    assert events[0] == {"type": "tool", "name": "get_trash_schedule", "cached": False}
    tokens = [e["text"] for e in events if e["type"] == "token"]
    assert len(tokens) > 1, "the answer must arrive in pieces, not in one lump"
    assert "".join(tokens).strip() == "Wednesday, weekly."


async def test_a_cached_call_says_so_in_its_event(monkeypatch, spy):
    same = call("get_holiday_schedule")
    script(monkeypatch, [FakeResult("", [same, same]), FakeResult("ok")])
    events = await events_of(None, "smart", [], [])
    assert [e["cached"] for e in events if e["type"] == "tool"] == [False, True]
