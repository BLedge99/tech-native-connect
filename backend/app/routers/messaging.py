from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, WebSocket, WebSocketDisconnect
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import SessionLocal, get_db
from app.models.auth import User
from app.models.domain import ConnectionRequest, Message, Notification, Thread
from app.schemas.messaging import MessageCreate
from app.realtime import manager
from app.services.auth import find_session
from app.services.connections import request_payload
from app.services.messaging import (
    create_message,
    mark_thread_read,
    open_thread,
    require_participant,
    thread_list_payload,
    unread_for_thread,
)
from app.services.pagination import decode_datetime_cursor, encode_datetime_cursor
from app.web import ApiError, get_current_user, require_csrf

router = APIRouter(prefix="/api/v1", tags=["messaging"])


async def resolve_thread_or_connection(
    db: AsyncSession, path_id: UUID, user_id: UUID, create: bool
) -> tuple[Thread | None, ConnectionRequest]:
    thread = await db.get(Thread, path_id)
    if thread is not None:
        thread, connection = await require_participant(db, thread.id, user_id)
        return thread, connection
    connection = await db.scalar(select(ConnectionRequest).where(ConnectionRequest.id == path_id))
    if connection is None or user_id not in (connection.sender_id, connection.receiver_id):
        raise ApiError(404, "not_found", "Thread not found.")
    if connection.status != "accepted":
        raise ApiError(403, "connection_not_established", "Both people must accept before messaging.")
    thread = await db.scalar(select(Thread).where(Thread.connection_request_id == connection.id))
    if thread is None and create:
        thread = await open_thread(db, connection.id, user_id)
    return thread, connection


@router.get("/threads")
async def list_threads(
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rows = (
        await db.execute(
            select(Thread, ConnectionRequest)
            .join(ConnectionRequest, ConnectionRequest.id == Thread.connection_request_id)
            .where(
                ConnectionRequest.status == "accepted",
                or_(ConnectionRequest.sender_id == user.id, ConnectionRequest.receiver_id == user.id),
            )
        )
    ).all()
    items = [await thread_list_payload(db, thread, connection, user.id) for thread, connection in rows]
    items.sort(key=lambda item: (item["last_message_at"], item["id"]), reverse=True)
    if cursor:
        created_at, row_id = decode_datetime_cursor(cursor)
        items = [
            item
            for item in items
            if item["last_message_at"] < created_at
            or (item["last_message_at"] == created_at and UUID(item["id"]) < row_id)
        ]
    has_more = len(items) > limit
    items = items[:limit]
    next_cursor = (
        encode_datetime_cursor(items[-1]["last_message_at"], UUID(items[-1]["id"])) if has_more and items else None
    )
    return {"items": items, "next_cursor": next_cursor}


@router.get("/threads/{thread_id}")
async def get_thread(
    thread_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    thread, connection = await resolve_thread_or_connection(db, thread_id, user.id, create=False)
    if thread is None:
        request = await request_payload(db, connection, user.id)
        return {
            "id": str(thread_id),
            "other": request["other"],
            "last_message": None,
            "unread_count": 0,
            "last_message_at": None,
        }
    return await thread_list_payload(db, thread, connection, user.id)


@router.get("/threads/{thread_id}/messages")
async def get_messages(
    thread_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = None,
    after: datetime | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    thread, connection = await resolve_thread_or_connection(db, thread_id, user.id, create=False)
    now = await mark_thread_read(db, thread, user.id) if thread is not None else None
    if thread is None:
        await db.commit()
        return {"items": [], "next_cursor": None, "last_read_at": None, "unread_count": 0}
    query = select(Message).where(Message.thread_id == thread.id)
    if after is not None:
        query = query.where(Message.created_at > after)
    if cursor:
        created_at, row_id = decode_datetime_cursor(cursor)
        query = query.where(
            or_(
                Message.created_at < created_at,
                and_(Message.created_at == created_at, Message.id < row_id),
            )
        )
    rows = list(
        (
            await db.scalars(
                query.order_by(Message.created_at.desc(), Message.id.desc()).limit(limit + 1)
            )
        ).all()
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    await db.commit()
    return {
        "items": [
            {
                "id": str(row.id),
                "thread_id": str(row.thread_id),
                "sender_id": str(row.sender_id),
                "body": row.body,
                "created_at": row.created_at,
            }
            for row in rows
        ],
        "next_cursor": encode_datetime_cursor(rows[-1].created_at, rows[-1].id) if has_more and rows else None,
        "last_read_at": now,
        "unread_count": 0,
    }


@router.post("/threads/{thread_id}/messages", status_code=201, dependencies=[Depends(require_csrf)])
async def post_message(
    thread_id: UUID,
    payload: MessageCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    thread, _ = await resolve_thread_or_connection(db, thread_id, user.id, create=True)
    _, message, recipient_id = await create_message(db, thread.id, user, payload.body)
    await db.commit()
    data = {
        "id": str(message.id),
        "thread_id": str(thread.id),
        "sender_id": str(user.id),
        "body": message.body,
        "created_at": message.created_at.isoformat(),
    }
    frame = {"type": "message", "data": data}
    await manager.broadcast_thread(thread.id, frame)
    notice = await db.scalar(
        select(Notification)
        .where(Notification.thread_id == thread.id, Notification.actor_id == user.id, Notification.user_id == recipient_id)
        .order_by(Notification.created_at.desc())
        .limit(1)
    )
    if notice is not None:
        await manager.send_user_except_thread(
            recipient_id,
            thread.id,
            {"type": "notification", "data": {"id": str(notice.id), "type": notice.type, **notice.data}},
        )
    return data


@router.post("/threads/{thread_id}/read", status_code=204, dependencies=[Depends(require_csrf)])
async def read_thread(
    thread_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    thread, _ = await resolve_thread_or_connection(db, thread_id, user.id, create=False)
    if thread is not None:
        await mark_thread_read(db, thread, user.id)
    await db.commit()
    return Response(status_code=204)


@router.get("/threads/{thread_id}/messages/unread-count")
async def get_thread_unread_count(
    thread_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, int]:
    thread, _ = await resolve_thread_or_connection(db, thread_id, user.id, create=False)
    count = await unread_for_thread(db, thread.id, user.id, thread.created_at) if thread else 0
    return {"unread_count": count}


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    raw_token = websocket.cookies.get("session")
    if not raw_token:
        await websocket.close(code=4401)
        return
    async with SessionLocal() as db:
        found = await find_session(db, raw_token)
        if found is None:
            await websocket.close(code=4401)
            return
        _, user = found
        user_id = user.id
    await manager.connect(user_id, websocket)
    try:
        while True:
            frame = await websocket.receive_json()
            kind = frame.get("type")
            try:
                path_id = UUID(frame["thread_id"])
                async with SessionLocal() as db:
                    if kind == "subscribe":
                        thread, _ = await resolve_thread_or_connection(db, path_id, user_id, create=False)
                        if thread is None:
                            raise ApiError(404, "not_found", "Thread not found.")
                        await manager.subscribe(websocket, thread.id)
                        await websocket.send_json({"type": "subscribed", "thread_id": str(thread.id)})
                    elif kind == "unsubscribe":
                        await manager.unsubscribe(websocket, path_id)
                    elif kind == "send_message":
                        body = str(frame.get("body", "")).strip()
                        if not body or len(body) > 2000:
                            raise ApiError(422, "validation_error", "Messages must be 1–2000 characters.")
                        thread, _ = await resolve_thread_or_connection(db, path_id, user_id, create=True)
                        sender = await db.get(User, user_id)
                        _, message, _ = await create_message(db, thread.id, sender, body)
                        await db.commit()
                        message_data = {
                            "id": str(message.id),
                            "thread_id": str(thread.id),
                            "sender_id": str(user_id),
                            "body": message.body,
                            "created_at": message.created_at.isoformat(),
                            "client_id": frame.get("client_id"),
                        }
                        await manager.broadcast_thread(
                            thread.id, {"type": "message", "data": message_data}, exclude=websocket
                        )
                        await websocket.send_json({"type": "ack", "data": message_data})
                    else:
                        raise ApiError(422, "bad_request", "Unknown WebSocket message type.")
            except ApiError as exc:
                await websocket.send_json({"type": "error", "code": exc.code, "message": exc.message})
            except (KeyError, ValueError, TypeError):
                await websocket.send_json({"type": "error", "code": "bad_request", "message": "Invalid WebSocket message."})
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(user_id, websocket)
