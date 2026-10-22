"""POST /api/chat and POST /api/chat/stream — the two endpoints the resident UI needs.

Thin: they bound the body, check the two cost guards and hand off to
app/agents/chat, which never raises. Depends on: app.db.engine — the buffered
route takes the usual session dependency, the streaming route opens its own
short-lived sessions so it never holds a pool connection while a body drains.
"""

import asyncio
import contextlib
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app import clock
from app.agents.chat import FALLBACK_REPLY, ChatResponse, handle_chat, stream_chat
from app.config import settings
from app.db import models
from app.db.engine import SessionLocal, get_session
from app.rate_limit import rate_limit
from app.resident_session import SESSION_ID_PATTERN, require_or_mint

log = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

# The browser mints the session id with crypto.randomUUID(); the eval runner and
# smoke.sh mint their own. Anything outside SESSION_ID_PATTERN is a caller probing
# the history key (a newline to split a log line, "../etc" to look like a path),
# and the id is the only thing tying a conversation together, so it is bounded
# and typed. The pattern itself moved to app/resident_session.py in M20, where
# the upload route bounds the same value.
# One turn may cite at most this many uploads. Each id costs a SMALL detect call
# and an EXTRACT call, so an unbounded list was an unbounded bill.
MAX_DOCUMENT_IDS = 5

# At most this many turns stream at once. Each one holds a DB session for the
# whole turn, and the pool is 10 + 10; without this, request 21 waits for the
# pool rather than for a slot and comes back as the apology with a 200.
_stream_slots = asyncio.Semaphore(settings.max_concurrent_streams)

#: How long the generator waits for the next orchestrator event before sending a
#: keep-alive. An ALB idles a connection out at 60 s by default and a slow tool
#: round can take longer than that, so a silent SSE connection is a dropped
#: answer with no resume (finding #17). A comment line is the cheapest keep-alive
#: the protocol has: EventSource ignores it, and so does web/lib/stream.ts.
HEARTBEAT_INTERVAL_S = 15.0
HEARTBEAT = ": heartbeat\n\n"

#: What a resident sees when every stream slot is taken.
BUSY = "The assistant is busy. Try again in a few seconds."

#: The day's spend, in the City's own day rather than UTC's.
#:
#: Two things were wrong with `date(created_at) = current_date()`. It compared a
#: UTC day to the City's, so the cap reset at 5 pm Pacific; and `date(created_at)`
#: is a function on the column, so it could not use traces_created_idx. Casting
#: through AT TIME ZONE keeps the first fix; the BETWEEN on the bare column keeps
#: the index usable, which is the second.
DAILY_SPEND_SQL = text(
    """
    SELECT COALESCE(SUM(cost_usd), 0.0) FROM traces
    WHERE created_at >= (
              (now() AT TIME ZONE 'America/Los_Angeles')::date
          ) AT TIME ZONE 'America/Los_Angeles'
      AND created_at < (
              ((now() AT TIME ZONE 'America/Los_Angeles')::date + 1)
          ) AT TIME ZONE 'America/Los_Angeles'
    """
)

#: Warn once per City day when the breaker is in sight, so an operator hears
#: about it before residents get the 429 rather than after.
CAP_WARN_FRACTION = 0.8
_cap_warned_on = None


class ChatRequest(BaseModel):
    """The resident turn, bounded at the edge so nothing unbounded reaches a model."""

    session_id: str = Field(pattern=SESSION_ID_PATTERN, description="Browser-generated id")
    # Bedrock rejects an empty user turn ("a conversation must start with a user
    # message"), which surfaced as the generic "something went wrong" apology and
    # still cost a classifier call. Saying 422 up front is honest and free.
    # The upper bound is the other half: a 1 MB message used to be a 200, and the
    # whole text went to classify(), the prompt, the history and the traces row.
    message: str = Field(min_length=1, max_length=settings.max_message_chars)
    # M2 records these on the trace; M3 wires them into document intake.
    document_ids: list[int] = Field(default_factory=list, max_length=MAX_DOCUMENT_IDS)

    @field_validator("document_ids")
    @classmethod
    def _dedupe(cls, ids: list[int]) -> list[int]:
        """`[7, 7, 7]` is one document, not three EXTRACT calls. Order is kept."""
        return list(dict.fromkeys(ids))


async def enforce_limits(session: AsyncSession, session_id: str) -> None:
    """Refuse a turn that would blow the per-session or per-day ceiling.

    Runs before classify(), because the classifier is itself a model call: a
    breaker that trips after the first call is not a breaker. Both queries are
    plain aggregates, and a 429 carries a sentence a resident can read.
    """
    turns = (
        await session.execute(
            select(func.count())
            .select_from(models.ChatMessage)
            .where(models.ChatMessage.session_id == session_id)
            .where(models.ChatMessage.role == "user")
        )
    ).scalar_one()
    if turns >= settings.max_turns_per_session:
        raise HTTPException(
            status_code=429,
            detail=(
                "This conversation has reached its limit of "
                f"{settings.max_turns_per_session} messages. Start a new conversation "
                "to keep going."
            ),
        )

    global _cap_warned_on
    spend = float((await session.execute(DAILY_SPEND_SQL)).scalar_one() or 0.0)
    if spend >= settings.daily_cost_cap_usd:
        log.warning("daily cost cap reached: $%.4f", spend)
        raise HTTPException(
            status_code=429,
            detail=(
                "The assistant has reached its daily usage limit and is paused until "
                "tomorrow. Call the City's general information line at 619-236-5555."
            ),
        )
    # Once per City day, not once per turn: at 80% of the cap there are still
    # hundreds of turns left, and a line per turn would bury the one that matters.
    if spend >= CAP_WARN_FRACTION * settings.daily_cost_cap_usd:
        day = clock.today()
        if _cap_warned_on != day:
            _cap_warned_on = day
            log.warning(
                "daily cost is at %.0f%% of the $%.2f cap ($%.4f spent today, %s)",
                100 * spend / settings.daily_cost_cap_usd,
                settings.daily_cost_cap_usd,
                spend,
                day.isoformat(),
            )


@router.post("/api/chat", response_model=ChatResponse, dependencies=[Depends(rate_limit)])
async def post_chat(
    request: Request,
    body: ChatRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> ChatResponse:
    """One buffered turn. Kept alongside the stream because evals and smoke.sh need a body."""
    if not body.message.strip():
        raise HTTPException(status_code=422, detail="message must not be blank")
    # Who owns the conversation is decided before what it costs: a turn sent on
    # someone else's id must not spend their quota on the way to a 403.
    await require_or_mint(session, body.session_id, request, response)
    await enforce_limits(session, body.session_id)
    response = await handle_chat(session, body.session_id, body.message, body.document_ids)
    # The access line carries the traces row id, so one grep joins "it went wrong
    # at 14:03" to the turn that did. The stream route cannot: its trace id only
    # exists after the body has been sent and the line already logged.
    request.state.trace_id = response.trace.get("id")
    return response


def _sse(event: dict) -> str:
    """One server-sent event. `default=str` because a tool result may hold a date."""
    return f"data: {json.dumps(event, default=str)}\n\n"


@asynccontextmanager
async def stream_slot() -> AsyncIterator[None]:
    """Hold one of MAX_CONCURRENT_STREAMS slots for the life of a block.

    Kept for the tests and for any caller that *wants* to queue. The route itself
    no longer uses it: it takes the slot without waiting (see `take_stream_slot`).
    """
    async with _stream_slots:
        yield


def take_stream_slot() -> bool:
    """Take a stream slot if one is free right now; never wait for one.

    The spec for this reads "asyncio.wait_for(acquire(), timeout=0) semantics",
    and this *is* those semantics, written out — `wait_for` with a zero timeout
    cannot be used literally, because it wraps the coroutine in a task, checks
    `done()` before the loop has had a chance to run it, and so times out even
    when a slot is free.

    `locked()` and `acquire()` are safe to read as one step: asyncio is
    single-threaded and `Semaphore.acquire` returns without suspending on the
    free path, so no other task can run between the two lines.
    """
    if _stream_slots.locked():
        return False
    # The non-blocking half of Semaphore.acquire(), which has no public form.
    _stream_slots._value -= 1
    return True


async def _with_heartbeat(events: AsyncIterator[dict], interval: float) -> AsyncIterator[str]:
    """Serialise `events` to SSE, emitting a comment line whenever it goes quiet.

    A tool round or a slow first token can leave the socket silent for longer
    than a load balancer's idle timeout (60 s on an ALB by default), and a
    dropped SSE connection has no resume — the resident just watches a half
    answer stop. A comment frame keeps the connection warm and is invisible to
    the client: EventSource drops any line starting with a colon on the floor.

    The turn runs to completion inside ONE producer task and hands events over a
    queue. The first version drove `__anext__` step by step from fresh tasks,
    which ran each step of the generator in a different asyncio context; the
    trace collector's ContextVar token, set at the top of the turn, was then
    reset from another context and every streamed turn ended in a ValueError
    after its last token (found on the rebuilt stack 2026-09-15).
    """
    queue: asyncio.Queue[tuple[str, object]] = asyncio.Queue()

    async def pump() -> None:
        try:
            async for event in events:
                await queue.put(("event", event))
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - handed to the consumer, which raises it
            await queue.put(("error", exc))
            return
        await queue.put(("end", None))

    task = asyncio.create_task(pump())
    try:
        while True:
            try:
                kind, payload = await asyncio.wait_for(queue.get(), interval)
            except TimeoutError:
                yield HEARTBEAT
                continue
            if kind == "event":
                yield _sse(payload)  # type: ignore[arg-type]
            elif kind == "error":
                raise payload  # type: ignore[misc]
            else:
                return
    finally:
        if not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task


@router.post("/api/chat/stream", dependencies=[Depends(rate_limit)])
async def post_chat_stream(request: Request, body: ChatRequest) -> StreamingResponse:
    """The same turn as /api/chat, delivered as it happens.

    No `Depends(get_session)`. A yield-dependency is *not* released before a
    StreamingResponse body drains, so the old signature pinned one pool
    connection for the whole stream and then asked for a second one inside the
    generator — a hard deadlock at exactly pool_size + max_overflow = 20
    concurrent streams, measured by the reviewer. The guards now run in a session
    opened and closed inside this handler, and the generator opens its own.

    Admission control is a 429 here rather than a queue inside the generator: the
    semaphore used to be acquired after the 200 and the headers were already on
    the wire, so nothing could shed load and no client saw backpressure.

    Any failure still ends in a `done` event with the reply the buffered path
    would have given — a resident should never watch the connection simply stop.
    """
    if not body.message.strip():
        raise HTTPException(status_code=422, detail="message must not be blank")

    async def events() -> AsyncIterator[str]:
        """Every orchestrator event as SSE, ending in `done` whatever happens."""
        try:
            async with SessionLocal() as stream_session:
                turn = stream_chat(stream_session, body.session_id, body.message, body.document_ids)
                async for frame in _with_heartbeat(turn, HEARTBEAT_INTERVAL_S):
                    yield frame
        except Exception as exc:  # noqa: BLE001 - a dropped socket is worse than a bad answer
            log.exception("chat stream failed")
            yield _sse(
                {
                    "type": "done",
                    "reply": FALLBACK_REPLY,
                    "citations": [],
                    "actions": [],
                    "trace": {"error": f"{type(exc).__name__}: {exc}"},
                }
            )
        finally:
            # The slot was taken in the handler, so it is given back here however
            # the body ends: a clean `done`, an exception, or a client that hung
            # up mid-answer (starlette still closes the generator).
            _stream_slots.release()

    stream = StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # nginx and friends buffer a proxied response by default, which would
            # hand the resident the whole answer at once — the thing we just fixed.
            "X-Accel-Buffering": "no",
        },
    )
    # The cookie is set on the object actually returned: FastAPI copies a
    # dependency Response's headers only for routes that return a model, and
    # Set-Cookie has to be on the wire before the first token. Constructing the
    # response does not start the body — the generator is lazy — so nothing has
    # been sent yet and a guard below can still raise. Both guards run in the
    # same order as the buffered route: 403 before 429.
    async with SessionLocal() as guard_session:
        await require_or_mint(guard_session, body.session_id, request, stream)
        await enforce_limits(guard_session, body.session_id)

    # Last, because everything above can still raise and an un-started generator
    # never reaches its `finally` to give the slot back.
    if not take_stream_slot():
        log.info("stream refused: all %d slots busy", settings.max_concurrent_streams)
        raise HTTPException(status_code=429, detail=BUSY, headers={"Retry-After": "2"})
    return stream
