"""Pydantic request/response models.

Two schemas for users: UserPrivate (own profile, includes email) and UserPublic
(never includes email). Not one schema with fields stripped in a router —
routers are thin and stripping there is exactly where a leak happens.
specs/03_profiles.md §6.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

# ─── Auth ────────────────────────────────────────────────────────────────────


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=2, max_length=80)

    @field_validator("display_name")
    @classmethod
    def _strip(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Enter a display name.")
        return cleaned


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class MagicLinkRequest(BaseModel):
    email: EmailStr


# ─── Shared ──────────────────────────────────────────────────────────────────


class RefOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str


class CourseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str


class ProfilePublic(BaseModel):
    """What anyone may see. No email, no is_active, no is_admin."""

    bio: str | None = None
    role: str | None = None
    course: CourseOut | None = None
    looking_for: str | None = None
    skills: list[RefOut] = Field(default_factory=list)
    interests: list[RefOut] = Field(default_factory=list)
    profile_complete: bool = False
    has_photo: bool = False
    photo_url: str | None = None


class UserPublic(BaseModel):
    """Other people's profile view. Must never contain email."""

    id: uuid.UUID
    display_name: str
    first_name: str
    created_at: datetime | None = None
    profile: ProfilePublic


class UserPrivate(BaseModel):
    """Own account. The ONLY shape that ever includes an email address."""

    id: uuid.UUID
    email: str
    display_name: str
    first_name: str
    is_admin: bool
    is_active: bool
    created_at: datetime | None = None
    last_login_at: datetime | None = None
    profile: ProfilePublic


class UserSummary(BaseModel):
    """For embedding in connections, threads, matches, notifications."""

    id: uuid.UUID
    display_name: str
    first_name: str | None = None
    has_photo: bool = False
    photo_url: str | None = None


# ─── Profiles ────────────────────────────────────────────────────────────────


class UpdateProfileRequest(BaseModel):
    bio: str | None = Field(default=None, max_length=500)
    role: str | None = None
    course_id: uuid.UUID | None = None
    looking_for: str | None = Field(default=None, max_length=300)
    skill_ids: list[uuid.UUID] | None = None
    interest_ids: list[uuid.UUID] | None = None

    @field_validator("role")
    @classmethod
    def _valid_role(cls, v: str | None) -> str | None:
        if v in (None, ""):
            return None
        if v not in ("software_developer", "business_developer"):
            raise ValueError("Choose software_developer or business_developer.")
        return v


# ─── Matching ────────────────────────────────────────────────────────────────


class MatchOut(BaseModel):
    user: UserPublic
    score: int
    reasons: list[str]
    shared_skills: list[RefOut] = Field(default_factory=list)
    connection_state: str


# ─── Connections ─────────────────────────────────────────────────────────────


class SendConnectionRequest(BaseModel):
    receiver_id: uuid.UUID
    message: str | None = Field(default=None, max_length=300)


class RespondToConnectionRequest(BaseModel):
    action: str

    @field_validator("action")
    @classmethod
    def _valid(cls, v: str) -> str:
        if v not in ("accept", "decline"):
            raise ValueError("Action must be accept or decline.")
        return v


class ConnectionOut(BaseModel):
    id: uuid.UUID
    status: str
    other: UserSummary
    message: str | None = None
    created_at: datetime
    responded_at: datetime | None = None
    unread_count: int = 0
    thread_id: uuid.UUID | None = None


class ConnectionSummary(BaseModel):
    received_pending: int
    sent_pending: int
    connected: int
    unread_messages: int = 0


# ─── Messaging ───────────────────────────────────────────────────────────────


class SendMessageRequest(BaseModel):
    body: str = Field(min_length=1, max_length=2000)

    @field_validator("body")
    @classmethod
    def _strip(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Write a message first.")
        return cleaned


class MessageOut(BaseModel):
    id: uuid.UUID
    thread_id: uuid.UUID
    sender_id: uuid.UUID
    body: str
    created_at: datetime


class ThreadOut(BaseModel):
    id: uuid.UUID
    other: UserSummary
    last_message: MessageOut | None = None
    unread_count: int = 0
    last_message_at: datetime | None = None


# ─── Notifications ───────────────────────────────────────────────────────────


class NotificationOut(BaseModel):
    id: uuid.UUID
    type: str
    text: str
    url: str
    read_at: datetime | None = None
    created_at: datetime
    actor_id: uuid.UUID | None = None
    data: dict = Field(default_factory=dict)


class MarkReadRequest(BaseModel):
    read: bool = True


class UnreadCount(BaseModel):
    unread_count: int


# ─── Project ideas ───────────────────────────────────────────────────────────


class IdeaIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=2000)
    category: str
    skills_needed: list[str] = Field(default_factory=list, max_length=8)
    course_id: uuid.UUID | None = None


class IdeaUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    category: str | None = None
    skills_needed: list[str] | None = Field(default=None, max_length=8)
    course_id: uuid.UUID | None = None
    is_open: bool | None = None


class IdeaOut(BaseModel):
    id: uuid.UUID
    title: str
    description: str
    category: str
    skills_needed: list[str] = Field(default_factory=list)
    course: CourseOut | None = None
    is_open: bool
    interest_count: int = 0
    viewer_has_interested: bool = False
    created_at: datetime
    author: UserSummary


# ─── Admin ───────────────────────────────────────────────────────────────────


class AdminUserOut(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    first_name: str
    is_admin: bool
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None = None
    role: str | None = None
    course: CourseOut | None = None
    skills: list[RefOut] = Field(default_factory=list)
    profile_complete: bool = False


class NamedRefIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    category: str | None = Field(default=None, max_length=50)


class AuditOut(BaseModel):
    id: uuid.UUID
    admin_id: uuid.UUID
    action: str
    target_type: str | None = None
    target_id: uuid.UUID | None = None
    metadata: dict = Field(default_factory=dict)
    created_at: datetime


class AdminOverview(BaseModel):
    total_users: int
    active_users: int
    new_this_week: int
    connections_made: int
    project_ideas: int


class ResolveReportRequest(BaseModel):
    status: str
    resolution: str | None = Field(default=None, max_length=200)


class Page(BaseModel):
    """Cursor pagination envelope. specs/00_conventions.md §5."""

    items: list
    next_cursor: str | None = None