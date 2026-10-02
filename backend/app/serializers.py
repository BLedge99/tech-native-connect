"""Serialisation helpers. One place builds every public shape, so the
UserPublic/UserPrivate split is structural rather than a convention."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    ConnectionRequest,
    Message,
    Notification,
    Profile,
    ProjectIdea,
    User,
)
from app.schemas import (
    AdminUserOut,
    AuditOut,
    ConnectionOut,
    ConnectionSummary,
    CourseOut,
    IdeaOut,
    MatchOut,
    MessageOut,
    NotificationOut,
    ProfilePublic,
    RefOut,
    ThreadOut,
    UserPrivate,
    UserPublic,
    UserSummary,
)
from app.services.messaging import unread_count as thread_unread
from app.services.notifications import render_text


def course_out(profile: Profile) -> CourseOut | None:
    return CourseOut(id=profile.course.id, name=profile.course.name) if profile.course else None


def _public_profile(profile: Profile | None, user_id: uuid.UUID) -> ProfilePublic:
    if profile is None:
        return ProfilePublic()
    return ProfilePublic(
        bio=profile.bio,
        role=profile.role,
        course=course_out(profile),
        looking_for=profile.looking_for,
        skills=[RefOut(id=s.id, name=s.name) for s in profile.skills],
        interests=[RefOut(id=i.id, name=i.name) for i in profile.interests],
        profile_complete=profile.profile_complete,
        has_photo=profile.photo_id is not None,
        photo_url=f"/api/v1/users/{user_id}/photo" if profile.photo_id else None,
    )


def user_public(user: User, profile: Profile | None = None) -> UserPublic:
    """No email. Ever. There is a test that scans every endpoint for this."""
    return UserPublic(
        id=user.id,
        display_name=user.display_name,
        first_name=user.first_name,
        created_at=user.created_at,
        profile=_public_profile(profile if profile is not None else user.profile, user.id),
    )


def user_private(user: User, profile: Profile | None = None) -> UserPrivate:
    return UserPrivate(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        first_name=user.first_name,
        is_admin=user.is_admin,
        is_active=user.is_active,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
        profile=_public_profile(profile if profile is not None else user.profile, user.id),
    )


def summary(user: User, *, has_photo: bool | None = None) -> UserSummary:
    """has_photo is passed by callers that already know it. Falling back to
    user.profile triggers a lazy load, which raises in async context."""
    if has_photo is None:
        has_photo = (
            user.profile.photo_id is not None
            if "profile" in user.__dict__ and user.__dict__["profile"] is not None
            else False
        )
    return UserSummary(
        id=user.id,
        display_name=user.display_name,
        first_name=user.first_name,
        has_photo=has_photo,
        photo_url=f"/api/v1/users/{user.id}/photo" if has_photo else None,
    )


def match_out(item) -> MatchOut:
    from app.services.match_service import to_view

    view = to_view(item.user, item.user.profile)
    shared_ids = set()
    for name in item.shared_skill_names:
        for sid, skill_name in view.skills:
            if skill_name == name:
                shared_ids.add(sid)
    return MatchOut(
        user=user_public(item.user),
        score=item.score,
        reasons=item.reasons,
        shared_skills=[RefOut(id=i, name=n) for i, n in view.skills if i in shared_ids],
        connection_state=item.connection_state,
    )


def connection_out(
    request: ConnectionRequest,
    viewer_id: uuid.UUID,
    other: User,
    *,
    unread_count: int = 0,
    thread_id: uuid.UUID | None = None,
) -> ConnectionOut:
    """Callers preload `other` and `thread_id` so this stays synchronous."""
    return ConnectionOut(
        id=request.id,
        status=request.status,
        other=summary(other),
        message=request.message,
        created_at=request.created_at,
        responded_at=request.responded_at,
        unread_count=unread_count,
        thread_id=thread_id,
    )


def message_out(message: Message) -> MessageOut:
    return MessageOut(
        id=message.id,
        thread_id=message.thread_id,
        sender_id=message.sender_id,
        body=message.body,
        created_at=message.created_at,
    )


def thread_out(
    thread,
    other: User,
    *,
    last_message: Message | None = None,
    unread_count: int = 0,
) -> ThreadOut:
    return ThreadOut(
        id=thread.id,
        other=summary(other),
        last_message=message_out(last_message) if last_message else None,
        unread_count=unread_count,
        last_message_at=last_message.created_at if last_message else thread.created_at,
    )


def notification_out(row: Notification) -> NotificationOut:
    return NotificationOut(
        id=row.id,
        type=row.type,
        text=render_text(row),
        url=row.url,
        read_at=row.read_at,
        created_at=row.created_at,
        actor_id=row.actor_id,
        data=row.data or {},
    )


def idea_out(
    idea: ProjectIdea,
    author: User,
    *,
    interest_count: int = 0,
    viewer_has_interested: bool = False,
    course_name: str | None = None,
) -> IdeaOut:
    course = None
    if idea.course_id:
        course = CourseOut(id=idea.course_id, name=course_name or "")
    return IdeaOut(
        id=idea.id,
        title=idea.title,
        description=idea.description,
        category=idea.category,
        skills_needed=list(idea.skills_needed or []),
        course=course,
        is_open=idea.is_open,
        interest_count=interest_count,
        viewer_has_interested=viewer_has_interested,
        created_at=idea.created_at,
        author=summary(author),
    )


def admin_user_out(user: User) -> AdminUserOut:
    profile = user.profile
    return AdminUserOut(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        first_name=user.first_name,
        is_admin=user.is_admin,
        is_active=user.is_active,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
        role=profile.role if profile else None,
        course=course_out(profile) if profile else None,
        skills=[RefOut(id=s.id, name=s.name) for s in (profile.skills if profile else [])],
        profile_complete=profile.profile_complete if profile else False,
    )


def audit_out(row) -> AuditOut:
    return AuditOut(
        id=row.id,
        admin_id=row.admin_id,
        action=row.action,
        target_type=row.target_type,
        target_id=row.target_id,
        metadata=row.metadata_ or {},
        created_at=row.created_at,
    )


__all__ = [
    "user_public",
    "user_private",
    "summary",
    "match_out",
    "connection_out",
    "message_out",
    "thread_out",
    "notification_out",
    "idea_out",
    "admin_user_out",
    "audit_out",
]