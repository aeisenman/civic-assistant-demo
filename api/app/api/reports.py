"""GET /api/reports/summary — every number behind the staff dashboard, in SQL.

Called by web/app/staff/dashboard/page.tsx through web/lib/reports.ts; nothing
else reads it. Depends on: app.db.engine (the session), app.db.models (traces,
chat_messages, applications, application_events) and app.auth (staff only).

Why SQL and not Python: the traces table is the only place a turn is recorded,
and a dashboard that paged 30 days of rows into the process to count them would
be the first thing to fall over. Every figure below is one aggregate, so the
work stays in Postgres and the response is a few kilobytes whatever the window.
"""

import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Float, and_, cast, desc, distinct, func, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.chat import FALLBACK_REPLY
from app.auth import require_staff
from app.db import models
from app.db.engine import get_session

log = logging.getLogger(__name__)

# The whole router is staff-only: it reports on resident messages, which is the
# same data the traces router is gated for.
router = APIRouter(tags=["reports"], dependencies=[Depends(require_staff)])

#: The window the dashboard may ask for. 1 is "today-ish", 90 is a quarter; past
#: that the by_day series stops being a chart and the query stops being cheap.
MIN_DAYS = 1
MAX_DAYS = 90

#: Turns the dashboard does not judge: a greeting has nothing to cite and nothing
#: to look up, so counting it as "unanswered" would be noise.
SMALLTALK = "smalltalk"

#: The decline family, copied (not imported — app/ must not depend on the eval
#: harness) from the eval scorer's PROMPT_CONSTANTS in evals/run.py, whose own
#: comment is the definition: "the City's general information line. Every
#: referral and every 'I don't have that' reply ends in it." A reply that hands
#: the resident this number is a reply the assistant could not answer itself.
DECLINE_PHRASES = ("619-236-5555",)

#: How many recent misses the dashboard lists. Enough to read in one sitting.
UNANSWERED_LIMIT = 10


def _cutoff(days: int) -> datetime:
    """The start of the window, computed once so every query shares one instant."""
    return datetime.now(UTC) - timedelta(days=days)


def _rounded(value: float | None, places: int) -> float:
    """None-safe rounding: an empty window must still produce a number, not null."""
    return round(float(value or 0.0), places)


# ------------------------------------------------------------------ totals


async def _totals(session: AsyncSession, cutoff: datetime) -> dict:
    """Turns, cost, latency percentiles and the two failure counts, in one row.

    `fallback_turns` counts the turns the resident saw the canned apology on:
    either the orchestrator caught an exception (`error` set) or it returned
    FALLBACK_REPLY, which is the same event seen from the other side.
    """
    is_error = models.Trace.error.isnot(None)
    stmt = select(
        func.count().label("turns"),
        func.coalesce(func.sum(models.Trace.cost_usd), 0.0).label("cost_usd"),
        func.percentile_cont(0.5).within_group(models.Trace.latency_ms).label("p50"),
        func.percentile_cont(0.95).within_group(models.Trace.latency_ms).label("p95"),
        func.count().filter(is_error).label("error_turns"),
        func.count().filter(or_(is_error, models.Trace.reply == FALLBACK_REPLY)).label("fallback_turns"),
    ).where(models.Trace.created_at >= cutoff)
    row = (await session.execute(stmt)).one()
    return {
        "turns": int(row.turns or 0),
        "cost_usd": _rounded(row.cost_usd, 6),
        "latency_p50_ms": int(row.p50 or 0),
        "latency_p95_ms": int(row.p95 or 0),
        "error_turns": int(row.error_turns or 0),
        "fallback_turns": int(row.fallback_turns or 0),
    }


async def _sessions(session: AsyncSession, cutoff: datetime) -> int:
    """Distinct conversations in the window, from chat_messages rather than traces.

    A conversation exists as soon as the resident types, even if that turn failed
    before a trace row was written, so this is the honest denominator.
    """
    stmt = select(func.count(distinct(models.ChatMessage.session_id))).where(
        models.ChatMessage.created_at >= cutoff
    )
    return int((await session.execute(stmt)).scalar() or 0)


# -------------------------------------------------------------- breakdowns


async def _by_day(session: AsyncSession, cutoff: datetime) -> list[dict]:
    """One row per calendar day: volume, spend and the slow tail."""
    day = func.date(models.Trace.created_at).label("day")
    stmt = (
        select(
            day,
            func.count().label("turns"),
            func.coalesce(func.sum(models.Trace.cost_usd), 0.0).label("cost_usd"),
            func.percentile_cont(0.95).within_group(models.Trace.latency_ms).label("p95"),
        )
        .where(models.Trace.created_at >= cutoff)
        .group_by(day)
        .order_by(day)
    )
    return [
        {
            "date": r.day.isoformat() if hasattr(r.day, "isoformat") else str(r.day),
            "turns": int(r.turns or 0),
            "cost_usd": _rounded(r.cost_usd, 6),
            "latency_p95_ms": int(r.p95 or 0),
        }
        for r in (await session.execute(stmt)).all()
    ]


async def _by_intent(session: AsyncSession, cutoff: datetime, turns: int) -> list[dict]:
    """What residents actually ask about.

    `share` is divided here rather than in SQL: the total is already known, and a
    window function would cost a second pass to produce the same fraction.
    """
    intent = func.coalesce(models.Trace.intent, "unknown").label("intent")
    stmt = (
        select(intent, func.count().label("turns"))
        .where(models.Trace.created_at >= cutoff)
        .group_by(intent)
        .order_by(desc("turns"))
    )
    return [
        {
            "intent": r.intent,
            "turns": int(r.turns or 0),
            "share": _rounded(int(r.turns or 0) / turns, 4) if turns else 0.0,
        }
        for r in (await session.execute(stmt)).all()
    ]


async def _by_tier(session: AsyncSession, cutoff: datetime) -> list[dict]:
    """Where the money goes: the router's tier choice against its bill."""
    tier = func.coalesce(models.Trace.tier, "unknown").label("tier")
    stmt = (
        select(
            tier,
            func.count().label("turns"),
            func.coalesce(func.sum(models.Trace.cost_usd), 0.0).label("cost_usd"),
        )
        .where(models.Trace.created_at >= cutoff)
        .group_by(tier)
        .order_by(desc("turns"))
    )
    return [
        {"tier": r.tier, "turns": int(r.turns or 0), "cost_usd": _rounded(r.cost_usd, 6)}
        for r in (await session.execute(stmt)).all()
    ]


async def _tools(session: AsyncSession, cutoff: datetime) -> list[dict]:
    """Tool usage, unnested from the `tool_calls` JSONB with jsonb_array_elements.

    The column is a JSONB array of `{name, arguments, result_summary, source,
    error?}` objects, so counting calls means expanding it in SQL: a lateral
    `jsonb_array_elements` gives one row per call and the three counts are plain
    FILTERs over it. `jsonb_exists` is the function spelling of the `?` operator,
    and `?` is a parameter marker for several drivers — the function form is the
    one that survives being compiled by any of them.
    """
    call = func.jsonb_array_elements(models.Trace.tool_calls, type_=JSONB).column_valued(
        "call", joins_implicitly=True
    )
    name = call["name"].astext.label("name")
    stmt = (
        select(
            name,
            func.count().label("calls"),
            func.count().filter(func.jsonb_exists(call, "error")).label("errors"),
            func.count().filter(call["source"].astext == "live").label("live"),
        )
        # `traces` must be named first: a lateral function may only reference a
        # FROM entry to its left, so without this the generated SQL is
        # `FROM jsonb_array_elements(traces.tool_calls), traces`, which Postgres
        # rejects as an invalid reference.
        .select_from(models.Trace)
        .where(models.Trace.created_at >= cutoff)
        .group_by(name)
        .order_by(desc("calls"))
    )
    out: list[dict] = []
    for r in (await session.execute(stmt)).all():
        calls = int(r.calls or 0)
        out.append(
            {
                "name": r.name or "unknown",
                "calls": calls,
                "errors": int(r.errors or 0),
                "live_share": _rounded(int(r.live or 0) / calls, 4) if calls else 0.0,
            }
        )
    return out


async def _citation_rate(session: AsyncSession, cutoff: datetime) -> float:
    """Share of real questions answered with at least one retrieved chunk.

    Smalltalk is excluded: a greeting has nothing to cite, and including it would
    make the number move with how politely residents open a conversation.
    """
    cited = func.jsonb_array_length(models.Trace.rag_chunk_ids) > 0
    stmt = select(
        func.count().label("turns"),
        func.count().filter(cited).label("cited"),
    ).where(
        models.Trace.created_at >= cutoff,
        func.coalesce(models.Trace.intent, "") != SMALLTALK,
    )
    row = (await session.execute(stmt)).one()
    turns = int(row.turns or 0)
    return _rounded(int(row.cited or 0) / turns, 4) if turns else 0.0


# ------------------------------------------------------------- applications


async def _applications(session: AsyncSession, cutoff: datetime) -> dict:
    """Counts by type and status, plus how long the queue takes to pick one up."""
    by_type_status_stmt = (
        select(
            models.Application.type.label("type"),
            models.Application.status.label("status"),
            func.count().label("count"),
        )
        .where(models.Application.created_at >= cutoff)
        .group_by(models.Application.type, models.Application.status)
        .order_by(models.Application.type, models.Application.status)
    )
    by_type_status = [
        {"type": r.type, "status": r.status, "count": int(r.count or 0)}
        for r in (await session.execute(by_type_status_stmt)).all()
    ]

    # Time to first human touch: the first `submitted` event and the first
    # `in_review` event of the same application. Taking the *first* of each
    # matters — an application sent back for more information is submitted twice,
    # and pairing the second submission with the first review would read as a
    # negative wait.
    events = (
        select(
            models.ApplicationEvent.application_id.label("application_id"),
            func.min(models.ApplicationEvent.created_at)
            .filter(models.ApplicationEvent.to_status == "submitted")
            .label("submitted_at"),
            func.min(models.ApplicationEvent.created_at)
            .filter(models.ApplicationEvent.to_status == "in_review")
            .label("review_at"),
        )
        .where(models.ApplicationEvent.created_at >= cutoff)
        .group_by(models.ApplicationEvent.application_id)
        .subquery()
    )
    hours = cast(
        func.extract("epoch", events.c.review_at - events.c.submitted_at) / 3600.0,
        Float,
    )
    median_stmt = select(func.percentile_cont(0.5).within_group(hours)).where(
        and_(
            events.c.submitted_at.isnot(None),
            events.c.review_at.isnot(None),
            events.c.review_at >= events.c.submitted_at,
        )
    )
    median = (await session.execute(median_stmt)).scalar()

    counts_stmt = select(
        func.count().filter(models.Application.status == "issued").label("issued"),
        func.count().filter(models.Application.status == "needs_info").label("needs_info"),
    ).where(models.Application.created_at >= cutoff)
    counts = (await session.execute(counts_stmt)).one()

    return {
        "by_type_status": by_type_status,
        # None, not 0: "nothing reached review yet" is not "it took no time".
        "median_hours_to_review": None if median is None else round(float(median), 2),
        "issued": int(counts.issued or 0),
        "needs_info": int(counts.needs_info or 0),
    }


# --------------------------------------------------------------- unanswered


async def _unanswered(session: AsyncSession, cutoff: datetime) -> list[dict]:
    """The most recent turns the assistant could not really answer.

    Two shapes, and the one the dashboard shows as `reason`:
    - `no_sources`: no tool was called and nothing was retrieved, so whatever the
      reply said came from the model alone — the exact thing the prompt forbids.
    - `declined`: the reply handed the resident the City's general line, which is
      the honest ending of "the sources do not cover this".
    Both are content gaps, which is why they are listed rather than counted: the
    list is the input to the next round of KB writing.
    """
    no_sources = and_(
        func.jsonb_array_length(models.Trace.tool_calls) == 0,
        func.jsonb_array_length(models.Trace.rag_chunk_ids) == 0,
    )
    declined = or_(*[models.Trace.reply.ilike(f"%{phrase}%") for phrase in DECLINE_PHRASES])
    stmt = (
        select(
            models.Trace.message,
            models.Trace.intent,
            models.Trace.reply,
            models.Trace.created_at,
        )
        .where(
            models.Trace.created_at >= cutoff,
            func.coalesce(models.Trace.intent, "") != SMALLTALK,
            or_(no_sources, declined),
        )
        .order_by(desc(models.Trace.id))
        .limit(UNANSWERED_LIMIT)
    )
    out: list[dict] = []
    for r in (await session.execute(stmt)).all():
        reply = r.reply or ""
        # A decline is the more specific diagnosis, so it wins when both are true.
        reason = "declined" if any(p in reply for p in DECLINE_PHRASES) else "no_sources"
        out.append(
            {
                "message": r.message,
                "intent": r.intent,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "reason": reason,
            }
        )
    return out


# ----------------------------------------------------------------- endpoint


@router.get("/api/reports/summary")
async def summary(
    # Bounded in the signature, so 0 and 365 are a 422 from FastAPI rather than a
    # query that scans the whole table or a chart with no bars.
    days: int = Query(default=7, ge=MIN_DAYS, le=MAX_DAYS),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Everything the dashboard draws, for the last `days` days.

    Every key is always present and every number is a number: an empty window
    returns zeros and empty lists, so the page has one code path, not two.
    """
    cutoff = _cutoff(days)
    totals = await _totals(session, cutoff)
    sessions = await _sessions(session, cutoff)
    return {
        "days": days,
        "totals": {
            "turns": totals["turns"],
            "sessions": sessions,
            "cost_usd": totals["cost_usd"],
            "latency_p50_ms": totals["latency_p50_ms"],
            "latency_p95_ms": totals["latency_p95_ms"],
            "error_turns": totals["error_turns"],
            "fallback_turns": totals["fallback_turns"],
        },
        "by_day": await _by_day(session, cutoff),
        "by_intent": await _by_intent(session, cutoff, totals["turns"]),
        "by_tier": await _by_tier(session, cutoff),
        "tools": await _tools(session, cutoff),
        "citation_rate": await _citation_rate(session, cutoff),
        "applications": await _applications(session, cutoff),
        "unanswered": await _unanswered(session, cutoff),
    }
