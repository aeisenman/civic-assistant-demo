"""GET /health and GET /health/deep — is the stack wired, and can it think.

Used by the developer, the README, scripts/smoke.sh and the web health pill.
`/health` is free and anonymous (process, db, s3, kb count); `/health/deep` is
the model probe, staff-only and cached. Depends on: db engine, storage, llm.
"""

import logging
import time

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.auth import require_staff
from app.config import settings
from app.db.engine import SessionLocal
from app.llm.client import Tier, chat, embed
from app.storage import s3

log = logging.getLogger(__name__)

router = APIRouter(tags=["health"])

# How long a deep probe's answer stands. The probe costs a real (tiny) chat call
# and a real embed call, so repeating it per request is spend a caller controls.
DEEP_CACHE_SECONDS = 60
_deep_cache: dict | None = None
_deep_cached_at = 0.0

# Startup steps that failed, filled in by app.main so a half-started process can
# say which box is red instead of crash-looping (audit row 2).
STARTUP_ERRORS: dict[str, str] = {}


def record_startup_error(step: str, exc: BaseException) -> None:
    """Remember one failed startup step; /health reports it and returns 503."""
    STARTUP_ERRORS[step] = f"{type(exc).__name__}: {exc}"


def clear_startup_errors() -> None:
    """Reset between tests, and on a clean startup."""
    STARTUP_ERRORS.clear()


async def _check_db() -> tuple[str, int | None]:
    """Returns (status, kb_chunks count) — the count doubles as an ingest check."""
    try:
        async with SessionLocal() as session:
            await session.execute(text("SELECT 1"))
            count = (await session.execute(text("SELECT count(*) FROM kb_chunks"))).scalar_one()
        return "ok", int(count)
    except Exception as exc:  # noqa: BLE001 - report, never raise
        log.warning("health: db error: %s", exc)
        return "error", None


async def _check_s3() -> str:
    """head_bucket, off the event loop.

    Synchronous boto3 here meant a slow object store froze every in-flight SSE
    stream for as long as the call took — a health check that caused the outage
    it was meant to report.
    """
    try:
        await s3.ahead_bucket()
        return "ok"
    except Exception as exc:  # noqa: BLE001
        log.warning("health: s3 error: %s", exc)
        return "error"


async def _check_llm() -> str:
    """Cheapest possible real call: one token from the SMALL tier."""
    try:
        result = await chat(
            Tier.SMALL,
            [{"role": "user", "content": "ping"}],
            max_tokens=1,
            temperature=0.0,
        )
        return "ok" if result.model else "error"
    except Exception as exc:  # noqa: BLE001
        log.warning("health: llm error: %s", exc)
        return "error"


async def _check_embed() -> str:
    """Embeds one word and checks the width matches the migrated vector column."""
    try:
        vectors = await embed(["ping"])
        if len(vectors) == 1 and len(vectors[0]) == settings.embed_dim:
            return "ok"
        got = len(vectors[0]) if vectors else 0
        log.warning("health: embed dim %d != EMBED_DIM %d", got, settings.embed_dim)
        return "error"
    except Exception as exc:  # noqa: BLE001
        log.warning("health: embed error: %s", exc)
        return "error"


@router.get("/health")
async def health() -> JSONResponse:
    """Process, db, s3 and the KB count. No model call, so it is free to poll.

    It used to make a real chat call and a real embed call on every request,
    which meant an anonymous `while true; curl /health` was unbounded Bedrock
    spend (audit row 1). The model probe moved to /health/deep. A dead db or a
    dead S3 is a 503 with `status: degraded`, because a load balancer should
    take this process out rather than route residents at a broken stack.
    """
    db_status, kb_chunks = await _check_db()
    s3_status = await _check_s3()
    degraded = db_status != "ok" or s3_status != "ok" or bool(STARTUP_ERRORS)
    body = {
        "status": "degraded" if degraded else "ok",
        "db": db_status,
        "s3": s3_status,
        "kb_chunks": kb_chunks,
        "models": settings.models_by_tier,
        # alias -> human model name, so the UI can show "smart · claude-sonnet-4-6".
        "provider_models": settings.llm_provider_models_json,
        # Empty on a clean boot; one entry per startup step that failed, so the
        # app can serve with a red pill instead of crash-looping.
        "startup_errors": dict(STARTUP_ERRORS),
    }
    return JSONResponse(body, status_code=503 if degraded else 200)


@router.get("/health/deep", dependencies=[Depends(require_staff)])
async def health_deep() -> dict:
    """The model and embedding probe: staff-only, and cached for a minute.

    Both halves cost real tokens, so this is the one health answer that is not
    free. Staff-only and cached means the spend is bounded by who can sign in
    and by the clock, not by how fast a stranger can curl.
    """
    global _deep_cache, _deep_cached_at
    now = time.monotonic()
    if _deep_cache is not None and now - _deep_cached_at < DEEP_CACHE_SECONDS:
        return {**_deep_cache, "cached": True, "age_s": round(now - _deep_cached_at, 1)}

    probe = {
        "llm": await _check_llm(),
        "embed": await _check_embed(),
        "models": settings.models_by_tier,
        "provider_models": settings.llm_provider_models_json,
    }
    probe["status"] = "ok" if probe["llm"] == "ok" and probe["embed"] == "ok" else "degraded"
    _deep_cache, _deep_cached_at = probe, now
    return {**probe, "cached": False, "age_s": 0.0}


def clear_deep_cache() -> None:
    """Forget the cached probe — used by the tests, and by a manual re-check."""
    global _deep_cache, _deep_cached_at
    _deep_cache, _deep_cached_at = None, 0.0
