"""Auth service: hashing, tokens, sessions, magic links. Spec 02.

Every function here is unit-testable without a database or an HTTP request.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.errors import (
    AccountDeactivated,
    CsrfFailed,
    EmailTaken,
    Forbidden,
    InvalidCredentials,
    Unauthenticated,
)
from app.models import MagicLinkToken, Profile, Session, User

# ponytail: default params are the argon2 defaults and are fine here. If login
# latency ever matters in production, tune time_memory up rather than reaching
# for a different algorithm.
_hasher = PasswordHasher()


# ─── Passwords ───────────────────────────────────────────────────────────────


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        _hasher.verify(password_hash, password)
        return True
    except VerifyMismatchError:
        return False


# ─── Tokens ──────────────────────────────────────────────────────────────────


def new_token() -> bytes:
    return secrets.token_bytes(32)


def hash_token(token: bytes) -> bytes:
    """Only the hash is stored, so a leaked DB dump yields no live sessions."""
    return hashlib.sha256(token).digest()


# ─── Normalisation ───────────────────────────────────────────────────────────


def normalise_email(email: str) -> str:
    """Trim + lowercase at the boundary so whitespace/case never create a
    second account. Spec 02 §4."""
    return email.strip().lower()


def derive_first_name(email: str, display_name: str | None = None) -> str:
    if display_name:
        return display_name.strip().split()[0][:50]
    return email.split("@")[0][:50].replace(".", " ").title()


# ─── Sessions ────────────────────────────────────────────────────────────────


# How stale last_used_at may get before a request bothers to write it back.
# ponytail: a fixed interval, not a config knob — if this ever needs tuning for
# real session-expiry behaviour, put it in settings then.
_TOUCH_INTERVAL = timedelta(minutes=5)


async def create_session(db: AsyncSession, user: User) -> tuple[bytes, Session]:
    settings = get_settings()
    token = new_token()
    row = Session(
        user_id=user.id,
        token_hash=hash_token(token),
        csrf_token=new_token(),
        expires_at=datetime.now(UTC) + timedelta(days=settings.session_days),
    )
    db.add(row)
    await db.flush()
    return token, row


async def load_session(db: AsyncSession, token: bytes | None) -> tuple[Session, User] | None:
    """Returns None for every failure — the caller cannot tell why.

    The profile and its skills/interests/course are eager-loaded here. Every
    request needs them (profile_complete gates matching, the reason strings need
    skill names), and touching a lazy relationship outside async context raises
    MissingGreenlet.
    """
    if not token:
        return None
    result = await db.execute(
        select(Session, User)
        .join(User, User.id == Session.user_id)
        .options(
            selectinload(User.profile).selectinload(Profile.skills),
            selectinload(User.profile).selectinload(Profile.interests),
            selectinload(User.profile).selectinload(Profile.course),
        )
        .where(Session.token_hash == hash_token(token))
    )
    row = result.one_or_none()
    if row is None:
        return None
    session, user = row
    if session.expires_at <= datetime.now(UTC):
        await db.delete(session)
        await db.commit()
        return None
    if not user.is_active:
        return None
    # Sliding expiry, throttled. Writing last_used_at on *every* request made
    # every request a write, and because SQLAlchemy autoflushes on the next
    # query, a session revoked by a concurrent logout turned that flush into
    # "StaleDataError: UPDATE statement on table 'sessions' expected to update
    # 1 row(s); 0 were matched" — a 500 on whatever unrelated endpoint happened
    # to query next.
    #
    # It goes through a Core UPDATE and is committed here rather than left dirty
    # on the ORM object: that keeps the flush path free of the ORM UPDATE (so a
    # vanished session is a no-op, not an exception) and it actually persists.
    # Leaving it uncommitted looks harmless and is not — nothing else commits on
    # a read-only request, so last_used_at would never advance, every later
    # request would rewrite it, and each one would hold a row lock on the
    # session for the life of the request.
    #
    # Safe to commit this early: load_session is the first thing a request does,
    # so there is nothing else pending.
    now = datetime.now(UTC)
    if now - session.last_used_at > _TOUCH_INTERVAL:
        await db.execute(
            update(Session).where(Session.id == session.id).values(last_used_at=now)
        )
        await db.commit()
    return session, user


async def revoke_session(db: AsyncSession, session: Session) -> None:
    await db.delete(session)
    await db.commit()


async def revoke_all_sessions(db: AsyncSession, user_id: uuid.UUID) -> None:
    await db.execute(delete(Session).where(Session.user_id == user_id))


def encode_csrf(token: bytes) -> str:
    """The CSRF token is deliberately readable by JS and echoed in a header —
    that is what makes it usable. The session cookie stays httpOnly."""
    return base64.urlsafe_b64encode(token).decode().rstrip("=")


def decode_csrf(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def check_csrf(session: Session, header_value: str | None) -> None:
    if not header_value:
        raise CsrfFailed()
    try:
        supplied = decode_csrf(header_value)
    except Exception:
        raise CsrfFailed()
    if not secrets.compare_digest(supplied, session.csrf_token):
        raise CsrfFailed()


# ─── Registration and login ──────────────────────────────────────────────────


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == normalise_email(email)))
    return result.scalar_one_or_none()


async def register_user(
    db: AsyncSession, *, email: str, password: str, display_name: str
) -> User:
    email = normalise_email(email)
    if await get_user_by_email(db, email):
        raise EmailTaken()
    user = User(
        email=email,
        password_hash=hash_password(password),
        display_name=display_name.strip(),
        first_name=derive_first_name(email, display_name),
    )
    db.add(user)
    await db.flush()
    return user


async def authenticate(db: AsyncSession, *, email: str, password: str) -> User:
    user = await get_user_by_email(db, email)
    # Verify against a dummy hash when the user does not exist so the response
    # time does not reveal whether the email is registered.
    stored = user.password_hash if user else DUMMY_HASH
    ok = verify_password(stored, password)
    if user is None or not ok:
        # Unknown email and wrong password must be byte-identical. Spec 02 §3.
        raise InvalidCredentials()
    if not user.is_active:
        raise AccountDeactivated()
    user.last_login_at = datetime.now(UTC)
    return user


# Generated once at import so the timing-equalisation above costs nothing per call.
DUMMY_HASH = _hasher.hash("not-a-real-password-used-only-for-timing")


# ─── Magic links ─────────────────────────────────────────────────────────────


async def issue_magic_link(db: AsyncSession, user: User) -> bytes:
    """Single use, 15 min. Requesting a new one invalidates the old, or old
    links sitting in inboxes keep working."""
    settings = get_settings()
    await db.execute(
        delete(MagicLinkToken).where(
            MagicLinkToken.user_id == user.id, MagicLinkToken.used_at.is_(None)
        )
    )
    token = new_token()
    db.add(
        MagicLinkToken(
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=datetime.now(UTC) + timedelta(minutes=settings.magic_link_minutes),
        )
    )
    await db.flush()
    return token


async def consume_magic_link(db: AsyncSession, token: bytes) -> User:
    from app.errors import BadRequest

    result = await db.execute(
        select(MagicLinkToken).where(MagicLinkToken.token_hash == hash_token(token))
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise BadRequest("That sign-in link is not valid.", code="invalid_magic_link")
    if row.used_at is not None:
        raise BadRequest("That sign-in link has already been used.", code="magic_link_used")
    if row.expires_at <= datetime.now(UTC):
        raise BadRequest("That sign-in link has expired.", code="magic_link_expired")

    row.used_at = datetime.now(UTC)
    user = await db.get(User, row.user_id)
    if user is None:
        raise BadRequest("That sign-in link is not valid.", code="invalid_magic_link")
    if not user.is_active:
        raise AccountDeactivated()
    user.email_verified_at = user.email_verified_at or datetime.now(UTC)
    user.last_login_at = datetime.now(UTC)
    return user


def magic_link_url(token: bytes, base_url: str) -> str:
    raw = base64.urlsafe_b64encode(token).decode().rstrip("=")
    return f"{base_url.rstrip('/')}/api/v1/auth/magic-link/verify?token={raw}"