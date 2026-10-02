"""Users, sessions, magic link tokens. Spec 02 §2."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import CITEXT, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("char_length(display_name) BETWEEN 1 AND 80", name="ck_display_name_len"),
        CheckConstraint("char_length(email) <= 254", name="ck_email_len"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    # citext: Alice@x.com and alice@x.com are one user. See ADR 0002.
    email: Mapped[str] = mapped_column(CITEXT, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    first_name: Mapped[str] = mapped_column(String(50), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # lazy="joined": the current user's profile is needed on essentially every
    # request (profile_complete gates matching, reason strings need skill names).
    # Eager here avoids MissingGreenlet on every access.
    profile: Mapped["Profile"] = relationship(  # noqa: F821
        back_populates="user", uselist=False, cascade="all, delete-orphan", lazy="joined"
    )
    sessions: Mapped[list["Session"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Session(Base):
    """Opaque server-side session. Only a HASH of the token is stored, so a
    leaked database dump does not hand over live sessions. Spec 02 §2."""

    __tablename__ = "sessions"
    __table_args__ = (
        Index("ix_sessions_token_hash", "token_hash", unique=True),
        Index("ix_sessions_user_id", "user_id"),
        Index("ix_sessions_expires_at", "expires_at"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[bytes] = mapped_column(nullable=False)
    csrf_token: Mapped[bytes] = mapped_column(nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped[User] = relationship(back_populates="sessions")


class MagicLinkToken(Base):
    """Single use, 15 minute expiry. Requesting a new one invalidates the old."""

    __tablename__ = "magic_link_tokens"
    __table_args__ = (
        Index("ix_magic_link_token_hash", "token_hash", unique=True),
        Index("ix_magic_link_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[bytes] = mapped_column(nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )