import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import MagicLinkToken, Session, User

password_hasher = PasswordHasher()
SESSION_LIFETIME = timedelta(days=7)
MAGIC_LINK_LIFETIME = timedelta(minutes=15)


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def hash_token(token: str) -> bytes:
    return hashlib.sha256(token.encode("utf-8")).digest()


async def create_session(db: AsyncSession, user: User) -> tuple[Session, str, str]:
    raw_token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    session = Session(
        user_id=user.id,
        token_hash=hash_token(raw_token),
        csrf_token=csrf_token.encode("ascii"),
        expires_at=now + SESSION_LIFETIME,
        last_used_at=now,
    )
    db.add(session)
    await db.flush()
    return session, raw_token, csrf_token


async def find_session(db: AsyncSession, raw_token: str) -> tuple[Session, User] | None:
    result = await db.execute(
        select(Session, User)
        .join(User, User.id == Session.user_id)
        .where(Session.token_hash == hash_token(raw_token))
    )
    found = result.first()
    if found is None:
        return None
    session, user = found
    now = datetime.now(UTC)
    if session.expires_at <= now or not user.is_active:
        await db.delete(session)
        await db.commit()
        return None
    session.expires_at = now + SESSION_LIFETIME
    session.last_used_at = now
    return session, user


async def request_magic_link(db: AsyncSession, email: str) -> tuple[str, User] | None:
    user = await db.scalar(select(User).where(User.email == email))
    if user is None or not user.is_active:
        return None
    await db.execute(delete(MagicLinkToken).where(MagicLinkToken.user_id == user.id))
    raw_token = secrets.token_urlsafe(32)
    db.add(
        MagicLinkToken(
            user_id=user.id,
            token_hash=hash_token(raw_token),
            expires_at=datetime.now(UTC) + MAGIC_LINK_LIFETIME,
        )
    )
    await db.commit()
    return raw_token, user