"""One whole turn through stream_chat, with the model and the database faked.

Proves the two contracts M12 rests on: the events arrive in the right order, and
the `done` body is the same object /api/chat returns, because handle_chat is
nothing but a consumer of this generator. Depends on: monkeypatching the five
names app.agents.chat calls out to (intake, history, classify, retrieve,
persist) plus chat_stream and dispatch, so no LLM and no Postgres are involved.
"""

from dataclasses import dataclass, field
from typing import Any

import pytest

from app.agents import chat as chat_module
from app.llm.router import Classification


@dataclass
class FakeResult:
    """The LLMResult fields the tool loop reads."""

    text: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    raw_message: dict[str, Any] = field(default_factory=lambda: {"role": "assistant"})


def stream_of(rounds: list[FakeResult]):
    """A chat_stream stand-in: text a word at a time, then the result."""

    calls = {"n": 0}

    async def fake_chat_stream(tier, messages, tools=None):
        result = rounds[min(calls["n"], len(rounds) - 1)]
        calls["n"] += 1
        if not result.tool_calls:
            for word in result.text.split(" "):
                yield word + " "
        yield result

    return fake_chat_stream


@pytest.fixture
def wired(monkeypatch):
    """Cut every edge of the orchestrator except the part M12 changed."""

    async def no_intake(session, session_id, message, document_ids):
        return None

    async def no_history(session, session_id):
        return []

    async def classify(message, recent):
        return Classification(intent="trash", confidence=0.9, complexity="low")

    async def no_hits(session, message, topic):
        return []

    async def persist(session, session_id, message, reply, trace_row):
        return 42

    async def dispatch(name, arguments, session):
        return {"summary": "trash and organics every Wednesday", "source": "seed"}

    monkeypatch.setattr(chat_module, "handle_intake_turn", no_intake)
    monkeypatch.setattr(chat_module, "_history", no_history)
    monkeypatch.setattr(chat_module.llm_router, "classify", classify)
    monkeypatch.setattr(chat_module, "retrieve", no_hits)
    monkeypatch.setattr(chat_module, "_persist", persist)
    monkeypatch.setattr(chat_module, "dispatch", dispatch)
    return monkeypatch


def tool_call(name: str, **arguments) -> dict:
    return {"id": f"call_{name}", "name": name, "arguments": arguments}


ANSWER = "Trash is collected every Wednesday."
ONE_TOOL_TURN = [
    FakeResult("", [tool_call("get_trash_schedule", address="4521 Adams Ave")]),
    FakeResult(ANSWER),
]


async def events_for(monkeypatch, rounds: list[FakeResult]) -> list[dict]:
    monkeypatch.setattr(chat_module, "chat_stream", stream_of(rounds))
    return [e async for e in chat_module.stream_chat(None, "s1", "when is trash day?")]


async def test_the_event_order_is_status_tool_tokens_done(wired):
    events = await events_for(wired, ONE_TOOL_TURN)

    assert [e["type"] for e in events][0] == "status"
    assert events[0]["intent"] == "trash"
    assert events[0]["tier"] == "smart"
    assert events[0]["model"], "the UI labels the bubble with the model, so it must be sent"

    assert events[1] == {"type": "tool", "name": "get_trash_schedule", "cached": False}
    assert [e["type"] for e in events[2:-1]] == ["token"] * (len(events) - 3)
    assert "".join(e["text"] for e in events[2:-1]).strip() == ANSWER
    assert events[-1]["type"] == "done"


async def test_the_done_body_is_the_answer_with_its_trace(wired):
    events = await events_for(wired, ONE_TOOL_TURN)
    done = events[-1]

    assert done["reply"] == ANSWER
    assert done["trace"]["id"] == 42
    assert done["trace"]["intent"] == "trash"
    assert [t["name"] for t in done["trace"]["tool_calls"]] == ["get_trash_schedule"]
    assert done["trace"]["error"] is None


async def test_the_done_body_equals_the_buffered_body(wired):
    """handle_chat must not be able to answer differently from the stream."""
    done = (await events_for(wired, ONE_TOOL_TURN))[-1]

    wired.setattr(chat_module, "chat_stream", stream_of(ONE_TOOL_TURN))
    buffered = await chat_module.handle_chat(None, "s1", "when is trash day?")

    streamed_body = {k: v for k, v in done.items() if k != "type"}
    # Wall-clock latency is the one field two runs cannot share.
    streamed_body["trace"] = dict(streamed_body["trace"], latency_ms=0)
    buffered_body = buffered.model_dump()
    buffered_body["trace"] = dict(buffered_body["trace"], latency_ms=0)

    assert streamed_body == buffered_body


async def test_a_failed_turn_still_ends_in_done(wired):
    async def explode(message, recent):
        raise RuntimeError("classifier is down")

    wired.setattr(chat_module.llm_router, "classify", explode)
    events = await events_for(wired, ONE_TOOL_TURN)

    assert [e["type"] for e in events] == ["done"]
    assert events[0]["reply"] == chat_module.FALLBACK_REPLY
    assert "classifier is down" in events[0]["trace"]["error"]
    assert events[0]["citations"] == []


async def test_a_workflow_turn_yields_only_done(wired):
    """An upload is templated, not generated: there is nothing to stream."""

    async def intake(session, session_id, message, document_ids):
        return {
            "reply": "Filed as PRM-2026-000123.",
            "citations": [],
            "actions": [{"action": "application_created", "tracking_number": "PRM-2026-000123"}],
            "trace": {"intent": "permits", "tier": "extract"},
        }

    wired.setattr(chat_module, "handle_intake_turn", intake)
    events = await events_for(wired, ONE_TOOL_TURN)

    assert [e["type"] for e in events] == ["done"]
    assert events[0]["reply"] == "Filed as PRM-2026-000123."
    assert events[0]["trace"]["id"] == 42
