from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Table,
    Text,
    Column,
    func,
    literal_column,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM, JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.auth import Base


user_role = ENUM("software_developer", "business_developer", name="user_role", create_type=False)
connection_status = ENUM("pending", "accepted", "declined", name="connection_status", create_type=False)
notification_type = ENUM(
    "connection_requested",
    "connection_accepted",
    "connection_declined",
    "new_message",
    "idea_interest",
    name="notification_type",
    create_type=False,
)
idea_category = ENUM(
    "find_problem",
    "build_product",
    "design_brand",
    "run_campaign",
    "other",
    name="idea_category",
    create_type=False,
)

profile_skills = Table(
    "profile_skills",
    Base.metadata,
    Column("profile_id", PGUUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True),
    Column("skill_id", PGUUID(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

profile_interests = Table(
    "profile_interests",
    Base.metadata,
    Column("profile_id", PGUUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True),
    Column("interest_id", PGUUID(as_uuid=True), ForeignKey("interests.id", ondelete="CASCADE"), primary_key=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    category: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Interest(Base):
    __tablename__ = "interests"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Photo(Base):
    __tablename__ = "photos"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    content_type: Mapped[str] = mapped_column(String(50), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    bio: Mapped[str | None] = mapped_column(String(500))
    role: Mapped[str | None] = mapped_column(user_role)
    course_id: Mapped[UUID | None] = mapped_column(ForeignKey("courses.id", ondelete="SET NULL"))
    looking_for: Mapped[str | None] = mapped_column(String(300))
    photo_id: Mapped[UUID | None] = mapped_column(ForeignKey("photos.id", ondelete="SET NULL"))
    profile_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ConnectionRequest(Base):
    __tablename__ = "connection_requests"
    __table_args__ = (
        CheckConstraint("sender_id <> receiver_id", name="ck_connection_not_self"),
        Index("ix_connections_receiver_status", "receiver_id", "status"),
        Index("ix_connections_sender_status", "sender_id", "status"),
        Index(
            "uq_connection_pair",
            func.least(literal_column("sender_id"), literal_column("receiver_id")),
            func.greatest(literal_column("sender_id"), literal_column("receiver_id")),
            unique=True,
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    sender_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    receiver_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(connection_status, nullable=False, server_default=text("'pending'"))
    message: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    responded_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class Thread(Base):
    __tablename__ = "threads"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    connection_request_id: Mapped[UUID] = mapped_column(
        ForeignKey("connection_requests.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_thread_created_id", "thread_id", "created_at", "id"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    thread_id: Mapped[UUID] = mapped_column(ForeignKey("threads.id", ondelete="CASCADE"), nullable=False)
    sender_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    body: Mapped[str] = mapped_column(String(2000), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ReadReceipt(Base):
    __tablename__ = "read_receipts"

    thread_id: Mapped[UUID] = mapped_column(ForeignKey("threads.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    last_read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_user_read_created", "user_id", "read_at", "created_at"),
        Index("ix_notifications_unread", "user_id", "created_at", postgresql_where=text("read_at IS NULL")),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    type: Mapped[str] = mapped_column(notification_type, nullable=False)
    actor_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    connection_request_id: Mapped[UUID | None] = mapped_column(ForeignKey("connection_requests.id", ondelete="SET NULL"))
    thread_id: Mapped[UUID | None] = mapped_column(ForeignKey("threads.id", ondelete="SET NULL"))
    project_idea_id: Mapped[UUID | None] = mapped_column(ForeignKey("project_ideas.id", ondelete="SET NULL"))
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ProjectIdea(Base):
    __tablename__ = "project_ideas"
    __table_args__ = (
        Index("ix_project_ideas_created", "created_at"),
        Index("ix_project_ideas_author", "author_id"),
        Index("ix_project_ideas_open_created", "is_open", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    author_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(idea_category, nullable=False)
    skills_needed: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, server_default=text("'{}'::varchar[]"))
    course_id: Mapped[UUID | None] = mapped_column(ForeignKey("courses.id", ondelete="SET NULL"))
    is_open: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class IdeaInterest(Base):
    __tablename__ = "idea_interests"

    idea_id: Mapped[UUID] = mapped_column(ForeignKey("project_ideas.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class AdminAuditLog(Base):
    __tablename__ = "admin_audit_log"
    __table_args__ = (
        Index("ix_admin_audit_created", "created_at"),
        Index("ix_admin_audit_admin_created", "admin_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    admin_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(50))
    target_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
