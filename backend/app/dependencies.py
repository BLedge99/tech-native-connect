"""FastAPI dependencies: session cookie, CSRF, current user, admin.

Never trust a client-supplied user id. The current user always comes from the
session. Specs/00_conventions.md §3.
"""

from __future__ import annotations

import base64

from fastapi import Cookie, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.errors import Forbidden, ProfileIncomplete, Unauthenticated
from app.models import User
from app.models.user import Session
from app.services.auth import check_csrf, load_session

SESSION_COOKIE = "session"
CSRF_HEADER = "x-csrf-token"


def encode_cookie(token: bytes) -> str:
    return base64.urlsafe_b64encode(token).decode().rstrip("=")


def decode_cookie(value: str | None) -> bytes | None:
    if not value:
        return None
    try:
        padding = "=" * (-len(value) % 4)
        return base64.urlsafe_b64decode(value + padding)
    except Exception:
        return None


async def get_optional_session(
    db: AsyncSession = Depends(get_db),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> tuple[Session, User] | None:
    """None for every failure. The caller cannot tell expired from forged."""
    return await load_session(db, decode_cookie(session_cookie))


async def require_session(
    pair: tuple[Session, User] | None = Depends(get_optional_session),
) -> tuple[Session, User]:
    if pair is None:
        raise Unauthenticated()
    return pair


async def get_current_user(
    pair: tuple[Session, User] = Depends(require_session),
) -> User:
    return pair[1]


async def get_current_session(
    pair: tuple[Session, User] = Depends(require_session),
) -> Session:
    return pair[0]


async def require_csrf(
    pair: tuple[Session, User] = Depends(require_session),
    csrf_header: str | None = Header(default=None, alias=CSRF_HEADER),
) -> None:
    session, _user = pair
    check_csrf(session, csrf_header)


async def get_current_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        # 403, not 404. The admin panel is not a secret — specs/09_admin.md §3.
        raise Forbidden("You do not have access to that.")
    return user


async def require_profile_complete(user: User = Depends(get_current_user)) -> User:
    profile = user.profile
    if profile is None or not profile.profile_complete:
        raise ProfileIncomplete()
    return user