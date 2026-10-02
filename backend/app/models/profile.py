"""Profiles, photos and the admin-managed reference data. Spec 03 §3."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Column,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import user_role_enum


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


# ─── Reference data (managed by admins, spec 09) ─────────────────────────────


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    category: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Interest(Base):
    __tablename__ = "interests"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ─── Join tables ─────────────────────────────────────────────────────────────
# Composite PKs mean the database enforces "no duplicates", not a SELECT-then-INSERT
# race. See specs/03_profiles.md §3 and specs/05_connection_requests.md §1.

profile_skills = Table(
    "profile_skills",
    Base.metadata,
    Column(
        "profile_id",
        UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "skill_id",
        UUID(as_uuid=True),
        ForeignKey("skills.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    Index("ix_profile_skills_skill_id", "skill_id"),
)

profile_interests = Table(
    "profile_interests",
    Base.metadata,
    Column(
        "profile_id",
        UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "interest_id",
        UUID(as_uuid=True),
        ForeignKey("interests.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    Index("ix_profile_interests_interest_id", "interest_id"),
)


class Photo(Base):
    """Profile photo stored as a blob. See decisions/0006-images-as-pg-blob.md.

    NEVER select photos.data in a profile list query — that loads every image
    into memory. Fetch it from its own endpoint.
    """

    __tablename__ = "photos"
    __table_args__ = (
        Index("ix_photos_user_id", "user_id", unique=True),
        CheckConstraint("byte_size > 0 AND byte_size <= 2097152", name="ck_photo_size"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    content_type: Mapped[str] = mapped_column(String(50), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    data: Mapped[bytes] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Profile(Base):
    """One-to-one with users, deliberately a separate table so auth (spec 02)
    does not grow into a profile model."""

    __tablename__ = "profiles"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    bio: Mapped[str | None] = mapped_column(String(500))
    role: Mapped[str | None] = mapped_column(user_role_enum)
    course_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="SET NULL")
    )
    looking_for: Mapped[str | None] = mapped_column(String(300))
    photo_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    # Cached: role IS NOT NULL AND count(skills) >= 1. Recomputed on every update.
    profile_complete: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="profile")  # noqa: F821

    # selectin throughout: these are read on nearly every request and touching
    # them lazily in async context raises MissingGreenlet.
    course: Mapped[Course | None] = relationship(lazy="selectin")
    skills: Mapped[list[Skill]] = relationship(secondary=profile_skills, lazy="selectin")
    interests: Mapped[list[Interest]] = relationship(secondary=profile_interests, lazy="selectin")