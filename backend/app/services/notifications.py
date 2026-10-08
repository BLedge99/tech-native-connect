"""Notifications. Synchronous insert then socket push — no queue.

A background job would need Redis/Celery for a table insert and a broadcast, and
would make the demo's live notification eventually consistent, which means it
arrives after the UI has already updated. specs/07_notifications.md §3.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import NotFound
from app.models import Notification, User
from app.models.enums import NotificationType
from app.realtime import manager
from app.services.pagination import decode_cursor

# Render strings live server-side, the client just displays them. specs/07 §5.
RENDER = {
    NotificationType.CONNECTION_REQUESTED: "{actor} wants to connect",
    NotificationType.CONNECTION_ACCEPTED: "{actor} accepted your request",
    NotificationType.CONNECTION_DECLINED: "{actor} declined your request",
    NotificationType.NEW_MESSAGE: "{actor} sent you a message",
    NotificationType.IDEA_INTEREST: "{actor} is interested in your idea \"{title}\"",
}


async def notify(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    notification_type: NotificationType,
    actor: User | None = None,
    connection_request_id: uuid.UUID | None = None,
    thread_id: uuid.UUID | None = None,
    project_idea_id: uuid.UUID | None = None,
    url: str = "/notifications",
    extra: dict | None = None,
    commit: bool = True,
) -> Notification | None:
    """You never notify yourself about your own action. One guard covers all
    five events."""
    if actor is not None and actor.id == user_id:
        return None

    data: dict = {
        "actor_name": actor.display_name if actor else "Someone",
        "actor_photo_url": (
            f"/api/v1/users/{actor.id}/photo" if actor else None
        ),
        "connection_request_id": str(connection_request_id) if connection_request_id else None,
        "thread_id": str(thread_id) if thread_id else None,
        "project_idea_id": str(project_idea_id) if project_idea_id else None,
    }
    if extra:
        data.update(extra)

    row = Notification(
        user_id=user_id,
        type=notification_type.value,
        actor_id=actor.id if actor else None,
        connection_request_id=connection_request_id,
        thread_id=thread_id,
        project_idea_id=project_idea_id,
        data=data,
        url=_safe_url(url),
    )
    db.add(row)
    if commit:
        await db.commit()
        await db.refresh(row)
        await push(row)
    else:
        await db.flush()
    return row


def _safe_url(url: str) -> str:
    """Relative paths only. A user-controllable URL here is an open-redirect
    vector on a page the user trusts."""
    if not url.startswith("/") or url.startswith("//"):
        return "/notifications"
    return url


def render_text(row: Notification) -> str:
    template = RENDER.get(row.type, "{actor} — new activity")
    data = row.data or {}
    return template.format(
        actor=data.get("actor_name", "Someone"),
        title=data.get("title", ""),
    )


async def push(row: Notification) -> None:
    """Best effort. A dead socket must never fail the request that created
    the notification."""
    try:
        await manager.broadcast_to_user(
            row.user_id,
            {
                "type": "notification",
                "data": {
                    "id": str(row.id),
                    "type": row.type,
                    "text": render_text(row),
                    "actor_id": str(row.actor_id) if row.actor_id else None,
                    "actor_name": (row.data or {}).get("actor_name"),
                    "url": row.url,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "read_at": row.read_at.isoformat() if row.read_at else None,
                },
            },
        )
    except Exception:
        pass


# ─── Queries ─────────────────────────────────────────────────────────────────


async def list_for(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    unread_only: bool = False,
    limit: int = 20,
    cursor: str | None = None,
) -> tuple[list[Notification], int]:
    stmt = select(Notification).where(Notification.user_id == user_id)
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    if cursor:
        since, since_id = decode_cursor(cursor)
        stmt = stmt.where(
            (Notification.created_at < since)
            | ((Notification.created_at == since) & (Notification.id < since_id))
        )
    stmt = stmt.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(limit + 1)
    rows = list(await db.scalars(stmt))
    unread = await unread_count(db, user_id)
    return rows, unread


async def unread_count(db: AsyncSession, user_id: uuid.UUID) -> int:
    return (
        await db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == user_id, Notification.read_at.is_(None))
        )
        or 0
    )


async def get_own(db: AsyncSession, user_id: uuid.UUID, notification_id: uuid.UUID) -> Notification:
    """Filter by user_id in the WHERE. Fetch-then-check leaks other people's
    rows into a response."""
    row = await db.scalar(
        select(Notification).where(
            Notification.id == notification_id, Notification.user_id == user_id
        )
    )
    if row is None:
        raise NotFound("That notification does not exist.")
    return row


async def mark_read(
    db: AsyncSession, user_id: uuid.UUID, notification_id: uuid.UUID
) -> Notification:
    row = await get_own(db, user_id, notification_id)
    if row.read_at is None:
        row.read_at = datetime.now(UTC)
        await db.commit()
    return row


async def mark_all_read(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Only unread rows, so already-read notifications keep their original
    timestamp — that timestamp orders the list."""
    await db.execute(
        update(Notification)
        .where(Notification.user_id == user_id, Notification.read_at.is_(None))
        .values(read_at=datetime.now(UTC))
    )
    await db.commit()


__all__ = [
    "notify",
    "render_text",
    "list_for",
    "unread_count",
    "get_own",
    "mark_read",
    "mark_all_read",
    "RENDER",
]