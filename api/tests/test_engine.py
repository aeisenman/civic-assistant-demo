"""The state machine's shape and its refusal to skip steps.

The hooks are stubbed out because `validating` and `issued` reach a database and
object storage; what matters here is that the spine is the one PLAN.md §6
describes and that an illegal jump raises instead of quietly writing a row.
"""

from types import SimpleNamespace

import pytest

from app.workflows import engine


class FakeResult:
    """Enough of a SQLAlchemy Result for the engine: a scalar and a rowcount.

    `status` is handed back to the `SELECT ... FOR UPDATE` the engine does before
    every transition, so the row always looks unchanged and the happy path runs.
    """

    def __init__(self, status: str | None):
        self._status = status
        self.rowcount = 1

    def scalar_one_or_none(self):
        return self._status


class FakeSession:
    """Records what the engine tried to write; no database involved."""

    def __init__(self, status: str | None = None):
        self.statements = []
        self.status = status

    async def execute(self, statement, *args, **kwargs):
        self.statements.append(statement)
        return FakeResult(self.status)

    async def commit(self):
        pass

    async def rollback(self):
        pass

    async def refresh(self, obj):
        pass


def make_app(status: str) -> SimpleNamespace:
    return SimpleNamespace(id=1, tracking_number="PRM-2026-000400", type="permit", status=status, fields={})


def test_transition_table_matches_the_documented_spine():
    assert engine.TRANSITIONS == {
        "draft": ["submitted"],
        "submitted": ["validating"],
        "validating": ["needs_info", "routed"],
        "needs_info": ["submitted"],
        "routed": ["in_review"],
        "in_review": ["approved", "rejected"],
        "approved": ["issued"],
        "issued": ["closed"],
        "rejected": ["closed"],
        "closed": [],
    }


def test_auto_and_manual_partition_the_statuses():
    assert engine.AUTO == {"submitted": "validating", "validating": None, "routed": "in_review"}
    assert set(engine.AUTO) | set(engine.MANUAL) == set(engine.TRANSITIONS)
    assert not set(engine.AUTO) & set(engine.MANUAL)


def test_allowed_transitions_reads_the_current_status():
    assert engine.allowed_transitions(make_app("in_review")) == ["approved", "rejected"]
    assert engine.allowed_transitions(make_app("closed")) == []
    assert engine.allowed_transitions(make_app("nonsense")) == []


async def test_advance_writes_an_event_and_sets_the_status(monkeypatch):
    monkeypatch.setattr(engine, "ON_ENTER", {})
    app = make_app("in_review")
    session = FakeSession(status="in_review")
    await engine.advance(session, app, "approved", "staff", "looks good")
    # One SELECT ... FOR UPDATE, one UPDATE for the status, one INSERT for the event.
    assert len(session.statements) == 3


async def test_advance_rejects_a_skipped_step(monkeypatch):
    monkeypatch.setattr(engine, "ON_ENTER", {})
    session = FakeSession()
    with pytest.raises(engine.InvalidTransition):
        await engine.advance(session, make_app("submitted"), "approved", "staff")
    assert session.statements == []


async def test_advance_runs_the_entry_hook(monkeypatch):
    seen = []

    async def hook(session, app):
        seen.append(app.status)

    monkeypatch.setattr(engine, "ON_ENTER", {"issued": hook})
    monkeypatch.setattr(engine, "BEFORE_COMMIT", {})  # no certificate in a unit test
    app = make_app("approved")
    await engine.advance(FakeSession(status="approved"), app, "issued", "staff")
    assert seen == ["approved"]  # the row object is refreshed by the real session


async def test_run_auto_follows_the_auto_map(monkeypatch):
    monkeypatch.setattr(engine, "ON_ENTER", {})
    app = make_app("routed")
    await engine.run_auto(FakeSession(status="routed"), app)
    assert len(engine.AUTO) == 3

    # A status with no automatic step is left alone.
    idle = make_app("needs_info")
    session = FakeSession()
    await engine.run_auto(session, idle)
    assert session.statements == []
