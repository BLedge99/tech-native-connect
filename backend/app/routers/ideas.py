from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.auth import User
from app.models.domain import Notification, ProjectIdea
from app.realtime import manager
from app.schemas.ideas import IdeaCreate, IdeaUpdate
from app.services.ideas import (
    create_idea,
    delete_idea,
    express_interest,
    idea_payload,
    update_idea,
    withdraw_interest,
)
from app.services.pagination import decode_datetime_cursor, encode_datetime_cursor
from app.web import ApiError, get_current_user, require_csrf

router = APIRouter(prefix="/api/v1/ideas", tags=["ideas"])


@router.get("")
async def list_ideas(
    category: list[Literal["find_problem", "build_product", "design_brand", "run_campaign", "other"]] = Query(default=[]),
    search: str | None = Query(default=None, max_length=100),
    author_id: UUID | None = None,
    mine: bool = False,
    open_only: bool = True,
    limit: int = Query(default=20, ge=1, le=50),
    cursor: str | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    query = select(ProjectIdea)
    if open_only:
        query = query.where(ProjectIdea.is_open.is_(True))
    if category:
        query = query.where(ProjectIdea.category.in_(category))
    if search and search.strip():
        pattern = f"%{search.strip()}%"
        query = query.where(or_(ProjectIdea.title.ilike(pattern), ProjectIdea.description.ilike(pattern)))
    if mine:
        query = query.where(ProjectIdea.author_id == user.id)
    elif author_id:
        query = query.where(ProjectIdea.author_id == author_id)
    if cursor:
        created_at, row_id = decode_datetime_cursor(cursor)
        query = query.where(
            or_(
                ProjectIdea.created_at < created_at,
                and_(ProjectIdea.created_at == created_at, ProjectIdea.id < row_id),
            )
        )
    rows = list(
        (
            await db.scalars(
                query.order_by(ProjectIdea.created_at.desc(), ProjectIdea.id.desc()).limit(limit + 1)
            )
        ).all()
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    return {
        "items": [await idea_payload(db, idea, user.id) for idea in rows],
        "next_cursor": encode_datetime_cursor(rows[-1].created_at, rows[-1].id) if has_more and rows else None,
    }


@router.post("", status_code=201, dependencies=[Depends(require_csrf)])
async def post_idea(
    payload: IdeaCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    idea = await create_idea(db, user, payload.model_dump())
    result = await idea_payload(db, idea, user.id)
    await db.commit()
    return result


@router.get("/{idea_id}")
async def get_idea(
    idea_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    idea = await db.get(ProjectIdea, idea_id)
    if idea is None:
        raise ApiError(404, "not_found", "Project idea not found.")
    return await idea_payload(db, idea, user.id)


@router.patch("/{idea_id}", dependencies=[Depends(require_csrf)])
async def patch_idea(
    idea_id: UUID,
    payload: IdeaUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    idea = await update_idea(db, idea_id, user, payload.model_dump(exclude_unset=True))
    result = await idea_payload(db, idea, user.id)
    await db.commit()
    return result


@router.delete("/{idea_id}", status_code=204, dependencies=[Depends(require_csrf)])
async def remove_idea(
    idea_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    await delete_idea(db, idea_id, user)
    await db.commit()
    return Response(status_code=204)


@router.post("/{idea_id}/interest", dependencies=[Depends(require_csrf)])
async def interest_in_idea(
    idea_id: UUID,
    response: Response,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    interest, created = await express_interest(db, idea_id, user)
    response.status_code = 201 if created else 200
    await db.commit()
    if created:
        notice = await db.scalar(
            select(Notification)
            .where(Notification.project_idea_id == idea_id, Notification.actor_id == user.id)
            .order_by(Notification.created_at.desc())
            .limit(1)
        )
        if notice is not None:
            await manager.send_user(
                notice.user_id,
                {"type": "notification", "data": {"id": str(notice.id), "type": notice.type, **notice.data}},
            )
    return {"idea_id": str(interest.idea_id), "user_id": str(interest.user_id), "created_at": interest.created_at}


@router.delete("/{idea_id}/interest", status_code=204, dependencies=[Depends(require_csrf)])
async def remove_interest(
    idea_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    await withdraw_interest(db, idea_id, user.id)
    await db.commit()
    return Response(status_code=204)
