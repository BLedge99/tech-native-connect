"""Messaging routes + the WebSocket. Spec 06.

require_participant is used on every route AND on socket subscribe. A WebSocket
is otherwise a long-lived bypass of every guard, and it is the most likely place
for a permissions hole.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, Response, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import SessionLocal, get_db
from app.dependencies import (
    SESSION_COOKIE,
    decode_cookie,
    get_current_user,
    require_csrf,
)
from app.errors import BadRequest, NotFound, ValidationFailed
from app.models import Message, User
from app.realtime import manager
from app.schemas import MessageOut, Page, SendMessageRequest, ThreadOut
from app.serializers import message_out, summary, thread_out
from app.services import auth as auth_svc
from app.services.pagination import encode_cursor
from app.services import messaging as svc

router = APIRouter(prefix="/api/v1", tags=["messaging"])


@router.get("/threads", response_model=list[ThreadOut])
async def list_threads(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    rows = await svc.list_threads(db, user.id)
    out = []
    for thread, _request, other in rows:
        messages = await svc.list_messages(db, thread.id, limit=1)
        last = messages[0] if messages else None
        out.append(
            thread_out(
                thread,
                other,
                last_message=last,
                unread_count=await svc.unread_count(db, thread.id, user.id),
            )
        )
    out.sort(key=lambda t: (t.last_message_at is None, t.last_message_at), reverse=True)
    return out


@router.get("/threads/{thread_id}", response_model=ThreadOut)
async def get_thread(
    thread_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    thread, request = await svc.require_participant(db, thread_id, user.id)
    other_id = svc.other_party(request, user.id)
    other = await db.get(User, other_id)
    messages = await svc.list_messages(db, thread.id, limit=1)
    return thread_out(
        thread,
        other,
        last_message=messages[0] if messages else None,
        unread_count=await svc.unread_count(db, thread.id, user.id),
    )


@router.get("/threads/{thread_id}/messages", response_model=Page)
async def list_messages(
    thread_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Opening the thread marks everything read in the same round trip."""
    await svc.require_participant(db, thread_id, user.id)
    messages = await svc.list_messages(db, thread_id, limit=limit + 1, cursor=cursor)
    await svc.mark_read(db, thread_id, user.id)
    has_more = len(messages) > limit
    messages = messages[:limit]
    return Page(
        items=[message_out(m) for m in messages],
        next_cursor=(
            encode_cursor(messages[-1].created_at, messages[-1].id)
            if has_more and messages
            else None
        ),
    )


@router.post(
    "/threads/{thread_id}/messages",
    status_code=201,
    response_model=MessageOut,
    dependencies=[Depends(require_csrf)],
)
async def send_message(
    thread_id: uuid.UUID,
    payload: SendMessageRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The response IS the created message, so a client that skipped
    optimistic UI still works."""
    thread, request = await svc.require_participant(db, thread_id, user.id)
    message = await svc.send_message(
        db, thread=thread, request=request, sender=user, body=payload.body
    )
    return message_out(message)


@router.post("/threads/{thread_id}/read", status_code=204, dependencies=[Depends(require_csrf)])
async def mark_thread_read(
    thread_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await svc.require_participant(db, thread_id, user.id)
    await svc.mark_read(db, thread_id, user.id)
    return Response(status_code=204)


@router.get("/threads/{thread_id}/messages/unread-count")
async def unread_count(
    thread_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await svc.require_participant(db, thread_id, user.id)
    return {"unread_count": await svc.unread_count(db, thread_id, user.id)}


# ─── WebSocket ───────────────────────────────────────────────────────────────

ws_router = APIRouter()


@ws_router.websocket("/api/v1/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Session cookie authenticates the handshake. No token in the query
    string — that leaks into logs and Referer headers."""
    token = decode_cookie(websocket.cookies.get(SESSION_COOKIE))
    async with SessionLocal() as db:
        pair = await auth_svc.load_session(db, token)
        if pair is None:
            await websocket.close(code=4001)
            return
        session, user = pair

    await websocket.accept()
    await manager.connect_user(user.id, websocket)
    subscribed: set[uuid.UUID] = set()

    try:
        while True:
            # A malformed frame must never kill the socket — that is how one bad
            # message from a stale client tab takes down a live demo.
            try:
                raw = await websocket.receive_json()
            except (ValueError, TypeError):
                await manager.send_to(
                    websocket, {"type": "error", "code": "bad_request", "message": "Expected JSON."}
                )
                continue
            kind = raw.get("type")

            if kind == "subscribe":
                thread_id = _uuid(raw.get("thread_id"))
                if thread_id is None:
                    await manager.send_to(
                        websocket, {"type": "error", "code": "bad_request", "message": "thread_id required"}
                    )
                    continue
                async with SessionLocal() as db:
                    try:
                        # SAME check as the HTTP routes. Never skip it here.
                        await svc.require_participant(db, thread_id, user.id)
                    except NotFound:
                        await manager.send_to(
                            websocket, {"type": "error", "code": "forbidden", "message": "No access."}
                        )
                        continue
                    except Exception:
                        await manager.send_to(
                            websocket,
                            {"type": "error", "code": "forbidden", "message": "No access."},
                        )
                        continue
                await manager.subscribe_thread(user.id, thread_id, websocket)
                subscribed.add(thread_id)
                await manager.send_to(
                    websocket, {"type": "subscribed", "thread_id": str(thread_id)}
                )

            elif kind == "unsubscribe":
                thread_id = _uuid(raw.get("thread_id"))
                if thread_id is not None:
                    await manager.unsubscribe_thread(thread_id, websocket)
                    subscribed.discard(thread_id)

            elif kind == "send_message":
                thread_id = _uuid(raw.get("thread_id"))
                body = (raw.get("body") or "").strip()
                client_id = raw.get("client_id")
                if thread_id is None or not body:
                    await manager.send_to(
                        websocket, {"type": "error", "code": "bad_request", "message": "thread_id and body required"}
                    )
                    continue
                async with SessionLocal() as db:
                    try:
                        thread, request = await svc.require_participant(db, thread_id, user.id)
                        message = await svc.send_message(
                            db,
                            thread=thread,
                            request=request,
                            sender=user,
                            body=body,
                            client_id=client_id,
                            # Already broadcast inside send_message; exclude us.
                            push=False,
                        )
                    except Exception as exc:
                        code = getattr(exc, "code", "forbidden")
                        await manager.send_to(
                            websocket, {"type": "error", "code": code, "message": str(exc) or "Not allowed."}
                        )
                        continue
                    # Ack to the sender so it can reconcile its optimistic copy.
                    await manager.send_to(
                        websocket,
                        {"type": "ack", "data": svc.serialize_message(message, client_id=client_id)},
                    )
                    # Broadcast to everyone else.
                    await manager.broadcast_to_thread(
                        thread.id,
                        {"type": "message", "data": svc.serialize_message(message)},
                        exclude=websocket,
                    )

            elif kind == "ping":
                await manager.send_to(websocket, {"type": "pong"})

    except WebSocketDisconnect:
        pass
    except Exception:
        # Never let an unexpected error in one frame go unhandled: it would
        # propagate as an ASGI error and drop every connection this user has.
        logging.getLogger(__name__).exception("WebSocket loop failed for user %s", user.id)
    finally:
        for thread_id in subscribed:
            await manager.unsubscribe_thread(thread_id, websocket)
        await manager.disconnect(user.id, websocket)


def _uuid(value) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


__all__ = ["router", "ws_router"]