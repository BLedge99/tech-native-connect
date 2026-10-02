"""Project ideas and interests in them. Spec 08 §2."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    Table,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.enums import idea_category_enum

# Composite PK makes double-interest structurally impossible.
idea_interests = Table(
    "idea_interests",
    Base.metadata,
    Column(
        "idea_id",
        UUID(as_uuid=True),
        ForeignKey("project_ideas.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "user_id",
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    Index("ix_idea_interests_idea_id", "idea_id"),
)


class ProjectIdea(Base):
    __tablename__ = "project_ideas"
    __table_args__ = (
        Index("ix_project_ideas_created", "created_at"),
        Index("ix_project_ideas_author", "author_id"),
        Index("ix_project_ideas_open_created", "is_open", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    author_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(idea_category_enum, nullable=False)
    # Free text, NOT a join to skills. An idea needs "a designer who knows
    # Figma" — free text expresses the specific ask, and ideas must not be
    # blocked by admin reference-data hygiene. See specs/08_project_ideas.md §2.
    skills_needed: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    course_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="SET NULL")
    )
    is_open: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )