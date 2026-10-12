from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.auth import User
from app.models.domain import ConnectionRequest, Message, Notification, ReadReceipt, Thread
from app.realtime import manager
from app.schemas.connections import ConnectionAction, ConnectionCreate
from app.services.connections import (
    connection_counts,
    request_payload,
    send_request,
    transition_request,
    withdraw_request,
)
from app.services.pagination import decode_datetime_cursor, encode_datetime_cursor
from app.web import ApiError, get_current_user, require_csrf

router = APIRouter(prefix="/api/v1/connections", tags=["connections"])


@router.post("", status_code=201, dependencies=[Depends(require_csrf)])
async def create_connection(
    payload: ConnectionCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    connection = await send_request(db, user, payload.receiver_id, payload.message)
    result = await request_payload(db, connection, user.id)
    await db.commit()
    notice = await db.scalar(
        select(Notification)
        .where(
            Notification.connection_request_id == connection.id,
            Notification.type == "connection_requested",
        )
        .limit(1)
    )
    if notice is not None:
        await manager.send_user(
            notice.user_id,
            {"type": "notification", "data": {"id": str(notice.id), "type": notice.type, **notice.data}},
        )
    return result


@router.get("")
async def list_connections(
    filter: str | None = Query(default=None, pattern="^(received|sent|connected)$"),
    user_id: UUID | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    query = select(ConnectionRequest).where(
        or_(ConnectionRequest.sender_id == user.id, ConnectionRequest.receiver_id == user.id)
    )
    if user_id is not None:
        query = query.where(
            or_(
                and_(ConnectionRequest.sender_id == user.id, ConnectionRequest.receiver_id == user_id),
                and_(ConnectionRequest.receiver_id == user.id, ConnectionRequest.sender_id == user_id),
            )
        )
    elif filter == "received":
        query = query.where(ConnectionRequest.receiver_id == user.id, ConnectionRequest.status == "pending")
    elif filter == "sent":
        query = query.where(ConnectionRequest.sender_id == user.id, ConnectionRequest.status == "pending")
    elif filter == "connected":
        query = query.where(ConnectionRequest.status == "accepted")
    if cursor:
        created_at, row_id = decode_datetime_cursor(cursor)
        query = query.where(
            or_(
                ConnectionRequest.created_at < created_at,
                and_(ConnectionRequest.created_at == created_at, ConnectionRequest.id < row_id),
            )
        )
    rows = list(
        (
            await db.scalars(
                query.order_by(ConnectionRequest.created_at.desc(), ConnectionRequest.id.desc()).limit(limit + 1)
            )
        ).all()
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    items = [await request_payload(db, row, user.id) for row in rows]
    return {
        "items": items,
        "next_cursor": encode_datetime_cursor(rows[-1].created_at, rows[-1].id) if has_more and rows else None,
    }


@router.get("/summary")
async def get_connection_summary(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> dict[str, int]:
    counts = await connection_counts(db, user.id)
    thread_rows = (
        await db.execute(
            select(Thread.id, Thread.created_at, ReadReceipt.last_read_at)
            .join(ConnectionRequest, ConnectionRequest.id == Thread.connection_request_id)
            .outerjoin(ReadReceipt, and_(ReadReceipt.thread_id == Thread.id, ReadReceipt.user_id == user.id))
            .where(
                ConnectionRequest.status == "accepted",
                or_(ConnectionRequest.sender_id == user.id, ConnectionRequest.receiver_id == user.id),
            )
        )
    ).all()
    unread = 0
    for thread_id, created_at, last_read_at in thread_rows:
        unread += len(
            (
                await db.scalars(
                    select(Message.id).where(
                        Message.thread_id == thread_id,
                        Message.sender_id != user.id,
                        Message.created_at > (last_read_at or created_at),
                    )
                )
            ).all()
        )
    return {**counts, "unread_messages": unread}


@router.get("/{connection_id}")
async def get_connection(
    connection_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    connection = await db.scalar(
        select(ConnectionRequest).where(
            ConnectionRequest.id == connection_id,
            or_(ConnectionRequest.sender_id == user.id, ConnectionRequest.receiver_id == user.id),
        )
    )
    if connection is None:
        raise ApiError(404, "not_found", "Connection request not found.")
    return await request_payload(db, connection, user.id)


@router.patch("/{connection_id}", dependencies=[Depends(require_csrf)])
async def answer_connection(
    connection_id: UUID,
    payload: ConnectionAction,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    connection = await transition_request(db, connection_id, user, payload.action)
    result = await request_payload(db, connection, user.id)
    await db.commit()
    notice = await db.scalar(
        select(Notification)
        .where(
            Notification.connection_request_id == connection.id,
            Notification.actor_id == user.id,
            Notification.user_id == connection.sender_id,
            Notification.type == f"connection_{'accepted' if payload.action == 'accept' else 'declined'}",
        )
        .limit(1)
    )
    if notice is not None:
        await manager.send_user(
            notice.user_id,
            {"type": "notification", "data": {"id": str(notice.id), "type": notice.type, **notice.data}},
        )
    return result


@router.delete("/{connection_id}", status_code=204, dependencies=[Depends(require_csrf)])
async def delete_connection(
    connection_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    await withdraw_request(db, connection_id, user)
    await db.commit()
    return Response(status_code=204)
