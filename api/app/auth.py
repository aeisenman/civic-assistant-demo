"""Staff passwords, session cookies and the require_staff dependency.

Called by app/api/auth.py (login/logout/me), by the guarded routers
(app/api/applications.py, app/api/traces.py) and by the seed loader, which
upserts the one demo staff user. Depends on: hashlib/secrets/hmac from the
standard library and app.db.models — no new dependency for a demo login.

Why scrypt and not bcrypt/argon2: both would be a new wheel to explain and to
pin, and `hashlib.scrypt` is a memory-hard KDF that ships with CPython.
"""

import hashlib
import hmac
import logging
import secrets
import time
from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, Request
from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import models
from app.db.engine import get_session

log = logging.getLogger(__name__)

COOKIE_NAME = "staff_session"
#: A shift is longer than a demo, and shorter than "forever".
SESSION_TTL = timedelta(hours=12)

# scrypt work factors. n=2**14 costs ~16 MB and ~50 ms on a laptop: enough to
# make a stolen hash expensive, cheap enough that a login feels instant.
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 32
SCRYPT_MAXMEM = 64 * 1024 * 1024

# Wrong-password handling. The delay is a module constant so tests can zero it.
FAILED_LOGIN_DELAY_S = 1.0
MAX_FAILURES = 5
FAILURE_WINDOW_S = 60.0

#: username -> monotonic timestamps of recent failures. In-process on purpose:
#: one API process, and a counter that forgets on restart is fine for a demo.
_failures: dict[str, list[float]] = {}


# --------------------------------------------------------------- passwords


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    """Return `scrypt$n$r$p$salt_hex$key_hex`; the salt travels with the hash."""
    salt = salt if salt is not None else secrets.token_bytes(16)
    key = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=SCRYPT_DKLEN,
        maxmem=SCRYPT_MAXMEM,
    )
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${key.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    """Constant-time check of a password against a stored hash string."""
    try:
        scheme, n, r, p, salt_hex, key_hex = encoded.split("$")
        if scheme != "scrypt":
            return False
        candidate = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(bytes.fromhex(key_hex)),
            maxmem=SCRYPT_MAXMEM,
        )
    except (ValueError, TypeError):
        # A malformed hash is a failed login, not a 500.
        return False
    return hmac.compare_digest(candidate.hex(), key_hex)


# --------------------------------------------------------------- cookie flags


def cookie_secure_for(request: Request) -> bool:
    """Whether a cookie set on this request should carry `Secure`.

    An explicit COOKIE_SECURE wins; otherwise fall back to the scheme the app
    sees. `--proxy-headers` in the Dockerfile makes that scheme honest behind a
    proxy that sets X-Forwarded-Proto, but a proxy that does not set it still
    needs the override. Shared by the staff cookie (app/api/auth.py) and the
    resident one (app/resident_session.py) so the two cannot drift apart.
    """
    if settings.cookie_secure is not None:
        return settings.cookie_secure
    return request.url.scheme == "https"


# ----------------------------------------------------------- session tokens


def new_session_token() -> str:
    """32 random bytes, URL-safe. This value only ever lives in the cookie."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """What we store. sha256 is right here: the token is already high-entropy."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ------------------------------------------------------- login rate limiting


def failures_in_window(username: str, now: float | None = None) -> int:
    """Recent failed logins for `username`, pruning anything older than a minute."""
    now = time.monotonic() if now is None else now
    recent = [t for t in _failures.get(username, []) if now - t < FAILURE_WINDOW_S]
    if recent:
        _failures[username] = recent
    else:
        _failures.pop(username, None)
    return len(recent)


def record_failure(username: str) -> None:
    """Count one bad password, so the next attempt can be slowed or refused."""
    _failures.setdefault(username, []).append(time.monotonic())


def clear_failures(username: str) -> None:
    """Forget a username's failures once it signs in successfully."""
    _failures.pop(username, None)


def reset_failures() -> None:
    """Test helper: forget every counter."""
    _failures.clear()


# ------------------------------------------------------------------ storage


async def get_user_by_username(session: AsyncSession, username: str) -> models.StaffUser | None:
    """The staff row for a username, or None — the caller decides what to say."""
    stmt = select(models.StaffUser).where(models.StaffUser.username == username)
    return (await session.execute(stmt)).scalars().first()


async def create_session(session: AsyncSession, user: models.StaffUser) -> str:
    """Mint a token, store only its hash, and sweep expired rows on the way."""
    token = new_session_token()
    now = datetime.now(UTC)
    await session.execute(delete(models.StaffSession).where(models.StaffSession.expires_at < now))
    await session.execute(
        insert(models.StaffSession).values(
            token_hash=hash_token(token),
            user_id=user.id,
            expires_at=now + SESSION_TTL,
        )
    )
    await session.commit()
    return token


async def resolve_session(session: AsyncSession, token: str) -> models.StaffUser | None:
    """The signed-in user for a cookie value, or None if absent or expired."""
    if not token:
        return None
    stmt = (
        select(models.StaffUser)
        .join(models.StaffSession, models.StaffSession.user_id == models.StaffUser.id)
        .where(
            models.StaffSession.token_hash == hash_token(token),
            models.StaffSession.expires_at > datetime.now(UTC),
        )
    )
    return (await session.execute(stmt)).scalars().first()


async def revoke_session(session: AsyncSession, token: str) -> None:
    """Logout. Unknown tokens are a no-op, so logout is always a 200."""
    if not token:
        return
    await session.execute(
        delete(models.StaffSession).where(models.StaffSession.token_hash == hash_token(token))
    )
    await session.commit()


async def ensure_staff_user(session: AsyncSession) -> models.StaffUser:
    """Upsert the single user named by STAFF_USERNAME; never truncates.

    Called from the seed loader. The password is re-hashed on every startup so
    that editing STAFF_PASSWORD in .env is all it takes to change it, and so the
    stored hash never outlives the environment that produced it.
    """
    username = settings.staff_username
    existing = await get_user_by_username(session, username)
    encoded = hash_password(settings.staff_password)
    if existing is None:
        await session.execute(
            insert(models.StaffUser).values(
                username=username,
                password_hash=encoded,
                display_name=settings.staff_display_name,
            )
        )
    else:
        await session.execute(
            update(models.StaffUser)
            .where(models.StaffUser.id == existing.id)
            .values(password_hash=encoded, display_name=settings.staff_display_name)
        )
    await session.commit()
    user = await get_user_by_username(session, username)
    log.info("seed: staff user '%s' ready", username)
    return user


# --------------------------------------------------------------- dependency


async def require_staff(request: Request, session: AsyncSession = Depends(get_session)) -> models.StaffUser:
    """401 unless the request carries a live staff_session cookie.

    Used as a route dependency by the staff queue and the traces API; the
    resident endpoints (chat, forms, document upload) do not use it.
    """
    user = await resolve_session(session, request.cookies.get(COOKIE_NAME, ""))
    if user is None:
        raise HTTPException(status_code=401, detail="staff sign-in required")
    return user
