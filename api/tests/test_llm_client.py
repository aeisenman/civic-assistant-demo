"""LLM client tests with a faked HTTP transport — no network, no Ollama.

The openai SDK accepts a custom httpx client, so httpx.MockTransport returns
canned OpenAI-shaped responses. Covers LLMResult fields, tool-call parsing,
cost math, TraceCollector capture, chat_json validation+retry, embed batching.
"""

import json

import httpx
import pytest
from openai import AsyncOpenAI
from pydantic import BaseModel

from app.config import settings
from app.llm import client as llm

# ------------------------------------------------------------------ fixtures


def _completion(content="hello", tool_calls=None, prompt=10, completion=5):
    message = {"role": "assistant", "content": content}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return {
        "id": "chatcmpl-1",
        "object": "chat.completion",
        "created": 0,
        "model": "test-model",
        "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
        "usage": {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": prompt + completion,
        },
    }


def fake_client(handler) -> AsyncOpenAI:
    """An AsyncOpenAI whose transport is a function, not a socket."""
    return AsyncOpenAI(
        base_url="http://fake/v1",
        api_key="test",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


@pytest.fixture(autouse=True)
def deterministic_models(monkeypatch):
    monkeypatch.setattr(settings, "llm_model_small", "small-m")
    monkeypatch.setattr(settings, "llm_model_smart", "smart-m")
    monkeypatch.setattr(settings, "llm_prices_json", {})
    monkeypatch.setattr(settings, "embed_model", "embed-m")
    monkeypatch.setattr(settings, "embed_dim", 4)


@pytest.fixture(autouse=True)
def clean_trace():
    token = llm.set_trace(None)
    yield
    llm.reset_trace(token)


# ---------------------------------------------------------------------- chat


async def test_chat_returns_populated_result():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        seen["url"] = str(request.url)
        return httpx.Response(200, json=_completion("Trash day is Monday."))

    result = await llm.chat(
        llm.Tier.SMART,
        [{"role": "user", "content": "when is trash day"}],
        client=fake_client(handler),
    )

    assert seen["url"].endswith("/chat/completions")
    assert seen["body"]["model"] == "smart-m"  # tier -> model, not hard-coded
    assert result.text == "Trash day is Monday."
    assert result.model == "smart-m"
    assert (result.prompt_tokens, result.completion_tokens) == (10, 5)
    assert result.latency_ms >= 0
    assert result.tool_calls == []
    assert result.raw_message == {"role": "assistant", "content": "Trash day is Monday."}


async def test_chat_parses_tool_calls_and_keeps_raw_message():
    tool_calls = [
        {
            "id": "call_1",
            "type": "function",
            "function": {
                "name": "get_trash_schedule",
                "arguments": '{"address": "4521 Adams Ave"}',
            },
        }
    ]

    def handler(request):
        return httpx.Response(200, json=_completion(None, tool_calls=tool_calls))

    result = await llm.chat(
        llm.Tier.SMART,
        [{"role": "user", "content": "trash"}],
        tools=[{"type": "function", "function": {"name": "get_trash_schedule"}}],
        client=fake_client(handler),
    )

    assert result.tool_calls == [
        {"id": "call_1", "name": "get_trash_schedule", "arguments": {"address": "4521 Adams Ave"}}
    ]
    # raw_message must be replayable straight back into `messages`.
    assert result.raw_message["tool_calls"][0]["function"]["name"] == "get_trash_schedule"


async def test_malformed_tool_arguments_do_not_crash():
    tool_calls = [{"id": "c1", "type": "function", "function": {"name": "t", "arguments": "{not json"}}]

    def handler(request):
        return httpx.Response(200, json=_completion(None, tool_calls=tool_calls))

    result = await llm.chat(llm.Tier.SMALL, [], client=fake_client(handler))
    assert result.tool_calls[0]["arguments"] == {"_raw": "{not json"}


# ---------------------------------------------------------------------- cost


def test_cost_is_zero_without_prices():
    assert llm.estimate_cost("small-m", 1000, 1000) == 0.0


def test_cost_math(monkeypatch):
    monkeypatch.setattr(
        settings,
        "llm_prices_json",
        {"smart-m": {"input_per_1m": 3.0, "output_per_1m": 15.0}},
    )
    # 1M in + 1M out = $3 + $15
    assert llm.estimate_cost("smart-m", 1_000_000, 1_000_000) == 18.0
    # 1000 in + 500 out = 0.003 + 0.0075
    assert llm.estimate_cost("smart-m", 1000, 500) == 0.0105


async def test_chat_prices_the_call(monkeypatch):
    monkeypatch.setattr(
        settings,
        "llm_prices_json",
        {"smart-m": {"input_per_1m": 1000.0, "output_per_1m": 2000.0}},
    )

    def handler(request):
        return httpx.Response(200, json=_completion(prompt=1000, completion=1000))

    result = await llm.chat(llm.Tier.SMART, [], client=fake_client(handler))
    assert result.cost_usd == pytest.approx(1.0 + 2.0)


# ------------------------------------------------------------------- tracing


async def test_trace_collector_captures_every_call(monkeypatch):
    monkeypatch.setattr(
        settings, "llm_prices_json", {"small-m": {"input_per_1m": 1000.0, "output_per_1m": 0.0}}
    )
    tool_calls = [{"id": "c1", "type": "function", "function": {"name": "get_referral", "arguments": "{}"}}]

    def handler(request):
        return httpx.Response(200, json=_completion("x", tool_calls=tool_calls, prompt=1000))

    collector = llm.TraceCollector()
    token = llm.set_trace(collector)
    try:
        await llm.chat(llm.Tier.SMALL, [], client=fake_client(handler))
        await llm.chat(llm.Tier.SMALL, [], client=fake_client(handler))
    finally:
        llm.reset_trace(token)

    assert len(collector.calls) == 2
    first = collector.calls[0]
    assert first["tier"] == "small"
    assert first["model"] == "small-m"
    assert first["tool_call_names"] == ["get_referral"]
    assert collector.totals["calls"] == 2
    assert collector.totals["prompt_tokens"] == 2000
    assert collector.totals["cost_usd"] == pytest.approx(2.0)


async def test_calls_outside_a_collector_are_not_recorded():
    def handler(request):
        return httpx.Response(200, json=_completion())

    await llm.chat(llm.Tier.SMALL, [], client=fake_client(handler))
    assert llm.current_trace() is None  # no collector, no crash


# ----------------------------------------------------------------- chat_json


class Classification(BaseModel):
    intent: str
    confidence: float


async def test_chat_json_validates():
    def handler(request):
        body = json.loads(request.content)
        assert body["response_format"]["json_schema"]["name"] == "Classification"
        return httpx.Response(200, json=_completion('{"intent": "trash", "confidence": 0.9}'))

    parsed = await llm.chat_json(
        llm.Tier.SMALL,
        [{"role": "user", "content": "bin day?"}],
        Classification,
        client=fake_client(handler),
    )
    assert parsed.intent == "trash"


async def test_chat_json_retries_once_then_succeeds():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(200, json=_completion('{"intent": "trash"}'))  # missing field
        return httpx.Response(200, json=_completion('{"intent": "trash", "confidence": 0.5}'))

    parsed = await llm.chat_json(llm.Tier.SMALL, [], Classification, client=fake_client(handler))
    assert calls["n"] == 2
    assert parsed.confidence == 0.5


async def test_chat_json_gives_up_after_two_attempts():
    def handler(request):
        return httpx.Response(200, json=_completion('{"nope": 1}'))

    with pytest.raises(ValueError, match="Classification"):
        await llm.chat_json(llm.Tier.SMALL, [], Classification, client=fake_client(handler))


# --------------------------------------------------------------------- embed


async def test_embed_batches_by_32_and_preserves_order():
    requests: list[list[str]] = []

    def handler(request):
        body = json.loads(request.content)
        requests.append(body["input"])
        data = [
            {"object": "embedding", "index": i, "embedding": [float(i), 0.0, 0.0, 0.0]}
            for i in range(len(body["input"]))
        ]
        return httpx.Response(
            200,
            json={
                "object": "list",
                "data": data,
                "model": "embed-m",
                "usage": {"prompt_tokens": 1, "total_tokens": 1},
            },
        )

    texts = [f"chunk {i}" for i in range(40)]
    vectors = await llm.embed(texts, client=fake_client(handler))

    assert len(requests) == 2 and len(requests[0]) == 32 and len(requests[1]) == 8
    assert len(vectors) == 40
    assert len(vectors[0]) == settings.embed_dim
    assert vectors[32][0] == 0.0  # second batch restarts its index


async def test_embed_empty_input_makes_no_request():
    def handler(request):  # pragma: no cover - must never run
        raise AssertionError("no HTTP call expected")

    assert await llm.embed([], client=fake_client(handler)) == []
