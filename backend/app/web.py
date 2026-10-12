import hmac
from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.auth import Session, User
from app.services.auth import find_session


class ApiError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        fields: dict[str, str] | None = None,
    ):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.fields = fields


@dataclass
class AuthContext:
    session: Session
    user: User


async def get_optional_auth_context(request: Request, db: AsyncSession = Depends(get_db)) -> AuthContext | None:
    raw_token = request.cookies.get("session")
    if not raw_token:
        return None
    found = await find_session(db, raw_token)
    if found is None:
        return None
    session, user = found
    await db.commit()
    return AuthContext(session=session, user=user)


async def get_current_user(context: AuthContext | None = Depends(get_optional_auth_context)) -> User:
    if context is None:
        raise ApiError(401, "unauthenticated", "Sign in to continue.")
    return context.user


async def get_current_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise ApiError(403, "forbidden", "You do not have permission to access this page.")
    return user


async def require_csrf(
    request: Request, context: AuthContext | None = Depends(get_optional_auth_context)
) -> None:
    if context is None:
        return
    supplied = request.headers.get("X-CSRF-Token", "").encode("ascii", errors="ignore")
    if not hmac.compare_digest(supplied, context.session.csrf_token):
        raise ApiError(403, "csrf_failed", "Refresh the page and try again.")