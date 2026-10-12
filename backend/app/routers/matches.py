from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.auth import User
from app.services.match_queries import get_matches
from app.web import ApiError, get_current_user

router = APIRouter(prefix="/api/v1/matches", tags=["matching"])


@router.get("")
async def list_matches(
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    skill: list[str] = Query(default=[]),
    role: Literal["software_developer", "business_developer"] | None = None,
    course_id: UUID | None = None,
    interest: list[str] = Query(default=[]),
    exclude_connected: bool = True,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await get_matches(
        db,
        user,
        limit=limit,
        cursor=cursor,
        skills=skill,
        role=role,
        course_id=course_id,
        interests=interest,
        exclude_connected=exclude_connected,
    )


@router.get("/{user_id}")
async def get_match(
    user_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await get_matches(
        db,
        user,
        limit=1,
        cursor=None,
        skills=[],
        role=None,
        course_id=None,
        interests=[],
        exclude_connected=True,
        candidate_id=user_id,
    )
    if not result["items"]:
        raise ApiError(404, "not_found", "Match not found.")
    return result["items"][0]
