"""Notification routes. Spec 07."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.dependencies import get_current_user, require_csrf
from app.models import User
from app.schemas import MarkReadRequest, NotificationOut, Page, UnreadCount
from app.serializers import notification_out
from app.services import notifications as svc
from app.services.pagination import encode_cursor

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


@router.get("", response_model=Page)
async def list_notifications(
    unread_only: bool = Query(default=False),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """unread_count comes back with the list so the bell cannot disagree with
    the page it links to."""
    rows, unread = await svc.list_for(db, user.id, unread_only=unread_only, limit=limit, cursor=cursor)
    has_more = len(rows) > limit
    rows = rows[:limit]
    return Page(
        items=[notification_out(r) for r in rows],
        next_cursor=(
            encode_cursor(rows[-1].created_at, rows[-1].id) if has_more and rows else None
        ),
    )


@router.get("/unread-count", response_model=UnreadCount)
async def unread_count(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    return UnreadCount(unread_count=await svc.unread_count(db, user.id))


@router.get("/{notification_id}", response_model=NotificationOut)
async def get_notification(
    notification_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return notification_out(await svc.get_own(db, user.id, notification_id))


@router.patch("/read-all", status_code=204, dependencies=[Depends(require_csrf)])
async def mark_all_read(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    await svc.mark_all_read(db, user.id)
    return None


@router.patch("/{notification_id}", response_model=NotificationOut, dependencies=[Depends(require_csrf)])
async def mark_read(
    notification_id: uuid.UUID,
    payload: MarkReadRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Idempotent. Pressing the button twice because it was slow is not a
    conflict, so this is 200 both times."""
    row = await svc.mark_read(db, user.id, notification_id)
    return notification_out(row)


__all__ = ["router"]