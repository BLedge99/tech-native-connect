"""Threads and messages. specs/06_messaging.md.

require_participant is the single gate: it covers BOTH conditions —
membership AND an accepted connection. Declared once, used everywhere,
including on the WebSocket subscribe path.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import ConnectionNotEstablished, Forbidden, NotFound
from app.models import (
    ConnectionRequest,
    Message,
    NotificationType,
    ReadReceipt,
    Thread,
    User,
)
from app.models.enums import ConnectionStatus
from app.realtime import manager
from app.services.connections import pair
from app.services.notifications import notify
from app.services.pagination import decode_cursor


async def accepted_request(
    db: AsyncSession, user_a: uuid.UUID, user_b: uuid.UUID
) -> ConnectionRequest | None:
    lo, hi = pair(user_a, user_b)
    return await db.scalar(
        select(ConnectionRequest).where(
            ConnectionRequest.pair_lo == lo,
            ConnectionRequest.pair_hi == hi,
            ConnectionRequest.status == ConnectionStatus.ACCEPTED,
        )
    )


async def require_participant(
    db: AsyncSession, thread_id: uuid.UUID, user_id: uuid.UUID
) -> tuple[Thread, ConnectionRequest]:
    """Non-participants get 404 — existence of someone else's private thread is
    not the caller's business. The 403 is for a real participant whose thread
    exists but whose connection is not accepted (defence in depth)."""
    thread = await db.get(Thread, thread_id)
    if thread is None:
        raise NotFound("That conversation does not exist.")
    request = await db.get(ConnectionRequest, thread.connection_request_id)
    if request is None or user_id not in (request.sender_id, request.receiver_id):
        raise NotFound("That conversation does not exist.")
    if request.status != ConnectionStatus.ACCEPTED:
        raise ConnectionNotEstablished()
    return thread, request


async def can_access(
    db: AsyncSession, user_a: uuid.UUID, user_b: uuid.UUID
) -> ConnectionRequest | None:
    return await accepted_request(db, user_a, user_b)


async def get_or_create_thread(
    db: AsyncSession, request: ConnectionRequest
) -> Thread:
    """Lazy creation on first message. Creating on accept would put empty
    conversations in the message list."""
    thread = await db.scalar(
        select(Thread).where(Thread.connection_request_id == request.id)
    )
    if thread is None:
        thread = Thread(connection_request_id=request.id)
        db.add(thread)
        await db.flush()
    return thread


async def open_thread_for_pair(
    db: AsyncSession, user_a: uuid.UUID, user_b: uuid.UUID
) -> Thread | None:
    request = await accepted_request(db, user_a, user_b)
    if request is None:
        return None
    return await get_or_create_thread(db, request)


async def list_threads(
    db: AsyncSession, user_id: uuid.UUID
) -> list[tuple[Thread, ConnectionRequest, User]]:
    """Only threads the user participates in AND whose connection is accepted."""
    result = await db.execute(
        select(Thread, ConnectionRequest)
        .join(ConnectionRequest, ConnectionRequest.id == Thread.connection_request_id)
        .where(
            (ConnectionRequest.sender_id == user_id)
            | (ConnectionRequest.receiver_id == user_id),
            ConnectionRequest.status == ConnectionStatus.ACCEPTED,
        )
    )
    rows = result.all()
    out: list[tuple[Thread, ConnectionRequest, User]] = []
    for thread, request in rows:
        other_id = (
            request.receiver_id if request.sender_id == user_id else request.sender_id
        )
        other = await db.get(User, other_id)
        if other is not None:
            out.append((thread, request, other))
    return out


def other_party(request: ConnectionRequest, viewer_id: uuid.UUID) -> uuid.UUID:
    return (
        request.receiver_id if request.sender_id == viewer_id else request.sender_id
    )


# ─── Read state ──────────────────────────────────────────────────────────────


async def unread_count(db: AsyncSession, thread_id: uuid.UUID, user_id: uuid.UUID) -> int:
    """A message is unread if it is not mine and arrived after my cursor.
    Absent receipt = everything unread."""
    receipt = await db.get(ReadReceipt, (thread_id, user_id))
    stmt = select(func.count()).select_from(Message).where(
        Message.thread_id == thread_id, Message.sender_id != user_id
    )
    if receipt is not None:
        stmt = stmt.where(Message.created_at > receipt.last_read_at)
    return await db.scalar(stmt) or 0


async def mark_read(
    db: AsyncSession, thread_id: uuid.UUID, user_id: uuid.UUID
) -> datetime:
    """On opening a thread, mark EVERYTHING read up to now — including messages
    that arrived while the tab was closed. Anything else shows the user unread
    messages about the conversation they are currently reading."""
    now = datetime.now(UTC)
    receipt = await db.get(ReadReceipt, (thread_id, user_id))
    if receipt is None:
        db.add(ReadReceipt(thread_id=thread_id, user_id=user_id, last_read_at=now))
    else:
        receipt.last_read_at = now
    await db.commit()
    return now


async def list_messages(
    db: AsyncSession, thread_id: uuid.UUID, *, limit: int = 50, cursor: str | None = None
) -> list[Message]:
    """Newest first, with id as the tiebreaker so two messages sharing a
    millisecond cannot repeat across pages."""
    stmt = select(Message).where(Message.thread_id == thread_id)
    if cursor:
        since, since_id = decode_cursor(cursor)
        stmt = stmt.where(
            (Message.created_at < since) | ((Message.created_at == since) & (Message.id < since_id))
        )
    result = await db.execute(
        stmt.order_by(Message.created_at.desc(), Message.id.desc()).limit(limit)
    )
    return list(result.scalars().all())


async def messages_after(
    db: AsyncSession, thread_id: uuid.UUID, since: datetime, *, limit: int = 500
) -> list[Message]:
    result = await db.execute(
        select(Message)
        .where(Message.thread_id == thread_id, Message.created_at > since)
        .order_by(Message.created_at.asc(), Message.id.asc())
        .limit(limit)
    )
    return list(result.scalars().all())


# ─── Send ────────────────────────────────────────────────────────────────────


async def send_message(
    db: AsyncSession,
    *,
    thread: Thread,
    request: ConnectionRequest,
    sender: User,
    body: str,
    client_id: str | None = None,
    push: bool = True,
) -> Message:
    """Persist FIRST, then broadcast. Broadcasting a message that failed to save
    means two users see it and it vanishes on refresh."""
    message = Message(thread_id=thread.id, sender_id=sender.id, body=body.strip())
    db.add(message)

    recipient_id = other_party(request, sender.id)
    await notify(
        db,
        user_id=recipient_id,
        notification_type=NotificationType.NEW_MESSAGE,
        actor=sender,
        thread_id=thread.id,
        url=f"/messages/{thread.id}",
        extra={"preview": body.strip()[:80]},
        commit=False,
    )
    await db.commit()
    await db.refresh(message)

    if push:
        payload = serialize_message(message, client_id=client_id)
        # Exclude the sender: they already rendered it optimistically. Including
        # them is the duplicate-message bug, on both the HTTP and socket paths.
        await manager.broadcast_to_thread(
            thread.id, {"type": "message", "data": payload}, exclude_user_id=sender.id
        )
    return message


def serialize_message(message: Message, *, client_id: str | None = None) -> dict:
    data = {
        "id": str(message.id),
        "thread_id": str(message.thread_id),
        "sender_id": str(message.sender_id),
        "body": message.body,
        "created_at": message.created_at.isoformat() if message.created_at else None,
    }
    if client_id:
        data["client_id"] = client_id
    return data


__all__ = [
    "accepted_request",
    "require_participant",
    "open_thread_for_pair",
    "get_or_create_thread",
    "list_threads",
    "other_party",
    "unread_count",
    "mark_read",
    "list_messages",
    "messages_after",
    "send_message",
    "serialize_message",
]