"""The orchestrator: one resident message in, one traced answer out.

Called by app/api/chat.py (both `/api/chat` and `/api/chat/stream`). Depends on:
app.agents.intake_turn (document and gap-filling turns, which short-circuit the
Q&A flow), app.llm.router (intent + tier), app.rag.retrieve (sources),
app.tools.registry (tool loop), app.db.models (history and the trace row). Every
failure path still returns a reply and a trace — a resident should never see a 500.

The turn is written once, as `stream_chat`, an async generator of events; the
`done` event carries the whole ChatResponse. `handle_chat` is a four-line
consumer of it, so the streaming endpoint and the buffered one cannot drift.
"""

import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

from pydantic import BaseModel
from sqlalchemy import desc, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.intake_turn import handle_intake_turn
from app.agents.profiles import profile_for, system_prompt_for, tools_for
from app.agents.rendering import (
    actions_from,
    citations_for,
    render_sources,
    source_entries,
    sources_block,
    today_line,
    untrusted_source,
)
from app.db import models
from app.llm import router as llm_router
from app.llm.client import (
    LLMResult,
    TraceCollector,
    chat_stream,
    model_for,
    reset_trace,
    set_trace,
)
from app.rag.retrieve import Hit, retrieve
from app.tools.registry import dispatch, openai_schemas

log = logging.getLogger(__name__)

HISTORY_TURNS = 10
MAX_TOOL_ROUNDS = 4
FALLBACK_REPLY = (
    "Sorry — something went wrong on my side while I was looking that up. Please try again, "
    "or call the City's general information line at 619-236-5555."
)


class ChatResponse(BaseModel):
    """What POST /api/chat returns; the trace drives the UI's trace drawer."""

    reply: str
    citations: list[dict]
    actions: list[dict]
    trace: dict


async def _history(session: AsyncSession, session_id: str) -> list[dict]:
    """Last N messages for this session, oldest first, role/content only."""
    rows = (
        (
            await session.execute(
                select(models.ChatMessage)
                .where(models.ChatMessage.session_id == session_id)
                .order_by(desc(models.ChatMessage.id))
                .limit(HISTORY_TURNS)
            )
        )
        .scalars()
        .all()
    )
    return [{"role": r.role, "content": r.content} for r in reversed(rows)]


def _call_key(name: str, arguments: dict) -> str:
    """Stable identity for one tool call, so a repeat is recognisable."""
    return name + "|" + json.dumps(arguments or {}, sort_keys=True, default=str)


def _not_allowed(name: str) -> dict:
    """The result a tool call gets when the profile never offered that tool.

    A summary rather than an exception: the model asked for something it was not
    given, and the honest repair is to tell it so and let it write the answer
    with what it does have (probe A9).
    """
    message = f"tool '{name}' is not available for this request"
    return {"error": message, "summary": message}


async def _tool_loop(
    session: AsyncSession,
    tier,
    messages: list[dict],
    schemas: list[dict],
    offset: int = 0,
    allowed: set[str] | None = None,
) -> AsyncIterator[dict]:
    """Chat until the model stops asking for tools; max MAX_TOOL_ROUNDS rounds.

    An async generator: it yields `{"type": "token"}` for the words of the answer
    as the model writes them and `{"type": "tool"}` as each call is dispatched,
    then one private `{"type": "_end"}` carrying (reply, calls, tool_sources) for
    the caller. Only the round that turns out to be the answer reaches the
    resident: `chat_stream` stops yielding text the moment a round starts calling
    tools, and the web clears whatever it had shown when a `tool` event arrives.

    A model that re-asks for a tool it already ran (the same name and the same
    arguments) gets the cached result rather than a second database hit: it is
    the same answer either way, and re-running it is how a turn burns its four
    rounds and times out.

    A tool that returns `sources` (search_city_website fetching sandiego.gov
    pages) has them numbered from `offset` — the count of retrieved KB chunks —
    and appended to the tool message, so the model cites a fetched page with the
    same [n] syntax as a knowledge-base chunk.

    `allowed` is the profile's tool allow-list. A model that asks for a tool this
    intent was never offered gets an error summary and no execution (probe A9);
    `None` means "no allow-list", which is what the unit tests drive the loop
    with. Everything the loop hands back to the model — tool JSON and fetched
    page text alike — goes inside a `<source trust="untrusted">` fence.
    """
    calls: list[dict] = []
    cache: dict[str, dict] = {}
    tool_sources: list[dict] = []
    reply = ""
    rounds_used = 0
    for round_no in range(MAX_TOOL_ROUNDS):
        rounds_used = round_no + 1
        result: LLMResult | None = None
        async for item in chat_stream(tier, messages, tools=schemas or None):
            if isinstance(item, str):
                yield {"type": "token", "text": item}
            else:
                # chat_stream always ends with the LLMResult; anything else is a delta.
                result = item
        if result is None:  # pragma: no cover - only a broken stream gets here
            break
        reply = result.text
        if not result.tool_calls:
            break
        messages.append(result.raw_message)
        for call in result.tool_calls:
            key = _call_key(call["name"], call["arguments"])
            cached = key in cache
            yield {"type": "tool", "name": call["name"], "cached": cached}
            if cached:
                log.info("tool loop: reusing cached result for %s", call["name"])
                output = cache[key]
            elif allowed is not None and call["name"] not in allowed:
                # The allow-list belongs to the profile, not the registry, so the
                # refusal happens here — before dispatch, so the tool never runs.
                log.warning("tool loop: %s is not on this profile's allow-list", call["name"])
                output = _not_allowed(call["name"])
                cache[key] = output
            else:
                output = await dispatch(call["name"], call["arguments"], session)
                cache[key] = output
            calls.append(
                {
                    "name": call["name"],
                    "arguments": call["arguments"],
                    "result_summary": output.get("summary") or output.get("error") or "",
                    "result": output,
                    "round": round_no + 1,
                    "cached": cached,
                }
            )
            # The tool's own JSON is fenced with a "t"-prefixed label: it is data
            # the model may use but never a citable [n], and the prefix keeps it
            # out of the citation numbering that the KB chunks and fetched pages
            # share.
            content = untrusted_source(json.dumps(output, default=str), n=f"t{len(calls)}", kind="tool")
            fresh = [] if cached else (output.get("sources") or [])
            if fresh:
                first = offset + len(tool_sources) + 1
                entries = source_entries([], fresh)
                tool_sources.extend(fresh)
                content += (
                    "\n\nThese pages are now sources "
                    + ", ".join(f"[{n}]" for n in range(first, first + len(fresh)))
                    + ". Cite them by those numbers:\n"
                    + render_sources(entries, start=first, kind="page")
                )
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": content})
    else:
        # The loop ran out of rounds while the model still wanted a tool. M10 asks
        # for evidence before raising the cap, so say so in the log rather than
        # guessing: two different tools plus the answer needs three rounds, and
        # MAX_TOOL_ROUNDS is 4.
        log.warning("tool loop hit MAX_TOOL_ROUNDS=%d with calls still pending", MAX_TOOL_ROUNDS)
    yield {
        "type": "_end",
        "reply": reply,
        "calls": calls,
        "tool_sources": tool_sources,
        # On the trace so a reader can see a turn that spent its whole budget
        # looping (probe A10) without re-reading the logs.
        "rounds": rounds_used,
    }


async def _persist(session: AsyncSession, session_id: str, message: str, reply: str, trace_row: dict) -> int:
    """Write the trace, then the user and assistant messages that point at it."""
    trace_id = (
        await session.execute(insert(models.Trace).values(**trace_row).returning(models.Trace.id))
    ).scalar_one()
    await session.execute(
        insert(models.ChatMessage),
        [
            {"session_id": session_id, "role": "user", "content": message, "trace_id": trace_id},
            {"session_id": session_id, "role": "assistant", "content": reply, "trace_id": trace_id},
        ],
    )
    await session.commit()
    return trace_id


async def stream_chat(
    session: AsyncSession, session_id: str, message: str, document_ids: list[int] | None = None
) -> AsyncIterator[dict]:
    """Classify, retrieve, answer with tools, cite, persist — as a stream of events.

    Yields, in order: one `status` (intent, tier and the model name, right after
    routing), a `tool` per dispatched call, a `token` per delta of the final
    answer, and always exactly one `done` carrying the whole ChatResponse body.
    A workflow turn (an upload, a gap-fill) is templated rather than generated,
    so it yields only `done`. Never raises: a failure is a `done` with the same
    fallback reply the buffered path returns, because a resident watching a
    stream must not be left with a half-sentence and a dead socket.
    """
    document_ids = document_ids or []

    # A file drop, or a reply to "I still need ...", is a workflow turn, not a
    # question. handle_intake_turn returns None for everything else.
    payload = await handle_intake_turn(session, session_id, message, document_ids)
    if payload is not None:
        trace_row = payload["trace"]
        try:
            trace_row["id"] = await _persist(session, session_id, message, payload["reply"], dict(trace_row))
        except Exception as exc:  # noqa: BLE001 - never lose the answer over a write
            log.exception("failed to persist intake turn")
            trace_row["id"] = None
            trace_row["error"] = f"persist failed: {exc}"
        yield {
            "type": "done",
            "reply": payload["reply"],
            "citations": payload["citations"],
            "actions": payload["actions"],
            "trace": trace_row,
        }
        return

    started = time.perf_counter()
    collector = TraceCollector()
    token = set_trace(collector)
    hits: list[Hit] = []
    calls: list[dict] = []
    tool_sources: list[dict] = []
    tool_rounds = 0
    classification = None
    tier_name = "smart"
    reason = ""
    error: str | None = None
    reply = FALLBACK_REPLY

    try:
        history = await _history(session, session_id)
        recent_user = [m["content"] for m in history if m["role"] == "user"]

        classification = await llm_router.classify(message, recent_user)
        tier, reason = llm_router.select_tier(classification)
        tier_name = tier.value
        profile = profile_for(classification.intent)
        # The model name rides along so the UI can say "smart · claude-sonnet-4-6"
        # while the answer is still being written, not only once the trace lands.
        yield {
            "type": "status",
            "intent": classification.intent,
            "tier": tier_name,
            "model": model_for(tier),
        }

        if classification.intent != "smalltalk":
            hits = await retrieve(session, message, profile.kb_topic)

        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                # The date goes last so it is the freshest thing in the prompt.
                # system_prompt_for / tools_for drop the web-search rule and the
                # web-search tool together when SEARCH_PROVIDER is "none".
                "content": system_prompt_for(profile) + sources_block(hits) + today_line(),
            },
            *history,
            {"role": "user", "content": message},
        ]
        tool_names = tools_for(profile)
        async for event in _tool_loop(
            session,
            tier,
            messages,
            openai_schemas(tool_names),
            offset=len(hits),
            allowed=set(tool_names),
        ):
            if event["type"] == "_end":
                reply, calls, tool_sources = (event["reply"], event["calls"], event["tool_sources"])
                tool_rounds = event["rounds"]
            else:
                yield event
        if not reply.strip():
            reply = (
                "I wasn't able to put an answer together for that. Could you rephrase it, or "
                "give me the address or tracking number it relates to?"
            )
    except Exception as exc:  # noqa: BLE001 - a broken turn is still a traced turn
        log.exception("chat turn failed")
        error = f"{type(exc).__name__}: {exc}"
        reply = FALLBACK_REPLY
    finally:
        reset_trace(token)

    citations = citations_for(reply, hits, tool_sources) if error is None else []
    totals = collector.totals
    trace_row = {
        "session_id": session_id,
        "message": message,
        "reply": reply,
        "intent": classification.intent if classification else None,
        "confidence": classification.confidence if classification else None,
        "tier": tier_name,
        "model": model_for(llm_router.Tier(tier_name)),
        "reason": reason,
        "error": error,
        "rag_chunk_ids": [h.chunk_id for h in hits],
        # source/match come from the M8 live tools: "live" vs "seed", and how the
        # address was resolved. They are the two facts a trace reader most wants.
        "tool_calls": [
            {
                "name": c["name"],
                "arguments": c["arguments"],
                "result_summary": c["result_summary"],
                "source": c["result"].get("source"),
                "match": c["result"].get("match"),
            }
            for c in calls
        ],
        "tool_rounds": tool_rounds,
        "calls": collector.calls,
        "document_ids": document_ids,
        "prompt_tokens": totals["prompt_tokens"],
        "completion_tokens": totals["completion_tokens"],
        "latency_ms": int((time.perf_counter() - started) * 1000),
        "cost_usd": totals["cost_usd"],
    }

    try:
        trace_row["id"] = await _persist(session, session_id, message, reply, dict(trace_row))
    except Exception as exc:  # noqa: BLE001 - never lose the answer over a write
        log.exception("failed to persist chat turn")
        trace_row["id"] = None
        trace_row["error"] = trace_row["error"] or f"persist failed: {exc}"

    yield {
        "type": "done",
        "reply": reply,
        "citations": citations,
        "actions": actions_from(calls),
        "trace": trace_row,
    }


async def handle_chat(
    session: AsyncSession, session_id: str, message: str, document_ids: list[int] | None = None
) -> ChatResponse:
    """The buffered turn: drain stream_chat and return its `done` body.

    `/api/chat`, the eval runner and scripts/smoke.sh all come through here, so
    it stays a consumer rather than a second implementation — the two endpoints
    cannot answer differently if only one of them can think.
    """
    async for event in stream_chat(session, session_id, message, document_ids):
        if event["type"] == "done":
            return ChatResponse(
                reply=event["reply"],
                citations=event["citations"],
                actions=event["actions"],
                trace=event["trace"],
            )
    # stream_chat always ends in `done`; this is here so the type checker and a
    # future refactor both see what happens if that ever stops being true.
    raise RuntimeError("stream_chat finished without a done event")
