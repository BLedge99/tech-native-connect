"""Project ideas routes. Spec 08."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_db
from app.dependencies import get_current_user, require_csrf, require_profile_complete
from app.models import Course, ProjectIdea, User
from app.schemas import IdeaIn, IdeaOut, IdeaUpdate, Page
from app.serializers import idea_out
from app.services import ideas as svc
from app.services.pagination import encode_cursor

router = APIRouter(prefix="/api/v1/ideas", tags=["ideas"])


@router.get("", response_model=Page)
async def list_ideas(
    category: list[str] = Query(default=[]),
    search: str | None = None,
    author_id: uuid.UUID | None = None,
    mine: bool = False,
    open_only: bool = True,
    limit: int = Query(default=20, ge=1, le=50),
    cursor: str | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = await svc.list_ideas(
        db,
        categories=category or None,
        search=search,
        author_id=author_id,
        mine=mine,
        viewer_id=user.id,
        open_only=open_only,
        limit=limit,
        cursor=cursor,
    )
    authors = {
        u.id: u
        for u in await db.scalars(
            select(User).where(User.id.in_([i.author_id for i, _, _ in rows] or [user.id]))
        )
    }
    course_names = dict(
        (
            await db.execute(
                select(Course.id, Course.name).where(
                    Course.id.in_([i.course_id for i, _, _ in rows if i.course_id] or [None])
                )
            )
        ).all()
    )
    items = [
        idea_out(
            idea,
            authors.get(idea.author_id),
            interest_count=count,
            viewer_has_interested=mine_interested,
            course_name=course_names.get(idea.course_id),
        )
        for idea, count, mine_interested in rows
        if idea.author_id in authors
    ]
    # Only report another page if the query found limit + 1 rows.
    has_more = len(rows) > limit
    return Page(
        items=items[:limit],
        next_cursor=(
            encode_cursor(rows[limit - 1][0].created_at, rows[limit - 1][0].id) if has_more else None
        ),
    )


@router.post("", status_code=201, response_model=IdeaOut, dependencies=[Depends(require_csrf)])
async def create_idea(
    payload: IdeaIn,
    user: User = Depends(require_profile_complete),
    db: AsyncSession = Depends(get_db),
):
    """A complete profile is required: matching cannot surface you to the
    developers your idea is for otherwise."""
    idea = await svc.create_idea(
        db,
        user,
        title=payload.title,
        description=payload.description,
        category=payload.category,
        skills_needed=payload.skills_needed,
        course_id=payload.course_id,
    )
    course_name = None
    if idea.course_id:
        course_name = await db.scalar(select(Course.name).where(Course.id == idea.course_id))
    return idea_out(idea, user, course_name=course_name)


@router.get("/{idea_id}", response_model=IdeaOut)
async def get_idea(
    idea_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    idea = await svc.get_idea(db, idea_id)
    author = await db.get(User, idea.author_id)
    rows = await svc.list_ideas(
        db, categories=[idea.category], open_only=False, viewer_id=user.id, limit=200
    )
    found = next(((i, c, m) for i, c, m in rows if i.id == idea.id), (idea, 0, False))
    course_name = None
    if idea.course_id:
        course_name = await db.scalar(select(Course.name).where(Course.id == idea.course_id))
    return idea_out(found[0], author, interest_count=found[1],
                    viewer_has_interested=found[2], course_name=course_name)


@router.patch("/{idea_id}", response_model=IdeaOut, dependencies=[Depends(require_csrf)])
async def update_idea(
    idea_id: uuid.UUID,
    payload: IdeaUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    idea = await svc.get_idea(db, idea_id)
    idea = await svc.update_idea(db, idea, user, **payload.model_dump(exclude_unset=True))
    author = await db.get(User, idea.author_id)
    course_name = None
    if idea.course_id:
        course_name = await db.scalar(select(Course.name).where(Course.id == idea.course_id))
    return idea_out(idea, author, course_name=course_name)


@router.delete("/{idea_id}", status_code=204, dependencies=[Depends(require_csrf)])
async def delete_idea(
    idea_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    idea = await svc.get_idea(db, idea_id)
    await svc.delete_idea(db, idea, user)
    return Response(status_code=204)


@router.post("/{idea_id}/interest", dependencies=[Depends(require_csrf)])
async def express_interest(
    idea_id: uuid.UUID,
    user: User = Depends(require_profile_complete),
    db: AsyncSession = Depends(get_db),
):
    """Idempotent — a double-click must not show an error."""
    idea = await svc.get_idea(db, idea_id)
    await svc.express_interest(db, idea, user)
    return {"ok": True}


@router.delete("/{idea_id}/interest", status_code=204, dependencies=[Depends(require_csrf)])
async def withdraw_interest(
    idea_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    idea = await svc.get_idea(db, idea_id)
    await svc.withdraw_interest(db, idea, user)
    return Response(status_code=204)


__all__ = ["router"]