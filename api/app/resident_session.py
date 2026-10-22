"""Binds a resident `session_id` to the browser that first used it.

Called by app/api/chat.py (both routes), app/api/documents.py and
app/api/applications.py, each before it does any work. Depends on: app.config
for the secret, app.db.models for the two tables that define "first contact",
and app.auth for the Secure-flag rule the staff cookie already follows.

Why an HMAC rather than a stored token: a resident has no account, so the only
thing worth protecting is the conversation behind a guessable id — a session id
that leaks (a screenshot, a shared link, a log line) otherwise hands over the
whole history and any uploads. HMAC-SHA256(session_id, SESSION_SECRET) means
nothing is stored server-side, a restart logs nobody out, and the id alone is
useless without the cookie.
"""

import hashlib
import hmac
import logging

from fastapi import HTTPException, Request, Response
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import cookie_secure_for
from app.config import settings
from app.db import models

log = logging.getLogger(__name__)

#: Separate from `staff_session`: different audience, different lifetime, and a
#: browser can legitimately hold both (a staff member testing the resident chat).
COOKIE_NAME = "resident_session"
#: Long, because losing it means losing a conversation, and it protects nothing
#: a resident did not already type into this browser.
COOKIE_MAX_AGE_S = 30 * 24 * 60 * 60

# The browser mints the id with crypto.randomUUID(); the eval runner and
# smoke.sh mint their own. Lives here rather than in app/api/chat.py because
# three routes now bound the same value.
SESSION_ID_PATTERN = r"^[A-Za-z0-9_-]{8,64}$"

#: One sentence, and it names the remedy: the web client rotates to a fresh id
#: and retries once before the resident ever sees this.
FOREIGN_SESSION = "This conversation belongs to another browser. Start a new conversation."


def mint(session_id: str) -> str:
    """The cookie value for a session id: HMAC-SHA256 under SESSION_SECRET, hex."""
    return hmac.new(
        settings.session_secret.encode("utf-8"),
        session_id.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify(session_id: str, cookie: str | None) -> bool:
    """Constant-time check that `cookie` was minted for exactly this id."""
    if not cookie:
        return False
    return hmac.compare_digest(mint(session_id), cookie)


async def has_history(session: AsyncSession, session_id: str) -> bool:
    """True once this id owns a chat message or an upload — i.e. it is claimed.

    One round trip, two EXISTS: the check runs on every request that arrives
    without a valid cookie, and two queries for a boolean would be two.
    """
    stmt = select(
        or_(
            select(models.ChatMessage.id).where(models.ChatMessage.session_id == session_id).exists(),
            select(models.Document.id).where(models.Document.session_id == session_id).exists(),
        )
    )
    return bool((await session.execute(stmt)).scalar_one())


async def require_or_mint(
    session: AsyncSession, session_id: str, request: Request, response: Response
) -> None:
    """Let this request through, minting the cookie on first contact; else 403.

    Three cases, in the order they are cheapest to decide:

    1. The request carries a cookie minted for this id — the usual one. No
       query at all, and it passes whether or not the id has history yet, so a
       client that retries its very first turn is not punished for it.
    2. No valid cookie and no history — first contact. Mint the cookie onto
       `response`. A *stale* cookie (this browser's previous conversation) lands
       here too and is overwritten, which is what "New conversation" needs.
    3. No valid cookie and history exists — someone else's conversation. 403.

    `response` is whatever object will be returned, because a route that returns
    a Response directly (the SSE stream) never inherits the dependency
    Response's headers, and the cookie has to be on the wire before the body.
    """
    if verify(session_id, request.cookies.get(COOKIE_NAME)):
        return
    if await has_history(session, session_id):
        log.info("refused session '%s': no cookie for an id that is already in use", session_id)
        raise HTTPException(status_code=403, detail=FOREIGN_SESSION)
    response.set_cookie(
        COOKIE_NAME,
        mint(session_id),
        max_age=COOKIE_MAX_AGE_S,
        httponly=True,
        samesite="lax",
        secure=cookie_secure_for(request),
        path="/",
    )
