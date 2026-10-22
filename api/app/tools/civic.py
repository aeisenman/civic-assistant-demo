"""Civic lookups: city events (seed + live council agendas) and refer-out agencies.

Called through app/tools/registry.py by the events, general and service_request
profiles. Depends on: the events and referrals seed tables and, for real council
meeting agendas, app/live/arcgis.py. Council district moved to app/live/arcgis.py
in M8 so there is exactly one address lookup in the codebase.
"""

import re
from collections.abc import Sequence
from datetime import date

from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import clock
from app.db import models
from app.live import arcgis
from app.live.geocode import escape_like

MAX_EVENTS = 8
MAX_REFERRALS = 3
# Three letters, not four: "dog", "DBA", "EIN" and "gas" are the whole question,
# and the old four-letter floor is half of why "dog license" reached the DMV
# (red-team finding 9). Function words are dropped by name instead, so admitting
# three-letter words does not admit "the" and "and".
MIN_TERM_LETTERS = 3
STOPWORDS = frozenset(
    """the and for are can how who why you your was its has have not but did does
    get got out per this that with from what about""".split()
)
# Longest suffix first, so "licensings" loses "ings" rather than "s".
SUFFIXES = ("ings", "ing", "es", "ed", "s")
MIN_STEM_LETTERS = 4
# A hit in the topic is what the resident actually asked about; a hit in the note
# is context. Weighting them apart is what puts "Dog licensing" above the DMV row
# when someone asks about a dog license (red-team finding 9).
TOPIC_WEIGHT = 2
NOTE_WEIGHT = 1


class SearchEventsArgs(BaseModel):
    query: str | None = Field(default=None, description="Words to match in the title or description")
    date_from: str | None = Field(default=None, description="ISO start date; defaults to today")
    date_to: str | None = Field(default=None, description="ISO end date")
    department: str | None = Field(default=None, description="Owning department, e.g. Library")


class ReferralArgs(BaseModel):
    topic: str = Field(description="What the resident asked about, e.g. 'dog license'")


def _parse_date(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def _matches(event: dict, args: SearchEventsArgs, start: date, end: date | None) -> bool:
    """The same filters the SQL applies, for the live rows that never touch SQL."""
    when = event.get("date")
    if when and when < start.isoformat():
        return False
    if end and when and when > end.isoformat():
        return False
    if args.query and args.query.strip().lower() not in (event.get("title") or "").lower():
        return False
    if args.department:
        return args.department.strip().lower() in (event.get("department") or "").lower()
    return True


async def search_events(args: SearchEventsArgs, session: AsyncSession) -> dict:
    """Upcoming events matching the filters, soonest first, at most eight.

    Seed rows are the fictional markets and library programs; the council
    meeting agendas are merged in live from the City's Granicus feed, so
    "when is the next council meeting" answers from the real calendar.
    """
    # Default to today: residents asking "what's on" never mean last month.
    start = _parse_date(args.date_from) or clock.today()
    stmt = select(models.Event).where(models.Event.date >= start)
    end = _parse_date(args.date_to)
    if end:
        stmt = stmt.where(models.Event.date <= end)
    if args.query:
        # escape_like: search_events(query="%") used to match every row and answer
        # as if the resident's word had been found. Same fix as geocode.py.
        like = f"%{escape_like(args.query.strip())}%"
        stmt = stmt.where(
            or_(
                models.Event.title.ilike(like, escape="\\"),
                models.Event.description.ilike(like, escape="\\"),
            )
        )
    if args.department:
        stmt = stmt.where(
            models.Event.department.ilike(f"%{escape_like(args.department.strip())}%", escape="\\")
        )
    rows = (await session.execute(stmt.order_by(models.Event.date).limit(MAX_EVENTS))).scalars().all()

    events = [
        {
            "title": e.title,
            "date": e.date.isoformat() if e.date else None,
            "start_time": e.start_time,
            "end_time": e.end_time,
            "location": e.location,
            "department": e.department,
            "cost": e.cost,
            "url": e.url,
            "source": "seed",
        }
        for e in rows
    ]
    live = [a for a in await arcgis.council_agendas() if _matches(a, args, start, end)]
    events = sorted(events + live, key=lambda e: e["date"] or "9999-12-31")[:MAX_EVENTS]
    if not events:
        message = "I found no events matching that in the City calendar."
        return {"events": [], "count": 0, "summary": message}
    lines = [
        f"{e['title']} on {e['date']} {e['start_time'] or ''}-{e['end_time'] or ''} at "
        f"{e['location']} ({e['cost']})".strip()
        + (" [live City agenda]" if e.get("source") == "live" else "")
        for e in events
    ]
    return {
        "events": events,
        "count": len(events),
        "searched_from": start.isoformat(),
        "live_agendas": sum(1 for e in events if e.get("source") == "live"),
        "summary": "Upcoming: " + "; ".join(lines),
    }


def stem(word: str) -> str:
    """Crudest useful stemmer: one plural/participle suffix, then a trailing -e.

    "dog license" used to miss the row "Dog licensing" entirely — the substring
    "license" is not in "licensing" — and the resident got the DMV instead
    (red-team finding 9). A real stemmer would be a dependency; this handles the
    only inflections a referral topic actually shows. A suffix is only removed
    when at least MIN_STEM_LETTERS letters remain, so "does" does not become "do".
    """
    for suffix in SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= MIN_STEM_LETTERS:
            word = word[: -len(suffix)]
            break
    if word.endswith("e") and len(word) - 1 >= MIN_STEM_LETTERS:
        word = word[:-1]
    return word


def referral_terms(topic: str) -> list[str]:
    """Stems of the significant words, lowercased, de-duplicated, order kept.

    A whole-phrase ILIKE missed "restaurant health permit" against the row
    "Food facility health permit", so we match word by word instead. Function
    words ("a", "my", "for") match everything, so they are dropped; if nothing
    survives, the caller falls back to the phrase. The stems are what
    get_referral puts in its ILIKE patterns, so `%licens%` finds both
    "license" and "licensing" in the database as well as in rank_referrals.
    """
    seen: list[str] = []
    for word in re.findall(r"[a-z0-9]+", topic.lower()):
        if len(word) < MIN_TERM_LETTERS or word in STOPWORDS:
            continue
        stemmed = stem(word)
        if stemmed not in seen:
            seen.append(stemmed)
    return seen


def _stems(text: str) -> set[str]:
    """The stemmed word set of one column, for whole-word matching."""
    return {stem(word) for word in re.findall(r"[a-z0-9]+", (text or "").lower())}


def rank_referrals(rows: Sequence, terms: list[str]) -> list:
    """Rows that matched at least one term, best score first, ties by seed order.

    `terms` are the stems referral_terms produced — they are not stemmed again
    here, because stemming twice would grind "licens" down to "licen". The topic
    is the column the resident's words are actually about, so a hit there counts
    double; a hit in the agency name or the explanatory note counts once. That is
    what puts "Dog licensing" above a row whose note merely mentions licences.
    """
    scored = []
    for position, row in enumerate(rows):
        topic_stems = _stems(row.topic)
        other_stems = _stems(f"{row.agency} {row.note or ''}")
        score = 0
        for term in terms:
            if term in topic_stems:
                score += TOPIC_WEIGHT
            elif term in other_stems:
                score += NOTE_WEIGHT
        if score:
            scored.append((-score, position, row))
    return [row for _, _, row in sorted(scored, key=lambda s: (s[0], s[1]))]


async def get_referral(args: ReferralArgs, session: AsyncSession) -> dict:
    """Which other agency handles something the City does not."""
    terms = referral_terms(args.topic) or [args.topic.strip().lower()]
    clauses = []
    for term in terms:
        like = f"%{escape_like(term)}%"
        clauses += [
            models.Referral.topic.ilike(like, escape="\\"),
            models.Referral.agency.ilike(like, escape="\\"),
            models.Referral.note.ilike(like, escape="\\"),
        ]
    candidates = (await session.execute(select(models.Referral).where(or_(*clauses)))).scalars().all()
    rows = rank_referrals(candidates, terms)[:MAX_REFERRALS]
    if not rows:
        message = (
            f"I don't have a referral on file for '{args.topic}'. The City's general "
            "information line is 619-236-5555."
        )
        return {"referrals": [], "summary": message}
    referrals = [{"topic": r.topic, "agency": r.agency, "url": r.url, "note": r.note} for r in rows]
    return {
        "referrals": referrals,
        "summary": "; ".join(f"{r['topic']}: {r['agency']} — {r['url']} ({r['note']})" for r in referrals),
    }
