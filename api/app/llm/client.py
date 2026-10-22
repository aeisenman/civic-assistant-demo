"""The only module in the codebase that talks to a model.

Everything (classifier, router, agents, extraction, RAG embedding) calls chat(),
chat_stream(), chat_json() or embed() here, so every call is tiered, priced and
traced in one place. Depends on: the `openai` SDK pointed at LLM_BASE_URL, so
Ollama, OpenAI and Bedrock-behind-LiteLLM are an env swap.
"""

import contextvars
import json
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import httpx
from openai import AsyncOpenAI, BadRequestError
from pydantic import BaseModel, ValidationError

from app.config import settings

log = logging.getLogger(__name__)

EMBED_BATCH = 32


class Tier(str, Enum):  # noqa: UP042 - StrEnum changes str(Tier.SMALL); the alias names are sent to the provider
    """Logical roles, not model names. PLAN.md §4 maps them per provider."""

    SMALL = "small"  # classification, extraction, JSON-only tasks
    SMART = "smart"  # resident-facing answers with tools + RAG
    ESCALATE = "escalate"  # low-confidence / complex / multi-intent turns
    EXTRACT = "extract"  # long-document extraction


@dataclass
class LLMResult:
    """One completion, plus everything the trace drawer needs to explain it."""

    text: str
    tool_calls: list[dict[str, Any]]
    model: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int
    cost_usd: float
    raw_message: dict[str, Any]  # append straight back onto `messages`


@dataclass
class TraceCollector:
    """Per-request record of every model call, activated with `use()`.

    M2 persists these into the `traces` table; M1 just proves capture works.
    """

    calls: list[dict[str, Any]] = field(default_factory=list)

    def add(self, entry: dict[str, Any]) -> None:
        """Record one model call; the trace row is also the spend ledger."""
        self.calls.append(entry)

    @property
    def totals(self) -> dict[str, float | int]:
        """Turn-level tokens, latency and cost, summed over every call in the turn."""
        return {
            "calls": len(self.calls),
            "prompt_tokens": sum(c["prompt_tokens"] for c in self.calls),
            "completion_tokens": sum(c["completion_tokens"] for c in self.calls),
            "latency_ms": sum(c["latency_ms"] for c in self.calls),
            "cost_usd": round(sum(c["cost_usd"] for c in self.calls), 6),
        }


_current_trace: contextvars.ContextVar[TraceCollector | None] = contextvars.ContextVar(
    "llm_trace", default=None
)


def set_trace(collector: TraceCollector | None) -> contextvars.Token:
    """Make `collector` the active one for this task; pass the token to reset."""
    return _current_trace.set(collector)


def reset_trace(token: contextvars.Token) -> None:
    """Undo set_trace, so a collector cannot leak into the next request."""
    _current_trace.reset(token)


def current_trace() -> TraceCollector | None:
    """The collector for this task, or None when nothing is being traced."""
    return _current_trace.get()


# --------------------------------------------------------------------------- clients
# Module-level singletons; tests inject a fake by passing `client=` to chat().
_chat_client: AsyncOpenAI | None = None
_embed_client: AsyncOpenAI | None = None


def client_timeout() -> httpx.Timeout:
    """The read/connect budget for every model call.

    The SDK default is a 600-second read timeout with two retries, so one hung
    provider could hold a stream — and the database session it carries — for
    half an hour (audit row 1). LLM_TIMEOUT_S is the ceiling instead; connect is
    short because a gateway that will not accept a socket is already down.
    """
    return httpx.Timeout(settings.llm_timeout_s, connect=5.0)


def chat_client() -> AsyncOpenAI:
    """The shared chat client, built once: a new one per turn would re-pool sockets."""
    global _chat_client
    if _chat_client is None:
        _chat_client = AsyncOpenAI(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            timeout=client_timeout(),
            # One retry, not two: a resident waiting on a stream would rather
            # have the fallback reply than three full timeouts of silence.
            max_retries=1,
        )
    return _chat_client


def embed_client() -> AsyncOpenAI:
    """The shared embeddings client; separate base URL so a provider can split them."""
    global _embed_client
    if _embed_client is None:
        _embed_client = AsyncOpenAI(
            base_url=settings.embed_base_url,
            api_key=settings.embed_api_key,
            timeout=client_timeout(),
            max_retries=1,
        )
    return _embed_client


def model_for(tier: Tier) -> str:
    """The model id behind a tier alias. Never hard-code a name; ask config."""
    return settings.model_for_tier(tier.value)


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """USD from LLM_PRICES_JSON. Unknown model (or Ollama) costs $0."""
    price = settings.llm_prices_json.get(model)
    if not price:
        return 0.0
    return round(
        prompt_tokens / 1_000_000 * price.get("input_per_1m", 0.0)
        + completion_tokens / 1_000_000 * price.get("output_per_1m", 0.0),
        6,
    )


def _parse_tool_calls(message: Any) -> list[dict[str, Any]]:
    """Normalise SDK tool calls to {id, name, arguments(dict)}."""
    out: list[dict[str, Any]] = []
    for call in getattr(message, "tool_calls", None) or []:
        try:
            args = json.loads(call.function.arguments or "{}")
        except json.JSONDecodeError:
            # Small models occasionally emit malformed JSON; the caller decides.
            args = {"_raw": call.function.arguments}
        out.append({"id": call.id, "name": call.function.name, "arguments": args})
    return out


def _record_call(
    tier: Tier,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    latency_ms: int,
    tool_calls: list[dict[str, Any]],
    cost: float,
) -> None:
    """Append one completion to the active trace and log it.

    Shared by chat() and chat_stream() so a streamed turn and a buffered turn
    produce byte-identical trace rows — the trace drawer must not be able to
    tell which path answered.
    """
    collector = current_trace()
    if collector is not None:
        collector.add(
            {
                "tier": tier.value,
                "model": model,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "latency_ms": latency_ms,
                "cost_usd": cost,
                "tool_call_names": [c["name"] for c in tool_calls],
            }
        )
    log.info(
        "llm tier=%s model=%s tokens=%d/%d latency=%dms cost=$%.6f",
        tier.value,
        model,
        prompt_tokens,
        completion_tokens,
        latency_ms,
        cost,
    )


async def chat(
    tier: Tier,
    messages: list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]] | None = None,
    response_format: dict[str, Any] | None = None,
    temperature: float = 0.2,
    max_tokens: int = 1024,
    client: AsyncOpenAI | None = None,
) -> LLMResult:
    """One chat completion at `tier`, timed, priced and appended to the trace."""
    model = model_for(tier)
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if tools:
        kwargs["tools"] = tools
    if response_format:
        kwargs["response_format"] = response_format

    started = time.perf_counter()
    completion = await (client or chat_client()).chat.completions.create(**kwargs)
    latency_ms = int((time.perf_counter() - started) * 1000)

    message = completion.choices[0].message
    tool_calls = _parse_tool_calls(message)
    usage = getattr(completion, "usage", None)
    prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
    completion_tokens = getattr(usage, "completion_tokens", 0) or 0
    cost = estimate_cost(model, prompt_tokens, completion_tokens)

    # The assistant message in plain-dict form, ready to append to `messages`.
    raw_message: dict[str, Any] = {"role": "assistant", "content": message.content or ""}
    if getattr(message, "tool_calls", None):
        raw_message["tool_calls"] = [
            {
                "id": c.id,
                "type": "function",
                "function": {"name": c.function.name, "arguments": c.function.arguments},
            }
            for c in message.tool_calls
        ]

    result = LLMResult(
        text=message.content or "",
        tool_calls=tool_calls,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        latency_ms=latency_ms,
        cost_usd=cost,
        raw_message=raw_message,
    )

    _record_call(tier, model, prompt_tokens, completion_tokens, latency_ms, tool_calls, cost)
    return result


# Models whose endpoint rejected `stream_options`, so the next stream for them
# skips it (and reports zero tokens). Same pattern as _no_json_schema below.
_no_stream_options: set[str] = set()


def _stream_tool_calls(partial: dict[int, dict[str, str]]) -> tuple[list[dict], list[dict]]:
    """Turn accumulated tool-call deltas into (normalised calls, raw message form).

    Streamed tool calls arrive in pieces: the id and name land once, the
    arguments as a string built up over many chunks, all keyed by `index`.
    """
    calls: list[dict[str, Any]] = []
    raw: list[dict[str, Any]] = []
    for _index, slot in sorted(partial.items()):
        try:
            args = json.loads(slot["arguments"] or "{}")
        except json.JSONDecodeError:
            args = {"_raw": slot["arguments"]}
        calls.append({"id": slot["id"], "name": slot["name"], "arguments": args})
        raw.append(
            {
                "id": slot["id"],
                "type": "function",
                "function": {"name": slot["name"], "arguments": slot["arguments"]},
            }
        )
    return calls, raw


async def chat_stream(
    tier: Tier,
    messages: list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]] | None = None,
    temperature: float = 0.2,
    max_tokens: int = 1024,
    client: AsyncOpenAI | None = None,
) -> AsyncIterator[str | LLMResult]:
    """Stream one completion at `tier`: text deltas first, one LLMResult last.

    Why the mixed yield type: a Python async generator cannot `return` a value,
    and the caller needs both the tokens as they arrive and the usage/cost record
    at the end. Every `str` item is a text delta; the final item is always an
    LLMResult with exactly the fields chat() produces, so tracing, pricing and
    the `messages` append are unchanged.

    Two provider quirks are handled here. `stream_options={"include_usage": true}`
    is what makes a streamed call report tokens at all, but not every endpoint
    accepts it, so a 400 that names it downgrades this model to a plain stream
    (tokens 0) and is remembered. And a round that starts calling tools stops
    yielding: the text a model writes alongside a tool call is a preamble
    ("Let me look that up"), not the answer, and the resident must not read it.
    It is still accumulated into LLMResult.text so the trace loses nothing.
    """
    model = model_for(tier)
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
    }
    if tools:
        kwargs["tools"] = tools
    if model not in _no_stream_options:
        kwargs["stream_options"] = {"include_usage": True}

    api = client or chat_client()
    started = time.perf_counter()
    try:
        stream = await api.chat.completions.create(**kwargs)
    except BadRequestError as exc:
        if "stream_options" not in kwargs or "stream_options" not in str(exc).lower():
            raise
        log.warning("chat_stream model=%s rejected stream_options; retrying without: %s", model, exc)
        _no_stream_options.add(model)
        kwargs.pop("stream_options")
        stream = await api.chat.completions.create(**kwargs)

    text_parts: list[str] = []
    partial: dict[int, dict[str, str]] = {}
    prompt_tokens = 0
    completion_tokens = 0

    async for chunk in stream:
        usage = getattr(chunk, "usage", None)
        if usage is not None:
            # The usage-only chunk arrives last and carries no choices.
            prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
            completion_tokens = getattr(usage, "completion_tokens", 0) or 0
        choices = getattr(chunk, "choices", None) or []
        if not choices:
            continue
        delta = getattr(choices[0], "delta", None)
        if delta is None:
            continue
        for call in getattr(delta, "tool_calls", None) or []:
            slot = partial.setdefault(call.index, {"id": "", "name": "", "arguments": ""})
            if getattr(call, "id", None):
                slot["id"] = call.id
            function = getattr(call, "function", None)
            if function is not None:
                if getattr(function, "name", None):
                    slot["name"] = function.name
                if getattr(function, "arguments", None):
                    slot["arguments"] += function.arguments
        piece = getattr(delta, "content", None)
        if piece:
            text_parts.append(piece)
            if not partial:
                yield piece

    latency_ms = int((time.perf_counter() - started) * 1000)
    text = "".join(text_parts)
    tool_calls, raw_tool_calls = _stream_tool_calls(partial)
    cost = estimate_cost(model, prompt_tokens, completion_tokens)

    raw_message: dict[str, Any] = {"role": "assistant", "content": text}
    if raw_tool_calls:
        raw_message["tool_calls"] = raw_tool_calls

    _record_call(tier, model, prompt_tokens, completion_tokens, latency_ms, tool_calls, cost)
    yield LLMResult(
        text=text,
        tool_calls=tool_calls,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        latency_ms=latency_ms,
        cost_usd=cost,
        raw_message=raw_message,
    )


# Models that have already rejected a `json_schema` response_format, so the next
# chat_json for them starts in plain JSON mode instead of paying another 400.
# Populated at runtime; keyed by the model name we send, same as the price table.
_no_json_schema: set[str] = set()

# Substrings that mark a 400 as "I do not accept this response_format", as
# opposed to a 400 about the messages. Bedrock's Anthropic models, for example,
# refuse `minimum`/`maximum` on a number and answer
# "output_config.format.schema: ... maximum, minimum are not supported".
_SCHEMA_REJECTED = ("response_format", "json_schema", "output_config", "schema")


def _schema_rejected(exc: BadRequestError) -> bool:
    """True when a 400 is about the JSON schema rather than the conversation."""
    text = str(exc).lower()
    return any(marker in text for marker in _SCHEMA_REJECTED)


def _unfence(text: str) -> str:
    """Strip a ```json ... ``` wrapper. json_object mode is an instruction, not a
    grammar, on Bedrock's Anthropic models, and they like to fence their JSON."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return text
    body = stripped.split("\n", 1)[1] if "\n" in stripped else ""
    return body.rsplit("```", 1)[0].strip()


def _schema_in_prompt(
    messages: list[dict[str, Any]], name: str, json_schema: dict[str, Any]
) -> list[dict[str, Any]]:
    """Move the schema into the system prompt, for providers that only do json_object."""
    instruction = (
        f"Reply with a single JSON object and nothing else. It must validate "
        f"against this JSON Schema named {name}:\n{json.dumps(json_schema)}"
    )
    out = list(messages)
    for i, m in enumerate(out):
        if m.get("role") == "system":
            out[i] = {**m, "content": f"{m['content']}\n\n{instruction}"}
            return out
    return [{"role": "system", "content": instruction}, *out]


async def chat_json(
    tier: Tier,
    messages: list[dict[str, Any]],
    schema: type[BaseModel],
    **kwargs: Any,
) -> BaseModel:
    """Chat constrained to `schema`, validated. One retry with the error shown.

    Small models mostly honour json_schema but occasionally drop a field; the
    retry is cheaper than a bespoke repair prompt.

    Two providers, two shapes of JSON: most accept a `json_schema`
    response_format, but Bedrock's Anthropic models validate the schema and 400
    on constructs pydantic emits (`minimum`/`maximum` on a number). On that 400
    we fall back once to `{"type": "json_object"}` with the schema pasted into
    the system prompt, and remember the model so the next call skips the 400.
    The log line says which path a call took.
    """
    json_schema = schema.model_json_schema()
    model = model_for(tier)
    if model in _no_json_schema:
        response_format: dict[str, Any] = {"type": "json_object"}
        convo = _schema_in_prompt(list(messages), schema.__name__, json_schema)
    else:
        response_format = {
            "type": "json_schema",
            "json_schema": {"name": schema.__name__, "schema": json_schema},
        }
        convo = list(messages)
    last_error: Exception | None = None

    for attempt in (1, 2):
        try:
            result = await chat(tier, convo, response_format=response_format, **kwargs)
        except BadRequestError as exc:
            if response_format["type"] != "json_schema" or not _schema_rejected(exc):
                raise
            log.warning(
                "chat_json model=%s rejected json_schema, falling back to json_object: %s",
                model,
                exc,
            )
            _no_json_schema.add(model)
            response_format = {"type": "json_object"}
            convo = _schema_in_prompt(convo, schema.__name__, json_schema)
            result = await chat(tier, convo, response_format=response_format, **kwargs)
        try:
            parsed = schema.model_validate_json(_unfence(result.text))
            log.info("chat_json %s via %s (attempt %d)", schema.__name__, response_format["type"], attempt)
            return parsed
        except (ValidationError, ValueError) as exc:
            last_error = exc
            log.warning("chat_json attempt %d failed validation: %s", attempt, exc)
            convo = convo + [
                result.raw_message,
                {
                    "role": "user",
                    "content": (
                        f"That did not validate against the schema: {exc}. "
                        "Reply with JSON matching the schema and nothing else."
                    ),
                },
            ]

    raise ValueError(f"{schema.__name__} not produced after 2 attempts: {last_error}")


async def embed(texts: list[str], *, client: AsyncOpenAI | None = None) -> list[list[float]]:
    """Embed texts with EMBED_MODEL, 32 at a time; order is preserved."""
    if not texts:
        return []
    out: list[list[float]] = []
    api = client or embed_client()
    for start in range(0, len(texts), EMBED_BATCH):
        batch = texts[start : start + EMBED_BATCH]
        started = time.perf_counter()
        response = await api.embeddings.create(model=settings.embed_model, input=batch)
        latency_ms = int((time.perf_counter() - started) * 1000)
        out.extend(item.embedding for item in response.data)
        log.info("embed model=%s items=%d latency=%dms", settings.embed_model, len(batch), latency_ms)
    return out
