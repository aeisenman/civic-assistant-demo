"""chat_stream over a faked SSE transport: deltas assemble, usage still lands.

Same trick as test_llm_client: httpx.MockTransport answers the openai SDK, this
time with a text/event-stream body, so the streaming path is exercised with no
network and no provider. Depends on: app.llm.client and the openai SDK's own
stream parser — the point is to test our accumulation, not to reimplement theirs.
"""

import json

import httpx
import pytest
from openai import AsyncOpenAI

from app.config import settings
from app.llm import client as llm


def sse(chunks: list[dict]) -> bytes:
    """The wire format an OpenAI-compatible endpoint sends for stream=True."""
    body = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks)
    return (body + "data: [DONE]\n\n").encode()


def chunk(delta: dict, usage: dict | None = None) -> dict:
    out = {
        "id": "chatcmpl-1",
        "object": "chat.completion.chunk",
        "created": 0,
        "model": "test-model",
        "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
    }
    if usage is not None:
        out["usage"] = usage
    return out


def usage_chunk(prompt: int, completion: int) -> dict:
    """The last chunk when stream_options.include_usage is on: usage, no choices."""
    return {
        "id": "chatcmpl-1",
        "object": "chat.completion.chunk",
        "created": 0,
        "model": "test-model",
        "choices": [],
        "usage": {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": prompt + completion,
        },
    }


def streaming_client(chunks: list[dict], seen: list[dict] | None = None) -> AsyncOpenAI:
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(json.loads(request.content))
        return httpx.Response(200, content=sse(chunks), headers={"content-type": "text/event-stream"})

    return AsyncOpenAI(
        base_url="http://fake/v1",
        api_key="test",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


async def collect(stream) -> tuple[list[str], llm.LLMResult]:
    """Split a chat_stream into its text deltas and its final LLMResult."""
    deltas: list[str] = []
    result: llm.LLMResult | None = None
    async for item in stream:
        if isinstance(item, str):
            deltas.append(item)
        else:
            result = item
    assert result is not None, "chat_stream must always end with an LLMResult"
    return deltas, result


@pytest.fixture(autouse=True)
def deterministic_models(monkeypatch):
    monkeypatch.setattr(settings, "llm_model_smart", "smart-m")
    monkeypatch.setattr(settings, "llm_prices_json", {})


@pytest.fixture(autouse=True)
def clean_trace():
    token = llm.set_trace(None)
    yield
    llm.reset_trace(token)


@pytest.fixture(autouse=True)
def forget_stream_options():
    """The downgrade set is module state; a test must not leak into the next."""
    llm._no_stream_options.clear()
    yield
    llm._no_stream_options.clear()


# --------------------------------------------------------------------- deltas


async def test_text_deltas_are_yielded_and_assembled():
    client = streaming_client(
        [
            chunk({"role": "assistant", "content": "Trash "}),
            chunk({"content": "is on "}),
            chunk({"content": "Wednesday."}),
            usage_chunk(120, 8),
        ]
    )
    deltas, result = await collect(llm.chat_stream(llm.Tier.SMART, [], client=client))

    assert deltas == ["Trash ", "is on ", "Wednesday."]
    assert result.text == "Trash is on Wednesday."
    assert result.raw_message == {"role": "assistant", "content": "Trash is on Wednesday."}
    assert result.model == "smart-m"


async def test_usage_from_the_final_chunk_lands_in_the_result_and_the_trace(monkeypatch):
    monkeypatch.setattr(settings, "llm_prices_json", {"smart-m": {"input_per_1m": 1.0, "output_per_1m": 2.0}})
    collector = llm.TraceCollector()
    token = llm.set_trace(collector)
    client = streaming_client([chunk({"content": "hi"}), usage_chunk(1_000_000, 500_000)])
    try:
        _deltas, result = await collect(llm.chat_stream(llm.Tier.SMART, [], client=client))
    finally:
        llm.reset_trace(token)

    assert (result.prompt_tokens, result.completion_tokens) == (1_000_000, 500_000)
    assert result.cost_usd == 2.0  # $1 of input + $1 of output
    assert collector.totals["prompt_tokens"] == 1_000_000
    assert collector.calls[0]["tier"] == "smart"
    assert collector.calls[0]["model"] == "smart-m"


async def test_include_usage_is_requested():
    seen: list[dict] = []
    client = streaming_client([chunk({"content": "hi"}), usage_chunk(1, 1)], seen)
    await collect(llm.chat_stream(llm.Tier.SMART, [], client=client))
    assert seen[0]["stream"] is True
    assert seen[0]["stream_options"] == {"include_usage": True}


async def test_a_stream_without_usage_still_answers():
    """Ollama-shaped: no usage chunk at all. The answer matters more than the count."""
    client = streaming_client([chunk({"content": "hello"})])
    deltas, result = await collect(llm.chat_stream(llm.Tier.SMART, [], client=client))
    assert deltas == ["hello"]
    assert (result.prompt_tokens, result.completion_tokens, result.cost_usd) == (0, 0, 0.0)


# ---------------------------------------------------------------- tool calls


def tool_delta(index: int, *, id: str = "", name: str = "", arguments: str = "") -> dict:
    function: dict = {}
    if name:
        function["name"] = name
    if arguments:
        function["arguments"] = arguments
    call: dict = {"index": index, "type": "function", "function": function}
    if id:
        call["id"] = id
    return {"tool_calls": [call]}


async def test_tool_call_deltas_are_accumulated_into_one_call():
    client = streaming_client(
        [
            chunk(tool_delta(0, id="call_1", name="get_trash_schedule")),
            chunk(tool_delta(0, arguments='{"address":')),
            chunk(tool_delta(0, arguments='"4521 Adams Ave"}')),
            usage_chunk(50, 20),
        ]
    )
    deltas, result = await collect(llm.chat_stream(llm.Tier.SMART, [], client=client))

    assert deltas == []
    assert result.tool_calls == [
        {
            "id": "call_1",
            "name": "get_trash_schedule",
            "arguments": {"address": "4521 Adams Ave"},
        }
    ]
    # The raw form goes straight back onto `messages`, so it keeps the JSON string.
    assert result.raw_message["tool_calls"][0]["function"] == {
        "name": "get_trash_schedule",
        "arguments": '{"address":"4521 Adams Ave"}',
    }


async def test_two_parallel_tool_calls_stay_separate():
    client = streaming_client(
        [
            chunk(tool_delta(0, id="a", name="get_trash_schedule", arguments="{}")),
            chunk(tool_delta(1, id="b", name="get_holiday_schedule", arguments="{}")),
        ]
    )
    _deltas, result = await collect(llm.chat_stream(llm.Tier.SMART, [], client=client))
    assert [c["name"] for c in result.tool_calls] == [
        "get_trash_schedule",
        "get_holiday_schedule",
    ]


async def test_text_alongside_a_tool_call_is_not_yielded_to_the_resident():
    """A preamble before a tool call is not the answer; it must not reach the UI."""
    client = streaming_client(
        [
            chunk({"content": "Let me look "}),
            chunk(tool_delta(0, id="a", name="get_trash_schedule", arguments="{}")),
            chunk({"content": "that up."}),
        ]
    )
    deltas, result = await collect(llm.chat_stream(llm.Tier.SMART, [], client=client))

    assert deltas == ["Let me look "], "only text before the first tool delta escapes"
    # Nothing is lost for the trace or for the message we append.
    assert result.text == "Let me look that up."


async def test_malformed_streamed_arguments_do_not_crash():
    client = streaming_client([chunk(tool_delta(0, id="a", name="t", arguments="{not json"))])
    _deltas, result = await collect(llm.chat_stream(llm.Tier.SMART, [], client=client))
    assert result.tool_calls[0]["arguments"] == {"_raw": "{not json"}


# ------------------------------------------------------- provider downgrades


async def test_an_endpoint_that_rejects_stream_options_is_retried_without_it():
    seen: list[dict] = []
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        attempts["n"] += 1
        if attempts["n"] == 1:
            return httpx.Response(
                400,
                json={"error": {"message": "stream_options is not supported"}},
                headers={"content-type": "application/json"},
            )
        return httpx.Response(
            200,
            content=sse([chunk({"content": "ok"})]),
            headers={"content-type": "text/event-stream"},
        )

    client = AsyncOpenAI(
        base_url="http://fake/v1",
        api_key="test",
        max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    deltas, _result = await collect(llm.chat_stream(llm.Tier.SMART, [], client=client))

    assert deltas == ["ok"]
    assert "stream_options" in seen[0] and "stream_options" not in seen[1]
    # And the model is remembered, so the next call does not pay for the 400 again.
    assert "smart-m" in llm._no_stream_options
