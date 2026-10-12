"""Auth routes. Spec 02. Routers are thin: parse, call service, serialise."""

from __future__ import annotations

import base64
import time

from fastapi import APIRouter, Depends, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db
from app.dependencies import (
    SESSION_COOKIE,
    encode_cookie,
    get_current_session,
    require_csrf,
)
from app.errors import BadRequest, TooManyRequests
from app.models import Session
from app.schemas import LoginRequest, MagicLinkRequest, RegisterRequest
from app.serializers import user_private
from app.services import auth as auth_svc
from app.services.mailer import send_magic_link

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


# ─── Throttling ──────────────────────────────────────────────────────────────
#
# ponytail: in-process fixed window, keyed by (endpoint, normalised email). One
# uvicorn worker is already a hard requirement here (see the WebSocket registry
# in realtime.py), so a shared counter would buy nothing. Per-email rather than
# per-IP because the threat this answers is hammering ONE account and mailing a
# victim repeatedly — both need a cap on one key, and per-IP would also have
# meant every integration test shares one budget.
#
# Upgrade path if the worker count ever changes: Redis INCR with a TTL, keyed
# the same way. The call sites would not move.
_WINDOW_SECONDS = 60.0
_attempts: dict[str, list[float]] = {}

# Keys are pruned only when that exact key comes back, so a stream of distinct
# emails would otherwise grow this dict forever. Sweep once it gets big enough
# to matter rather than on every request.
_SWEEP_AT = 512

LOGIN_LIMIT = 20
MAGIC_LINK_LIMIT = 5


def _throttle(key: str, limit: int) -> None:
    now = time.monotonic()
    recent = [t for t in _attempts.get(key, ()) if now - t < _WINDOW_SECONDS]
    if len(recent) >= limit:
        _attempts[key] = recent
        raise TooManyRequests()
    recent.append(now)
    _attempts[key] = recent
    if len(_attempts) > _SWEEP_AT:
        for stale in [k for k, ts in _attempts.items() if not ts or now - ts[-1] >= _WINDOW_SECONDS]:
            del _attempts[stale]


def set_session_cookie(response, token: bytes) -> None:
    settings = get_settings()
    response.set_cookie(
        SESSION_COOKIE,
        encode_cookie(token),
        httponly=True,           # XSS cannot read it. Do not remove.
        samesite="lax",
        secure=settings.app_env == "production",
        path="/",
        max_age=settings.session_days * 24 * 3600,
    )


@router.post("/register", status_code=201)
async def register(
    payload: RegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    user = await auth_svc.register_user(
        db,
        email=payload.email,
        password=payload.password,
        display_name=payload.display_name,
    )
    # A profile row exists from the start so an incomplete profile is a row with
    # nulls, not a user missing a row.
    from app.services.profiles import get_or_create_profile

    profile = await get_or_create_profile(db, user)
    token, session_row = await auth_svc.create_session(db, user)
    await db.commit()

    # Pass the profile explicitly — user.profile is not loaded on a fresh User.
    body = _session_body(user, profile, session_row)
    response = _json(body, status=201)
    set_session_cookie(response, token)
    return response


@router.post("/login")
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    _throttle(f"login:{auth_svc.normalise_email(payload.email)}", LOGIN_LIMIT)
    user = await auth_svc.authenticate(db, email=payload.email, password=payload.password)
    token, session_row = await auth_svc.create_session(db, user)
    await db.commit()
    body = _session_body(user, user.profile, session_row)
    response = _json(body)
    set_session_cookie(response, token)
    return response


@router.post("/logout", status_code=204, dependencies=[Depends(require_csrf)])
async def logout(
    response: Response,
    session: Session = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
):
    """Revoke the session the guard already resolved — FastAPI caches get_db, so
    this is the same AsyncSession the Session object belongs to.

    Two things were wrong here. It re-loaded the session a second time instead
    of using the one require_csrf had already loaded, and it answered with
    JSONResponse(None, 204) — which serialises a literal `null` body onto a
    status code that is defined to have none. Starlette then raised
    "Response content longer than Content-Length" *after* the 204 was on the
    wire, so every logout logged a 500 nobody saw.
    """
    await auth_svc.revoke_session(db, session)
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.post("/magic-link", status_code=202)
async def magic_link(payload: MagicLinkRequest, db: AsyncSession = Depends(get_db)):
    """Always 202, whether or not the email exists. A 404 here turns this
    endpoint into an account-enumeration oracle."""
    settings = get_settings()
    # Unauthenticated and it sends mail: without a cap it is a queue for
    # spamming one person's inbox, and it was.
    _throttle(
        f"magic-link:{auth_svc.normalise_email(payload.email)}", MAGIC_LINK_LIMIT
    )
    user = await auth_svc.get_user_by_email(db, payload.email)
    if user is not None and user.is_active:
        token = await auth_svc.issue_magic_link(db, user)
        link = auth_svc.magic_link_url(token, settings.app_url)
        await send_magic_link(user.email, link)
        await db.commit()
    return _json(
        {"message": "If that address has an account, a sign-in link is on its way."},
        status=202,
    )


@router.get("/magic-link/verify")
async def magic_link_verify(token: str, db: AsyncSession = Depends(get_db)):
    try:
        padding = "=" * (-len(token) % 4)
        raw = base64.urlsafe_b64decode(token + padding)
    except Exception:
        raise BadRequest("That sign-in link is not valid.", code="invalid_magic_link")

    user = await auth_svc.consume_magic_link(db, raw)
    session_token, _session = await auth_svc.create_session(db, user)
    await db.commit()

    # 302 back into the APP, not back into the API. The cookie is set on the
    # redirect response, and cookies ignore the port, so it travels.
    response = RedirectResponse(url=f"{get_settings().app_url}/", status_code=302)
    set_session_cookie(response, session_token)
    return response


def _session_body(user, profile, session_row) -> dict:
    """The user plus the CSRF token.

    The session cookie is httpOnly so JS cannot read it, which means the CSRF
    token has to come back in the body — including from register and login.
    Without it here, the client has no token until the next /users/me, and
    every mutation in between fails with 403.
    """
    return {
        **user_private(user, profile).model_dump(mode="json"),
        "csrf_token": auth_svc.encode_csrf(session_row.csrf_token),
    }


def _json(payload, status: int = 200):
    from fastapi.responses import JSONResponse

    return JSONResponse(content=payload, status_code=status)


__all__ = ["router"]