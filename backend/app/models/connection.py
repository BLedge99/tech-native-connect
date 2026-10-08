"""Connection requests. One row per pair, ever. Spec 05 §2.

The accepted connection IS this row at status='accepted'. There is deliberately
no separate connections table — two tables holding one fact is two sources of
truth, and they will disagree.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import connection_status_enum


class ConnectionRequest(Base):
    __tablename__ = "connection_requests"
    __table_args__ = (
        CheckConstraint("sender_id <> receiver_id", name="ck_no_self_request"),
        # One request per pair regardless of direction. LEAST/GREATEST normalise
        # so this catches both orderings with one definition.
        Index(
            "uq_one_request_per_pair",
            "pair_lo",
            "pair_hi",
            unique=True,
        ),
        Index("ix_connection_requests_received", "receiver_id", "status"),
        Index("ix_connection_requests_sent", "sender_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sender_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    receiver_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        connection_status_enum, default="pending", nullable=False
    )
    message: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Audit trail: answers "who accepted this?" without inferring it.
    responded_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    # Maintained by the service; the unique index uses them.
    pair_lo: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    pair_hi: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    sender: Mapped["User"] = relationship(foreign_keys=[sender_id])  # noqa: F821
    receiver: Mapped["User"] = relationship(foreign_keys=[receiver_id])  # noqa: F821

    @property
    def other(self, viewer_id: uuid.UUID) -> "User":
        return self.receiver if viewer_id == self.sender_id else self.sender