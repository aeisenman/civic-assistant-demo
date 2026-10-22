"""POST /api/auth/login, POST /api/auth/logout, GET /api/auth/me.

Called by web/app/login and by every staff page on load. Depends on app.auth
for hashing, session rows and the throttle. The cookie is HttpOnly so no script
can read it, SameSite=Lax so a third-party page cannot ride it, and Secure
driven by COOKIE_SECURE (unset = derive from the request scheme, which is what
the http://localhost demo needs; behind a TLS proxy the scheme lies, so set it).
"""

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app import auth
from app.db import models
from app.db.engine import get_session

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

#: One message for "no such user" and for "wrong password": a login form must
#: not tell an attacker which usernames exist.
BAD_CREDENTIALS = "Incorrect username or password."


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Sign a staff member in and set the HttpOnly session cookie.

    Rate-limited and delayed on failure: the only credential here is a shared
    demo passcode, so an online guessing run is the realistic attack.
    """
    username = body.username.strip()
    if auth.failures_in_window(username) >= auth.MAX_FAILURES:
        raise HTTPException(status_code=429, detail="Too many sign-in attempts. Try again in a minute.")

    user = await auth.get_user_by_username(session, username)
    if user is None or not auth.verify_password(body.password, user.password_hash):
        auth.record_failure(username)
        # A deliberate pause: it costs an honest typo one second and makes an
        # online guessing run ~1 attempt/second before the 429 kicks in.
        await asyncio.sleep(auth.FAILED_LOGIN_DELAY_S)
        log.info("auth: failed login for '%s'", username)
        raise HTTPException(status_code=401, detail=BAD_CREDENTIALS)

    auth.clear_failures(username)
    token = await auth.create_session(session, user)
    response.set_cookie(
        auth.COOKIE_NAME,
        token,
        max_age=int(auth.SESSION_TTL.total_seconds()),
        httponly=True,
        samesite="lax",
        # One rule for both cookies; see app/auth.py for why it is a tri-state.
        secure=auth.cookie_secure_for(request),
        path="/",
    )
    log.info("auth: '%s' signed in", username)
    return {"display_name": user.display_name, "username": user.username}


@router.post("/logout")
async def logout(request: Request, response: Response, session: AsyncSession = Depends(get_session)) -> dict:
    """Revoke the session server-side as well as dropping the cookie."""
    await auth.revoke_session(session, request.cookies.get(auth.COOKIE_NAME, ""))
    response.delete_cookie(auth.COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me")
async def me(user: models.StaffUser = Depends(auth.require_staff)) -> dict:
    """200 with the display name when signed in, 401 otherwise. The web pages
    call this on load and redirect to /login on a 401."""
    return {"display_name": user.display_name, "username": user.username}
