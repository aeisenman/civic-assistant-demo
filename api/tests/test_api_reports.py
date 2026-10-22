"""The reports endpoint: its shape, its bounds, its guard and its SQL.

Drives the FastAPI app with starlette's TestClient over a fake session that
answers app/api/reports.py's eleven aggregates in order and keeps the SQL it was
asked, so the shaping can be asserted with no Postgres and no model. Depends on:
app.main, app.api.reports, app.auth and app.db.engine.get_session.
"""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from app import auth
from app.api import reports
from app.db.engine import get_session
from app.main import app


class Row:
    """A stand-in for a SQLAlchemy Row: the code only reads named attributes."""

    def __init__(self, **kw):
        self.__dict__.update(kw)


class Result:
    """What `session.execute(...)` returns. One canned value, three accessors."""

    def __init__(self, value):
        self._value = value

    def all(self):
        return self._value

    def one(self):
        return self._value

    def scalar(self):
        return self._value


class FakeSession:
    """Answers the report queries in the order `summary()` runs them.

    Recording the compiled SQL is half the point: the tool breakdown has to be
    done in Postgres rather than by paging rows into Python, and the only way to
    assert that without a database is to read the statement.
    """

    def __init__(self, answers):
        self.answers = list(answers)
        self.sql: list[str] = []

    async def execute(self, statement, *args, **kwargs):
        assert self.answers, "summary() ran more queries than this fake answers"
        self.sql.append(str(statement.compile(dialect=postgresql.dialect())))
        return Result(self.answers.pop(0))


NOW = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)


def populated_answers():
    """One answer per query, in the order summary() asks them. A function rather
    than a constant so each test pops from its own list."""
    return [
        Row(turns=10, cost_usd=0.1234, p50=900.0, p95=2400.0, error_turns=1, fallback_turns=2),
        4,  # distinct chat sessions
        [Row(day=NOW.date(), turns=10, cost_usd=0.1234, p95=2400.0)],
        [Row(intent="trash", turns=6), Row(intent="permits", turns=4)],
        [Row(tier="fast", turns=7, cost_usd=0.01), Row(tier="smart", turns=3, cost_usd=0.11)],
        [Row(name="get_trash_schedule", calls=4, errors=1, live=2)],
        Row(turns=9, cited=6),
        [Row(type="permit", status="issued", count=2)],
        3.25,  # median hours submitted -> in_review
        Row(issued=2, needs_info=1),
        [
            Row(
                message="Can I keep chickens?",
                intent="general",
                reply="I do not have that. Call 619-236-5555.",
                created_at=NOW,
            ),
            Row(message="Is the pool open?", intent="general", reply="Probably.", created_at=NOW),
        ],
    ]


def empty_answers():
    """What an untouched demo database returns: no rows anywhere."""
    return [
        Row(turns=0, cost_usd=None, p50=None, p95=None, error_turns=0, fallback_turns=0),
        0,
        [],
        [],
        [],
        [],
        Row(turns=0, cited=0),
        [],
        None,
        Row(issued=0, needs_info=0),
        [],
    ]


@pytest.fixture
def db():
    """Mutable holder so a test can swap the answers before the request runs."""
    return FakeSession(populated_answers())


@pytest.fixture
def client(db):
    """No `with`: entering the context would run the lifespan and its migrations."""

    async def _fake_session():
        yield db

    app.dependency_overrides[get_session] = _fake_session
    app.dependency_overrides[auth.require_staff] = lambda: object()
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def anonymous(db):
    """The same app with the staff guard left in place."""

    async def _fake_session():
        yield db

    app.dependency_overrides[get_session] = _fake_session
    yield TestClient(app)
    app.dependency_overrides.clear()


# ------------------------------------------------------------------- guard


def test_the_summary_is_staff_only(anonymous):
    res = anonymous.get("/api/reports/summary")
    assert res.status_code == 401
    assert "sign-in" in res.json()["detail"]


# ------------------------------------------------------------------ bounds


@pytest.mark.parametrize("days", [0, -1, 91, 365])
def test_a_window_outside_one_to_ninety_days_is_a_422(client, days):
    assert client.get(f"/api/reports/summary?days={days}").status_code == 422


@pytest.mark.parametrize("days", [1, 7, 90])
def test_the_window_bounds_themselves_are_accepted(db, client, days):
    db.answers = populated_answers()
    res = client.get(f"/api/reports/summary?days={days}")
    assert res.status_code == 200
    assert res.json()["days"] == days


def test_the_default_window_is_seven_days(client):
    assert client.get("/api/reports/summary").json()["days"] == 7


# ------------------------------------------------------------------- shape


def test_every_key_is_present_and_typed(client):
    body = client.get("/api/reports/summary?days=7").json()

    assert set(body) == {
        "days",
        "totals",
        "by_day",
        "by_intent",
        "by_tier",
        "tools",
        "citation_rate",
        "applications",
        "unanswered",
    }
    assert set(body["totals"]) == {
        "turns",
        "sessions",
        "cost_usd",
        "latency_p50_ms",
        "latency_p95_ms",
        "error_turns",
        "fallback_turns",
    }
    assert body["totals"] == {
        "turns": 10,
        "sessions": 4,
        "cost_usd": 0.1234,
        "latency_p50_ms": 900,
        "latency_p95_ms": 2400,
        "error_turns": 1,
        "fallback_turns": 2,
    }
    assert body["by_day"] == [{"date": "2026-09-15", "turns": 10, "cost_usd": 0.1234, "latency_p95_ms": 2400}]
    # share is the fraction of the window's turns, computed from the same total.
    assert body["by_intent"] == [
        {"intent": "trash", "turns": 6, "share": 0.6},
        {"intent": "permits", "turns": 4, "share": 0.4},
    ]
    assert body["by_tier"][0] == {"tier": "fast", "turns": 7, "cost_usd": 0.01}
    assert body["tools"] == [{"name": "get_trash_schedule", "calls": 4, "errors": 1, "live_share": 0.5}]
    assert body["citation_rate"] == round(6 / 9, 4)
    assert body["applications"] == {
        "by_type_status": [{"type": "permit", "status": "issued", "count": 2}],
        "median_hours_to_review": 3.25,
        "issued": 2,
        "needs_info": 1,
    }


def test_the_unanswered_list_says_which_kind_of_miss_it_was(client):
    rows = client.get("/api/reports/summary").json()["unanswered"]
    assert [r["reason"] for r in rows] == ["declined", "no_sources"]
    assert rows[0]["message"] == "Can I keep chickens?"
    assert rows[0]["created_at"].startswith("2026-09-15")
    assert set(rows[0]) == {"message", "intent", "created_at", "reason"}


def test_an_empty_window_still_answers_with_every_key_and_no_nulls(db, client):
    db.answers = empty_answers()
    body = client.get("/api/reports/summary?days=30").json()

    assert body["totals"] == {
        "turns": 0,
        "sessions": 0,
        "cost_usd": 0.0,
        "latency_p50_ms": 0,
        "latency_p95_ms": 0,
        "error_turns": 0,
        "fallback_turns": 0,
    }
    assert body["by_day"] == body["by_intent"] == body["by_tier"] == []
    assert body["tools"] == body["unanswered"] == []
    assert body["citation_rate"] == 0.0
    # None, not 0.0: nothing reached review, which is not "it took no time".
    assert body["applications"]["median_hours_to_review"] is None


# --------------------------------------------------------------------- SQL


def test_the_tool_breakdown_is_done_in_postgres_with_jsonb_functions(db, client):
    client.get("/api/reports/summary")
    tools_sql = [q for q in db.sql if "jsonb_array_elements" in q]
    assert len(tools_sql) == 1, "exactly one query should unnest tool_calls"
    sql = tools_sql[0]
    # The lateral must follow `traces`: a set-returning function may only
    # reference a FROM entry to its left.
    assert "FROM traces, jsonb_array_elements(traces.tool_calls) AS call" in sql
    # `?` is a bind marker for several drivers, so the function spelling is used.
    assert "jsonb_exists(call" in sql
    assert "GROUP BY call ->>" in sql


def test_the_percentiles_are_computed_by_postgres_not_by_python(db, client):
    client.get("/api/reports/summary")
    sql = "\n".join(db.sql)
    assert "percentile_cont" in sql and "WITHIN GROUP (ORDER BY traces.latency_ms)" in sql
    # Median time to review comes out of application_events, not applications.
    assert "FROM application_events" in sql


def test_the_four_tables_the_dashboard_reports_on_are_all_queried(db, client):
    client.get("/api/reports/summary")
    sql = "\n".join(db.sql)
    for table in ("traces", "chat_messages", "applications", "application_events"):
        assert f"FROM {table}" in sql, f"{table} is never read"


def test_the_decline_family_matches_the_eval_scorers():
    """The phrase list is copied from evals/run.py; this is the copy's tripwire."""
    from evals.run import PROMPT_CONSTANTS

    assert set(reports.DECLINE_PHRASES) <= set(PROMPT_CONSTANTS)
    assert "619-236-5555" in reports.DECLINE_PHRASES
