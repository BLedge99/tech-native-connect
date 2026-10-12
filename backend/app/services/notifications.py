from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import User
from app.models.domain import Notification
from app.web import ApiError


def notification_url(kind: str, connection_id: UUID | None, thread_id: UUID | None, idea_id: UUID | None) -> str:
    urls = {
        "connection_requested": "/connections",
        "connection_accepted": "/connections",
        "connection_declined": "/connections",
    }
    if kind in urls:
        return urls[kind]
    if kind == "new_message" and thread_id:
        return f"/messages/{thread_id}"
    if kind == "idea_interest" and idea_id:
        return f"/ideas/{idea_id}"
    raise ValueError("Notification requires a valid relative destination.")


async def notify(
    db: AsyncSession,
    recipient_id: UUID,
    kind: str,
    actor: User | None,
    *,
    connection_id: UUID | None = None,
    thread_id: UUID | None = None,
    idea_id: UUID | None = None,
    text: str,
) -> Notification | None:
    if actor is not None and actor.id == recipient_id:
        return None
    if not text.strip() or text.startswith("//"):
        raise ApiError(422, "validation_error", "Notification content is invalid.")
    data = {
        "actor_name": actor.display_name if actor else "Someone",
        "actor_photo_url": f"/api/v1/users/{actor.id}/photo" if actor else None,
        "text": text,
        "connection_request_id": str(connection_id) if connection_id else None,
        "thread_id": str(thread_id) if thread_id else None,
        "project_idea_id": str(idea_id) if idea_id else None,
        "url": notification_url(kind, connection_id, thread_id, idea_id),
    }
    notification = Notification(
        user_id=recipient_id,
        type=kind,
        actor_id=actor.id if actor else None,
        connection_request_id=connection_id,
        thread_id=thread_id,
        project_idea_id=idea_id,
        data=data,
    )
    db.add(notification)
    await db.flush()
    return notification


async def unread_count(db: AsyncSession, user_id: UUID) -> int:
    return int(
        await db.scalar(
            select(func.count()).select_from(Notification).where(
                Notification.user_id == user_id, Notification.read_at.is_(None)
            )
        )
        or 0
    )


async def mark_notification_read(db: AsyncSession, notification_id: UUID, user_id: UUID) -> Notification:
    notification = await db.scalar(
        select(Notification).where(Notification.id == notification_id, Notification.user_id == user_id).with_for_update()
    )
    if notification is None:
        raise ApiError(404, "not_found", "Notification not found.")
    if notification.read_at is None:
        notification.read_at = datetime.now(UTC)
    return notification


async def mark_all_read(db: AsyncSession, user_id: UUID) -> None:
    await db.execute(
        update(Notification)
        .where(Notification.user_id == user_id, Notification.read_at.is_(None))
        .values(read_at=datetime.now(UTC))
    )
