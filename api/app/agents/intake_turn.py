"""The two chat turns that are workflow, not Q&A: a file drop and a gap-fill.

Called by app/agents/chat.handle_chat before the normal flow; returns None when
the turn is ordinary so chat.py falls through unchanged. Depends on:
app.workflows.intake (detect + extract), app.workflows.engine (status changes)
and app.agents.rendering (the reply templates). The replies here are templated,
not generated: the engine already knows the tracking number and the fee.
"""

import asyncio
import logging
import time

import httpx
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SATimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.rendering import (
    application_reply,
    intake_failed_reply,
    unknown_document_reply,
    unreadable_document_reply,
)
from app.db import models
from app.llm.client import TraceCollector, model_for, reset_trace, set_trace
from app.llm.router import Tier
from app.workflows import engine, intake

log = logging.getLogger(__name__)

# Failures that are the *infrastructure's*, not the document's. The templated
# "I couldn't file that" reply used to cover these too, so a resident whose
# permit was never attempted — because the pool timed out, or the gateway was
# unreachable — was told their filing had failed, and the request came back a
# 200 so nothing alerted. The reviewer hit exactly this: a QueuePool TimeoutError
# swallowed into an apology. Re-raised, these reach app/agents/chat.py, which
# turns them into the fallback reply *and* records the error on the trace.
INFRASTRUCTURE_ERRORS = (
    OperationalError,  # connection dropped, server restarting
    SATimeoutError,  # QueuePool limit reached
    asyncio.TimeoutError,  # any wait_for we or the SDK imposed
    httpx.TransportError,  # connect/read/pool errors talking to the gateway
)

# Which intent a workflow turn is recorded under, so /traces stays comparable.
INTENT_BY_TYPE = {
    "permit": "permits",
    "business_tax": "business",
    "service_request": "service_request",
    # There is no `housing` intent: housing questions (short-term rentals, ADUs,
    # tenant help) are handled by the `general` profile, so a STRO filing is
    # recorded under the intent a resident's STRO question would route to.
    "stro": "general",
}


def _actions(apps: list[models.Application]) -> list[dict]:
    return [
        {
            # "type" is the M3 contract; "action" keeps the M2 shape the UI
            # already switches on for tool-created applications.
            "type": "application_created",
            "action": "application_created",
            "tracking_number": app.tracking_number,
            "status": app.status,
            "department": app.department,
        }
        for app in apps
    ]


async def _validate_now(session: AsyncSession, app: models.Application) -> models.Application:
    """Run submitted -> validating inline so the reply can already say what's missing.

    The worker would do this within three seconds, but a resident who just
    uploaded a form should not watch a blank status.
    """
    if app.status == "submitted":
        await engine.advance(session, app, "validating", "system", "validated at intake")
    return app


async def _documents(session: AsyncSession, document_ids: list[int]) -> list[models.Document]:
    rows = []
    for doc_id in document_ids:
        doc = await session.get(models.Document, doc_id)
        if doc is None:
            log.warning("intake: no document %s", doc_id)
            continue
        rows.append(doc)
    return rows


async def _handle_documents(
    session: AsyncSession, session_id: str, document_ids: list[int]
) -> tuple[str, list[models.Application], str | None]:
    """Detect, extract and submit each upload; returns (reply, apps, app_type)."""
    parts: list[str] = []
    apps: list[models.Application] = []
    last_type: str | None = None
    for doc in await _documents(session, document_ids):
        if not doc.text:
            parts.append(unreadable_document_reply(doc.filename))
            continue
        app, app_type = await intake.submit_from_document(session, doc, session_id)
        if app is None:
            parts.append(unknown_document_reply(doc.filename))
            continue
        await _validate_now(session, app)
        apps.append(app)
        last_type = app_type
        parts.append(application_reply(app, extracted=app.fields))
    if not parts:
        parts.append("I couldn't find the file you attached — please try uploading it again.")
    return "\n\n".join(parts), apps, last_type


async def handle_intake_turn(
    session: AsyncSession, session_id: str, message: str, document_ids: list[int]
) -> dict | None:
    """Return a chat payload for a workflow turn, or None to fall through.

    A turn that is *not* intake returns None and chat.py answers it normally; a
    turn that is intake and then fails on the *document* — unreadable text, an
    extraction that produced nothing, a field the validator rejects — returns a
    templated apology, because falling through would answer "did you get my
    permit application?" with general advice about permits and never mention
    that filing failed.

    Infrastructure failures are re-raised instead (INFRASTRUCTURE_ERRORS). "I
    could not file that document" is a statement about the document, and saying
    it when the database was simply unreachable is a lie that also hides an
    outage behind a 200.
    """
    started = time.perf_counter()
    collector = TraceCollector()
    token = set_trace(collector)
    failure: str | None = None
    try:
        if document_ids:
            reply, apps, app_type = await _handle_documents(session, session_id, document_ids)
        else:
            pending = await engine.latest_for_session(session, session_id, "needs_info")
            if pending is None:
                return None
            app = await intake.fill_missing_from_message(session, pending, message)
            await _validate_now(session, app)
            reply, apps, app_type = application_reply(app), [app], app.type
    except INFRASTRUCTURE_ERRORS:
        # `finally` below still resets the trace contextvar on the way out.
        log.exception("intake turn hit an infrastructure failure for session %s", session_id)
        raise
    except Exception as exc:  # noqa: BLE001 - any failure still owes the resident a reply
        log.exception("intake turn failed for session %s", session_id)
        failure = f"{type(exc).__name__}: {exc}"
        reply, apps, app_type = intake_failed_reply(), [], None
    finally:
        reset_trace(token)

    totals = collector.totals
    intent = INTENT_BY_TYPE.get(app_type or "", "general")
    return {
        "reply": reply,
        "citations": [],
        "actions": _actions(apps),
        "trace": {
            "session_id": session_id,
            "message": message,
            "reply": reply,
            "intent": intent,
            "confidence": 1.0,
            "tier": Tier.EXTRACT.value,
            "model": model_for(Tier.EXTRACT),
            "reason": (
                "intake failed"
                if failure
                else ("document intake" if document_ids else "supplying missing fields")
            ),
            "error": failure,
            "rag_chunk_ids": [],
            "tool_calls": [],
            "calls": collector.calls,
            "document_ids": document_ids,
            "prompt_tokens": totals["prompt_tokens"],
            "completion_tokens": totals["completion_tokens"],
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "cost_usd": totals["cost_usd"],
        },
    }
