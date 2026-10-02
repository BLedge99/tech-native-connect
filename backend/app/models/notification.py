"""Notifications and admin audit log.

Notifications are immutable: no updates, no deletes except a cascade when the
user is deleted. Only read_at changes, and only NULL -> timestamp.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.enums import notification_type_enum


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        # Covers list + count. The partial index below is ponytail-clever:
        # unread is a small slice, so the count query stays cheap on every
        # page load via the bell.
        Index("ix_notifications_user_read_created", "user_id", "read_at", "created_at"),
        Index(
            "ix_notifications_unread",
            "user_id",
            "created_at",
            postgresql_where=text("read_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Recipient. NEVER the actor.
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(notification_type_enum, nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    connection_request_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    thread_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    project_idea_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    # Snapshot of display strings. Avoids an N+1 on the list. Stale names are
    # acceptable for a notification seconds old. See specs/07_notifications.md §2.
    data: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    # Relative path only. A user-controllable URL here is an open-redirect vector.
    url: Mapped[str] = mapped_column(String(300), default="/notifications", nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AdminAuditLog(Base):
    """Every admin read or write of user data. Written in the SAME transaction
    as the action — if the action rolls back, so does the audit row."""

    __tablename__ = "admin_audit_log"
    __table_args__ = (
        Index("ix_audit_created", "created_at"),
        Index("ix_audit_admin_created", "admin_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    admin_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(50))
    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )