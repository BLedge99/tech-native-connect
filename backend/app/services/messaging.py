from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import User
from app.models.domain import (
    ConnectionRequest,
    Message,
    Profile,
    ReadReceipt,
    Thread,
)
from app.services.notifications import notify
from app.web import ApiError


async def require_participant(db: AsyncSession, thread_id: UUID, user_id: UUID) -> tuple[Thread, ConnectionRequest]:
    result = await db.execute(
        select(Thread, ConnectionRequest)
        .join(ConnectionRequest, ConnectionRequest.id == Thread.connection_request_id)
        .where(Thread.id == thread_id)
    )
    row = result.first()
    if row is None:
        raise ApiError(404, "not_found", "Thread not found.")
    thread, connection = row
    if user_id not in (connection.sender_id, connection.receiver_id):
        raise ApiError(404, "not_found", "Thread not found.")
    if connection.status != "accepted":
        raise ApiError(403, "connection_not_established", "Both people must accept before messaging.")
    return thread, connection


async def open_thread(db: AsyncSession, connection_id: UUID, user_id: UUID) -> Thread:
    connection = await db.scalar(
        select(ConnectionRequest).where(ConnectionRequest.id == connection_id).with_for_update()
    )
    if connection is None or user_id not in (connection.sender_id, connection.receiver_id):
        raise ApiError(404, "not_found", "Connection not found.")
    if connection.status != "accepted":
        raise ApiError(403, "connection_not_established", "Both people must accept before messaging.")
    thread = await db.scalar(select(Thread).where(Thread.connection_request_id == connection_id))
    if thread is None:
        thread = Thread(connection_request_id=connection_id)
        db.add(thread)
        await db.flush()
    return thread


async def create_message(
    db: AsyncSession, thread_id: UUID, sender: User, body: str
) -> tuple[Thread, Message, UUID]:
    thread, connection = await require_participant(db, thread_id, sender.id)
    message = Message(thread_id=thread.id, sender_id=sender.id, body=body)
    db.add(message)
    await db.flush()
    recipient_id = connection.receiver_id if connection.sender_id == sender.id else connection.sender_id
    await notify(
        db,
        recipient_id,
        "new_message",
        sender,
        thread_id=thread.id,
        text=f"{sender.display_name} sent you a message",
    )
    return thread, message, recipient_id


async def unread_for_thread(db: AsyncSession, thread_id: UUID, user_id: UUID, joined_at: datetime) -> int:
    receipt = await db.get(ReadReceipt, (thread_id, user_id))
    statement = select(func.count()).select_from(Message).where(
        Message.thread_id == thread_id,
        Message.sender_id != user_id,
    )
    if receipt is not None:
        statement = statement.where(Message.created_at > receipt.last_read_at)
    return int(
        await db.scalar(statement) or 0
    )


async def unread_total(db: AsyncSession, user_id: UUID) -> int:
    rows = (
        await db.execute(
            select(Thread.id, Thread.created_at)
            .join(ConnectionRequest, ConnectionRequest.id == Thread.connection_request_id)
            .where(
                ConnectionRequest.status == "accepted",
                or_(ConnectionRequest.sender_id == user_id, ConnectionRequest.receiver_id == user_id),
            )
        )
    ).all()
    total = 0
    for thread_id, created_at in rows:
        total += await unread_for_thread(db, thread_id, user_id, created_at)
    return total


async def mark_thread_read(db: AsyncSession, thread: Thread, user_id: UUID) -> datetime:
    now = datetime.now(UTC)
    receipt = await db.get(ReadReceipt, (thread.id, user_id))
    if receipt is None:
        db.add(ReadReceipt(thread_id=thread.id, user_id=user_id, last_read_at=now))
    else:
        receipt.last_read_at = now
    return now


async def thread_list_payload(db: AsyncSession, thread: Thread, connection: ConnectionRequest, user_id: UUID) -> dict:
    other_id = connection.receiver_id if connection.sender_id == user_id else connection.sender_id
    other = await db.get(User, other_id)
    profile = await db.scalar(select(Profile).where(Profile.user_id == other_id))
    last_message = await db.scalar(
        select(Message)
        .where(Message.thread_id == thread.id)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(1)
    )
    unread_count = await unread_for_thread(db, thread.id, user_id, thread.created_at)
    return {
        "id": str(thread.id),
        "other": {
            "id": str(other.id),
            "display_name": other.display_name,
            "has_photo": bool(profile and profile.photo_id),
            "photo_url": f"/api/v1/users/{other.id}/photo" if profile and profile.photo_id else None,
        },
        "last_message": (
            {
                "id": str(last_message.id),
                "body": last_message.body,
                "sender_id": str(last_message.sender_id),
                "created_at": last_message.created_at,
            }
            if last_message
            else None
        ),
        "unread_count": unread_count,
        "last_message_at": last_message.created_at if last_message else thread.created_at,
    }

