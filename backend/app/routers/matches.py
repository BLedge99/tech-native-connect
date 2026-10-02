"""Matching routes. Spec 04."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.dependencies import get_current_user
from app.models import User
from app.schemas import MatchOut, Page
from app.serializers import match_out
from app.services import match_service
from app.services.connections import accepted_request_for

router = APIRouter(prefix="/api/v1", tags=["matches"])


@router.get("/matches", response_model=Page)
async def list_matches(
    limit: int = Query(default=20, ge=1, le=100),
    skill: list[str] = Query(default=[]),
    interest: list[str] = Query(default=[]),
    role: str | None = None,
    course_id: uuid.UUID | None = None,
    exclude_connected: bool = True,
    cursor: str | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Filters narrow the candidate set, scoring ranks within it. Never the
    reverse — that gives short pages and wrong counts."""
    skill_ids = await match_service.resolve_names(db, "skill", skill)
    interest_ids = await match_service.resolve_names(db, "interest", interest)
    if role not in (None, "software_developer", "business_developer"):
        from app.errors import ValidationFailed

        raise ValidationFailed({"role": "Unknown role."})

    items = await match_service.rank_for_viewer(
        db,
        user,
        skill_ids=skill_ids,
        interest_ids=interest_ids,
        role=role,
        course_id=course_id,
        exclude_connected=exclude_connected,
        limit=limit + 1,
        cursor=cursor,
    )
    items = items[:limit]
    has_more = len(items) == limit
    # The cursor encodes (score, user_id) so the ordering is a total order.
    # A fuzzy tiebreak would let page 2 repeat rows from page 1.
    last = items[-1] if items else None
    return Page(
        items=[match_out(i) for i in items],
        next_cursor=(
            match_service.encode_cursor(last.score, last.user.id) if has_more and last else None
        ),
    )


@router.get("/matches/{user_id}", response_model=MatchOut)
async def match_detail(
    user_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.errors import NotFound

    items = await match_service.rank_for_viewer(db, user, limit=100)
    for item in items:
        if item.user.id == user_id:
            return match_out(item)
    # Excluded users are 404, not 403: existence as a match is not the
    # caller's business.
    raise NotFound("That person is not in your matches.")


__all__ = ["router"]