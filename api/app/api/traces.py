"""GET /api/traces — what the model did, for the traces page and for debugging.

Reads the rows written by app/agents/chat.py. Depends on: app.db.engine,
app.db.models and app.auth (staff only). Newest first, because the interesting
trace is the last one.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_staff
from app.db import models
from app.db.engine import get_session

# Traces contain every resident message and reply, so the whole router is behind
# the staff session (M11). The chat page still shows its own turn's trace: that
# arrives inside the /api/chat response body, not from here.
router = APIRouter(tags=["traces"], dependencies=[Depends(require_staff)])

MAX_LIMIT = 500


def _as_dict(trace: models.Trace) -> dict:
    return {column.name: getattr(trace, column.name) for column in models.Trace.__table__.columns}


@router.get("/api/traces")
async def list_traces(
    # Bounded in the signature: a negative limit reached Postgres as LIMIT -1 and
    # came back a 500, and an unbounded one would page the whole table into memory.
    limit: int = Query(default=100, ge=1, le=MAX_LIMIT),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """The trace table, newest first — the page that shows how an answer was made."""
    rows = (
        (await session.execute(select(models.Trace).order_by(desc(models.Trace.id)).limit(limit)))
        .scalars()
        .all()
    )
    return [_as_dict(t) for t in rows]


@router.get("/api/traces/{trace_id}")
async def get_trace(trace_id: int, session: AsyncSession = Depends(get_session)) -> dict:
    """One trace in full, including the tool arguments the list view truncates."""
    trace = (await session.execute(select(models.Trace).where(models.Trace.id == trace_id))).scalars().first()
    if trace is None:
        raise HTTPException(status_code=404, detail=f"no trace {trace_id}")
    return _as_dict(trace)
