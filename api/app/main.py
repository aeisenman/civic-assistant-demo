"""FastAPI app factory and startup sequence for the municipality agent.

Entry point for the container (`uvicorn app.main:app`). Startup order matters:
migrations create the schema, then the S3 bucket, then seed data. Depends on:
app.db, app.storage, app.api. CORS names the web origin explicitly (WEB_ORIGIN)
because the staff session is a cookie and a wildcard cannot carry credentials.
"""

import asyncio
import contextlib
import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api import applications, auth, chat, documents, forms, health, reports, traces
from app.config import settings
from app.db.migrations import run_migrations
from app.rag.ingest import ingest_kb
from app.seed.loader import seed_all
from app.storage import s3
from app.workflows.worker import run_forever

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")
access_log = logging.getLogger("app.access")

REQUEST_ID_HEADER = "X-Request-ID"


async def _startup_step(name: str, coro_or_call) -> None:
    """Run one startup step; a failure is logged and reported, never fatal.

    The lifespan used to be a straight line, so a dead SeaweedFS or a Bedrock
    credential problem during KB ingest aborted startup and the container
    crash-looped — and /health, the thing built to say which box is red, was
    never reachable (audit row 2). Now the app serves and /health is 503.
    """
    try:
        result = coro_or_call()
        if asyncio.iscoroutine(result):
            await result
    except Exception as exc:  # noqa: BLE001 - a red box beats a crash loop
        log.exception("startup: %s failed", name)
        health.record_startup_error(name, exc)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Bring the stack up in dependency order, then hand over to uvicorn."""
    health.clear_startup_errors()

    log.info("startup: applying migrations")
    await _startup_step("migrations", run_migrations)

    log.info("startup: ensuring S3 bucket %s", settings.s3_bucket)
    await _startup_step("s3_bucket", s3.ensure_bucket)

    if settings.seed_on_startup:
        log.info("startup: loading seed data")
        await _startup_step("seed", seed_all)
    else:
        log.info("startup: SEED_ON_STARTUP=false, skipping seed")

    if settings.ingest_kb_on_startup:
        # No-op once kb_chunks is populated; `python -m app.rag.ingest --force` re-runs it.
        log.info("startup: ingesting knowledge base")

        async def _ingest() -> None:
            counts = await ingest_kb()
            log.info("startup: kb ingest %s", counts or "already populated")

        await _startup_step("kb_ingest", _ingest)
    else:
        log.info("startup: INGEST_KB_ON_STARTUP=false, skipping kb ingest")

    worker: asyncio.Task | None = None
    if settings.worker_enabled:
        # One asyncio task in this process: no broker, no second container.
        worker = asyncio.create_task(run_forever(settings.worker_interval_seconds))
    else:
        log.info("startup: WORKER_ENABLED=false, workflow worker not started")

    if health.STARTUP_ERRORS:
        log.error("startup: serving with failures: %s", health.STARTUP_ERRORS)
    log.info("startup: ready on :8080")
    yield
    if worker is not None:
        worker.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await worker
    log.info("shutdown")


def create_app() -> FastAPI:
    """Build the app: CORS, then every router. A function so tests can build their own."""
    app = FastAPI(title="City of San Diego — Municipality Agent API", lifespan=lifespan)
    # The staff session is a cookie, and a browser refuses to send credentials to
    # a wildcard origin — so WEB_ORIGIN names the exact origin(s) allowed.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.web_origins,
        allow_credentials=True,
        # Explicit lists, not "*" (audit finding 16). With allow_credentials the
        # two together are the whole cross-origin authority of this API, so they
        # name exactly what the web app sends: no PUT, no PATCH, and no header
        # the client does not actually set. A typo'd WEB_ORIGIN is then a much
        # smaller blast radius than "everything, with your session cookie".
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type", "X-Request-ID", "Idempotency-Key"],
        # So a browser can read the id off a failed request and quote it to us.
        expose_headers=[REQUEST_ID_HEADER],
    )

    @app.middleware("http")
    async def request_id(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        """Stamp every request with an id, log one access line, echo the header.

        A resident or a reviewer reporting "it said something went wrong" has
        nothing to hand us today. With this, the id on the response is the id in
        the log line, and the chat routes attach the traces row id to it, so one
        grep joins the complaint to the turn that caused it.
        """
        incoming = request.headers.get(REQUEST_ID_HEADER, "")
        # Only accept a client-supplied id that looks like one: it goes in a log.
        rid = incoming if incoming.isalnum() and len(incoming) <= 64 else uuid.uuid4().hex
        request.state.request_id = rid
        request.state.trace_id = None
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            access_log.exception(
                "%s %s -> 500 in %dms rid=%s",
                request.method,
                request.url.path,
                int((time.perf_counter() - started) * 1000),
                rid,
            )
            raise
        ms = int((time.perf_counter() - started) * 1000)
        trace_id = getattr(request.state, "trace_id", None)
        access_log.info(
            "%s %s -> %d in %dms rid=%s trace=%s",
            request.method,
            request.url.path,
            response.status_code,
            ms,
            rid,
            trace_id if trace_id is not None else "-",
        )
        response.headers[REQUEST_ID_HEADER] = rid
        return response

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(chat.router)
    app.include_router(traces.router)
    app.include_router(reports.router)
    app.include_router(forms.router)
    app.include_router(documents.router)
    app.include_router(applications.router)
    return app


app = create_app()
