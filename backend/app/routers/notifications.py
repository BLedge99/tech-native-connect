from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import and_, delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.auth import User
from app.models.domain import Notification
from app.schemas.notifications import MarkReadRequest
from app.services.notifications import mark_all_read, mark_notification_read, unread_count
from app.services.pagination import decode_datetime_cursor, encode_datetime_cursor
from app.web import ApiError, get_current_user, require_csrf

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


@router.get("/unread-count")
async def get_unread_count(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> dict[str, int]:
    return {"unread_count": await unread_count(db, user.id)}


@router.get("")
async def list_notifications(
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    unread_only: bool = False,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    query = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        query = query.where(Notification.read_at.is_(None))
    if cursor:
        created_at, row_id = decode_datetime_cursor(cursor)
        query = query.where(
            or_(
                Notification.created_at < created_at,
                and_(Notification.created_at == created_at, Notification.id < row_id),
            )
        )
    rows = list(
        (
            await db.scalars(
                query.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(limit + 1)
            )
        ).all()
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    return {
        "items": [
            {
                "id": str(row.id),
                "type": row.type,
                "read_at": row.read_at,
                "created_at": row.created_at,
                "data": row.data,
                "url": row.data["url"],
            }
            for row in rows
        ],
        "next_cursor": encode_datetime_cursor(rows[-1].created_at, rows[-1].id) if has_more and rows else None,
        "unread_count": await unread_count(db, user.id),
    }


@router.get("/{notification_id}")
async def get_notification(
    notification_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = await db.scalar(
        select(Notification).where(Notification.id == notification_id, Notification.user_id == user.id)
    )
    if row is None:
        raise ApiError(404, "not_found", "Notification not found.")
    return {
        "id": str(row.id),
        "type": row.type,
        "read_at": row.read_at,
        "created_at": row.created_at,
        "data": row.data,
        "url": row.data["url"],
    }


@router.patch("/read-all", status_code=204, dependencies=[Depends(require_csrf)])
async def read_all_notifications(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> Response:
    await mark_all_read(db, user.id)
    await db.commit()
    return Response(status_code=204)


@router.patch("/{notification_id}", dependencies=[Depends(require_csrf)])
async def mark_read(
    notification_id: UUID,
    payload: MarkReadRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if not payload.read:
        raise ApiError(422, "validation_error", "Notifications can only be marked as read.", {"read": "Set read to true."})
    row = await mark_notification_read(db, notification_id, user.id)
    await db.commit()
    return {"id": str(row.id), "read_at": row.read_at}


@router.delete("/{notification_id}", status_code=204, dependencies=[Depends(require_csrf)])
async def delete_notification(
    notification_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    result = await db.execute(
        delete(Notification).where(Notification.id == notification_id, Notification.user_id == user.id)
    )
    if result.rowcount == 0:
        raise ApiError(404, "not_found", "Notification not found.")
    await db.commit()
    return Response(status_code=204)


@router.delete("", status_code=204, dependencies=[Depends(require_csrf)])
async def clear_notifications(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> Response:
    await db.execute(delete(Notification).where(Notification.user_id == user.id))
    await db.commit()
    return Response(status_code=204)
