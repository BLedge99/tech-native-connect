import asyncio
import logging
import smtplib
from datetime import UTC, datetime
from email.message import EmailMessage
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db
from app.models.auth import MagicLinkToken, User
from app.models.domain import Profile
from app.schemas.auth import LoginRequest, MagicLinkRequest, RegisterRequest, UserResponse
from app.services.auth import create_session, hash_password, hash_token, request_magic_link, verify_password
from app.web import ApiError, AuthContext, get_optional_auth_context, require_csrf

router = APIRouter(prefix="/api/v1", tags=["auth"])
logger = logging.getLogger(__name__)
settings = get_settings()


def set_session_cookies(response: Response, raw_token: str, csrf_token: str) -> None:
    secure = settings.app_env == "production"
    response.set_cookie(
        "session", raw_token, httponly=True, secure=secure, samesite="lax", path="/", max_age=604800
    )
    response.headers["X-CSRF-Token"] = csrf_token


async def send_magic_link(email: str, link: str) -> None:
    message = EmailMessage()
    message["Subject"] = "Your Bootcamp Connect sign-in link"
    message["From"] = "no-reply@bootcampconnect.local"
    message["To"] = email
    message.set_content(f"Use this one-time link to sign in. It expires in 15 minutes.\n\n{link}")

    def deliver() -> None:
        with smtplib.SMTP(settings.mailpit_smtp_host, settings.mailpit_smtp_port, timeout=3) as smtp:
            smtp.send_message(message)

    try:
        await asyncio.to_thread(deliver)
    except (OSError, smtplib.SMTPException):
        logger.warning("Magic-link email could not be delivered to Mailpit")


@router.post("/auth/register", response_model=UserResponse, status_code=201)
async def register(payload: RegisterRequest, response: Response, db: AsyncSession = Depends(get_db)) -> User:
    email = str(payload.email)
    display_name = payload.display_name
    first_name = email.split("@", 1)[0][:50]
    existing = await db.scalar(select(User).where(User.email == email))
    if existing is not None:
        if not existing.is_active:
            raise ApiError(403, "account_deactivated", "This account has been deactivated.")
        raise ApiError(409, "email_taken", "An account with this email already exists.")
    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        display_name=display_name,
        first_name=first_name,
    )
    db.add(user)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise ApiError(409, "email_taken", "An account with this email already exists.") from exc
    db.add(Profile(user_id=user.id))
    _, raw_token, csrf_token = await create_session(db, user)
    await db.commit()
    set_session_cookies(response, raw_token, csrf_token)
    return user


@router.post("/auth/login", response_model=UserResponse)
async def login(payload: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)) -> User:
    user = await db.scalar(select(User).where(User.email == str(payload.email)))
    if user is not None and not user.is_active:
        raise ApiError(403, "account_deactivated", "This account has been deactivated.")
    if user is None or not verify_password(user.password_hash, payload.password):
        raise ApiError(401, "invalid_credentials", "Incorrect email or password.")
    user.last_login_at = datetime.now(UTC)
    _, raw_token, csrf_token = await create_session(db, user)
    await db.commit()
    set_session_cookies(response, raw_token, csrf_token)
    return user


@router.post("/auth/logout", status_code=204)
async def logout(
    request: Request,
    response: Response,
    context: AuthContext | None = Depends(get_optional_auth_context),
    _: None = Depends(require_csrf),
    db: AsyncSession = Depends(get_db),
) -> Response:
    if context is not None:
        await db.delete(context.session)
        await db.commit()
    response.status_code = 204
    response.delete_cookie("session", path="/", httponly=True, secure=settings.app_env == "production", samesite="lax")
    return response


@router.post("/auth/magic-link", status_code=202)
async def magic_link(payload: MagicLinkRequest, db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    result = await request_magic_link(db, str(payload.email))
    response = {"message": "If that address has an account, a link is on its way."}
    if result is not None:
        token, user = result
        query = urlencode({"token": token})
        link = f"http://localhost:5173/api/v1/auth/magic-link/verify?{query}"
        await send_magic_link(user.email, link)
    return response


@router.get("/auth/magic-link/verify")
async def verify_magic_link(
    request: Request,
    token: str,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    magic = await db.scalar(
        select(MagicLinkToken)
        .where(MagicLinkToken.token_hash == hash_token(token))
        .with_for_update()
    )
    if magic is None:
        raise ApiError(400, "invalid_magic_link", "This sign-in link is invalid.")
    if magic.used_at is not None:
        raise ApiError(400, "magic_link_used", "This sign-in link has already been used.")
    if magic.expires_at <= datetime.now(UTC):
        raise ApiError(400, "magic_link_expired", "This sign-in link has expired.")
    user = await db.get(User, magic.user_id)
    if user is None or not user.is_active:
        raise ApiError(400, "invalid_magic_link", "This sign-in link is invalid.")
    magic.used_at = datetime.now(UTC)
    user.email_verified_at = datetime.now(UTC)
    _, raw_token, csrf_token = await create_session(db, user)
    await db.commit()
    destination = request.query_params.get("from", "/")
    if not destination.startswith("/") or destination.startswith("//"):
        destination = "/"
    redirect = RedirectResponse(destination, status_code=302)
    set_session_cookies(redirect, raw_token, csrf_token)
    return redirect
