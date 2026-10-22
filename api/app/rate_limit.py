"""A per-IP token bucket, kept in Postgres so two replicas share one limit.

Used as a FastAPI dependency by app/api/chat.py, documents.py and
applications.py — the three routes a stranger can reach without signing in.
Depends on: app.db.engine (its own short-lived session), app.config for the two
knobs, and the `rate_limits` table from migration 009_runtime.sql.

Why Postgres and not a dict: the hostile review's finding #2 was that every
shared counter in this app is per-process, so `--scale api=2` silently doubles
each ceiling. One `INSERT … ON CONFLICT DO UPDATE … RETURNING` is one round trip
and one atomic read-modify-write, which is exactly what a bucket needs.
"""

import logging
import math

from fastapi import HTTPException, Request
from sqlalchemy import text

from app.config import settings
from app.db.engine import SessionLocal

log = logging.getLogger(__name__)

#: Refill and spend in a single statement.
#:
#: `rate_limits.tokens` on the right-hand side is the *stored* value, so the
#: expression reads as: take what was left, add whatever has accrued since
#: `updated_at`, cap it at the burst size, then spend one.
#:
#: The GREATEST(-1, …) floor is the whole design in one clause. Without a floor
#: a flood drives the balance arbitrarily negative and the caller stays blocked
#: for hours after it stops; with a floor of 0 there is no way to tell "spent the
#: last token" from "had none", because the row looks identical either way. -1
#: means "refused", and it costs a refused caller one token of future allowance,
#: so hammering the endpoint does not get you back in faster.
BUCKET_SQL = text(
    """
    INSERT INTO rate_limits (key, tokens, updated_at)
    VALUES (:key, :capacity - 1, now())
    ON CONFLICT (key) DO UPDATE SET
        tokens = GREATEST(
            -1,
            LEAST(
                :capacity,
                rate_limits.tokens
                    + EXTRACT(EPOCH FROM (now() - rate_limits.updated_at)) * :refill_per_second
            ) - 1
        ),
        updated_at = now()
    RETURNING tokens
    """
)

#: What a throttled caller is told. No numbers in it: the limit is an operational
#: detail, and a resident who typed twice quickly is not an attacker.
TOO_MANY = "Too many requests from this address. Wait a few seconds and try again."


def client_key(request: Request) -> str:
    """The bucket key for this request: the client IP, or "unknown".

    `request.client.host` and not the `X-Forwarded-For` header: uvicorn runs with
    `--proxy-headers` (see the Dockerfile), which means it has *already* rewritten
    `request.client` from the forwarded header when it trusts the hop. Reading the
    raw header here instead would let anyone set their own bucket key by sending
    one, which is a rate limiter that limits nobody.
    """
    client = request.client
    return f"ip:{client.host}" if client and client.host else "ip:unknown"


def retry_after_seconds(tokens: float) -> int:
    """Whole seconds until the bucket holds one token again; never below 1."""
    per_second = settings.rate_limit_per_minute / 60.0
    if per_second <= 0:
        return 60
    return max(1, math.ceil((1.0 - tokens) / per_second))


async def take_token(key: str) -> tuple[bool, float]:
    """Spend one token from `key`'s bucket. Returns (allowed, tokens_left).

    One statement, one round trip, and the arithmetic happens inside Postgres, so
    two replicas racing on the same key serialise on the row rather than on
    nothing at all.
    """
    async with SessionLocal() as session:
        tokens = (
            await session.execute(
                BUCKET_SQL,
                {
                    "key": key,
                    "capacity": float(settings.rate_limit_burst),
                    "refill_per_second": settings.rate_limit_per_minute / 60.0,
                },
            )
        ).scalar_one()
        await session.commit()
    tokens = float(tokens)
    return tokens >= 0, tokens


async def rate_limit(request: Request) -> None:
    """FastAPI dependency: 429 with a Retry-After when this IP is over its rate.

    Opens and closes its own session rather than taking `Depends(get_session)`:
    the streaming route must not hold a pool connection for the life of a
    response (finding #1), and a limiter that needs one would put it straight
    back. A database that is down must not close the front door, so an error
    here logs and lets the request through — the daily cost breaker and the
    per-session turn cap are the ceilings that actually protect the bill.
    """
    if not settings.rate_limit_enabled:
        return
    key = client_key(request)
    try:
        allowed, tokens = await take_token(key)
    except Exception:  # noqa: BLE001 - a broken limiter must not become an outage
        log.warning("rate limit unavailable; allowing %s", key, exc_info=True)
        return
    if not allowed:
        retry = retry_after_seconds(tokens)
        log.info("rate limited %s on %s (retry after %ss)", key, request.url.path, retry)
        raise HTTPException(
            status_code=429,
            detail=TOO_MANY,
            headers={"Retry-After": str(retry)},
        )
