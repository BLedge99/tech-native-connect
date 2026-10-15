"""Connection routes. Spec 05."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_db
from app.dependencies import get_current_user, require_csrf
from app.errors import Forbidden, NotFound
from app.models import ConnectionRequest, Thread, User
from app.schemas import (
    ConnectionOut,
    ConnectionSummary,
    Page,
    RespondToConnectionRequest,
    SendConnectionRequest,
)
from app.serializers import connection_out
from app.services import connections as svc
from app.services.pagination import encode_cursor

router = APIRouter(prefix="/api/v1/connections", tags=["connections"])


async def _thread_id(db: AsyncSession, request_id: uuid.UUID) -> uuid.UUID | None:
    thread_id = await db.scalar(select(Thread.id).where(Thread.connection_request_id == request_id))
    return thread_id


async def _other(db: AsyncSession, request: ConnectionRequest, viewer_id: uuid.UUID) -> User:
    other_id = (
        request.receiver_id if request.sender_id == viewer_id else request.sender_id
    )
    from app.models import Profile

    result = await db.execute(
        select(User)
        .options(selectinload(User.profile).selectinload(Profile.course))
        .where(User.id == other_id)
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise NotFound("That person no longer exists.")
    return user


async def _others(
    db: AsyncSession, requests: list[ConnectionRequest], viewer_id: uuid.UUID
) -> dict[uuid.UUID, User]:
    """Every other party for a whole page, in one query.

    `_other` per row is what made this endpoint O(rows) in queries: a 20-row
    page issued two statements per row.
    """
    ids = {
        r.receiver_id if r.sender_id == viewer_id else r.sender_id for r in requests
    }
    if not ids:
        return {}
    from app.models import Profile

    rows = await db.scalars(
        select(User)
        .options(selectinload(User.profile).selectinload(Profile.course))
        .where(User.id.in_(ids))
    )
    return {u.id: u for u in rows}


async def _thread_ids(
    db: AsyncSession, requests: list[ConnectionRequest]
) -> dict[uuid.UUID, uuid.UUID]:
    """request id -> thread id, for a whole page, in one query."""
    ids = [r.id for r in requests]
    if not ids:
        return {}
    return dict(
        (
            await db.execute(
                select(Thread.connection_request_id, Thread.id).where(
                    Thread.connection_request_id.in_(ids)
                )
            )
        ).all()
    )


@router.post("", status_code=201, response_model=ConnectionOut, dependencies=[Depends(require_csrf)])
async def send_connection(
    payload: SendConnectionRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    request = await svc.send_request(
        db, user, payload.receiver_id, message=payload.message
    )
    other = await _other(db, request, user.id)
    return connection_out(request, user.id, other)


@router.get("", response_model=Page)
async def list_connections(
    filter: str | None = Query(default=None, alias="filter"),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """One endpoint with a filter, not three. Same query, different WHERE."""
    if filter not in (None, "received", "sent", "connected"):
        from app.errors import ValidationFailed

        raise ValidationFailed({"filter": "Unknown filter."})

    requests = await svc.load_participant_requests(
        db, user.id, connection_filter=filter, limit=limit, cursor=cursor
    )
    has_more = len(requests) > limit
    requests = requests[:limit]
    others = await _others(db, requests, user.id)
    thread_ids = await _thread_ids(db, requests)
    out = [
        connection_out(
            request,
            user.id,
            others[request.receiver_id if request.sender_id == user.id else request.sender_id],
            thread_id=thread_ids.get(request.id),
        )
        for request in requests
    ]
    return Page(
        items=out,
        next_cursor=(
            encode_cursor(requests[-1].created_at, requests[-1].id)
            if has_more and requests
            else None
        ),
    )


@router.post("/{request_id}/thread", status_code=201, dependencies=[Depends(require_csrf)])
async def open_thread(
    request_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get-or-create the thread for an accepted connection.

    Threads are created lazily on first use (spec 05 §5) so the message list
    never shows empty conversations. That means a client needs a way to obtain
    the thread id before its first message — this is it.
    """
    from app.models import ConnectionRequest
    from app.services.messaging import get_or_create_thread

    request = await db.get(ConnectionRequest, request_id)
    if request is None or user.id not in (request.sender_id, request.receiver_id):
        raise NotFound("That request does not exist.")
    if request.status != "accepted":
        from app.errors import ConnectionNotEstablished

        raise ConnectionNotEstablished()
    thread = await get_or_create_thread(db, request)
    await db.commit()
    return {"id": str(thread.id), "connection_request_id": str(request.id)}


@router.get("/summary", response_model=ConnectionSummary)
async def connection_summary(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """One call for nav badges, so they cannot disagree with the list."""
    data = await svc.summary(db, user.id)
    from app.services.messaging import unread_total

    return ConnectionSummary(unread_messages=await unread_total(db, user.id), **data)


@router.get("/{request_id}", response_model=ConnectionOut)
async def get_connection(
    request_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    request = await db.get(ConnectionRequest, request_id)
    if request is None or user.id not in (request.sender_id, request.receiver_id):
        # 404, not 403. The existence of other people's connections is not
        # the caller's business.
        raise NotFound("That request does not exist.")
    other = await _other(db, request, user.id)
    return connection_out(request, user.id, other, thread_id=await _thread_id(db, request.id))


@router.patch("/{request_id}", response_model=ConnectionOut, dependencies=[Depends(require_csrf)])
async def respond_to_connection(
    request_id: uuid.UUID,
    payload: RespondToConnectionRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    request = await svc.get_request_or_404(db, request_id)
    if user.id not in (request.sender_id, request.receiver_id):
        raise NotFound("That request does not exist.")
    request = await svc.respond(db, request, user, payload.action)
    other = await _other(db, request, user.id)
    return connection_out(request, user.id, other, thread_id=await _thread_id(db, request.id))


@router.delete("/{request_id}", status_code=204, dependencies=[Depends(require_csrf)])
async def withdraw_connection(
    request_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    request = await svc.get_request_or_404(db, request_id)
    if user.id not in (request.sender_id, request.receiver_id):
        raise NotFound("That request does not exist.")
    await svc.withdraw(db, request, user)
    return Response(status_code=204)


__all__ = ["router"]
