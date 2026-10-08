"""Users and profiles. Specs 02 §3 and 03 §4."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.db import get_db
from app.dependencies import (
    get_current_user,
    require_csrf,
    require_profile_complete,
    require_session,
)
from app.errors import NotFound
from app.models import Course, Interest, Session, Skill, User
from app.schemas import (
    CourseOut,
    RefOut,
    UpdateProfileRequest,
    UserPrivate,
    UserPublic,
)
from app.serializers import user_private, user_public
from app.services.auth import encode_csrf
from app.services import profiles as prof_svc

router = APIRouter(prefix="/api/v1", tags=["users"])


def eager(user: User) -> User:
    for attr in ("profile",):
        setattr(user, attr, getattr(user, attr, None))
    if user.profile is not None:
        for rel in ("skills", "interests", "course"):
            getattr(user.profile, rel)
    return user


class MeOut(UserPrivate):
    """Own account plus the CSRF token the client needs for mutating requests.

    The session cookie is httpOnly so JS cannot read it; the CSRF token is
    deliberately readable and sent back in the X-CSRF-Token header.
    """

    csrf_token: str


@router.get("/users/me", response_model=MeOut)
async def me(
    pair: tuple[Session, User] = Depends(require_session),
    db: AsyncSession = Depends(get_db),
):
    session, user = pair
    profile = await prof_svc.get_or_create_profile(db, user)
    body = user_private(user, profile)
    return MeOut(**body.model_dump(), csrf_token=encode_csrf(session.csrf_token))


@router.patch("/users/me", response_model=UserPrivate, dependencies=[Depends(require_csrf)])
async def update_me(
    payload: UpdateProfileRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    profile = await prof_svc.update_profile(
        db,
        user,
        bio=payload.bio,
        role=payload.role,
        course_id=payload.course_id,
        looking_for=payload.looking_for,
        skill_ids=payload.skill_ids,
        interest_ids=payload.interest_ids,
    )
    return user_private(user, profile)


@router.post("/users/me/photo", dependencies=[Depends(require_csrf)])
async def upload_photo(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await file.read()
    await prof_svc.save_photo(db, user, data=data, declared_type=file.content_type)
    return {"ok": True, "photo_url": f"/api/v1/users/{user.id}/photo"}


@router.delete("/users/me/photo", status_code=204, dependencies=[Depends(require_csrf)])
async def delete_photo(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    await prof_svc.delete_photo(db, user)
    return Response(status_code=204)


@router.get("/users/me/photo")
async def own_photo(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    photo = await prof_svc.get_photo(db, user.id)
    return _image_response(photo.content_type, photo.data)


@router.get("/users/{user_id}", response_model=UserPublic)
async def public_profile(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _me: User = Depends(get_current_user),
):
    """No email. Deactivated users 404 rather than showing a ghost profile."""
    from app.models import Profile

    result = await db.execute(
        select(User)
        .options(
            selectinload(User.profile).selectinload(Profile.skills),
            selectinload(User.profile).selectinload(Profile.interests),
            selectinload(User.profile).selectinload(Profile.course),
        )
        .where(User.id == user_id)
    )
    target = result.scalar_one_or_none()
    if target is None or not target.is_active:
        raise NotFound("That person does not exist.")
    profile = await prof_svc.get_public_profile(db, user_id)
    return user_public(target, profile)


@router.get("/users/{user_id}/photo")
async def user_photo(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _me: User = Depends(get_current_user),
):
    """Session required. A signed-out stranger must not get the cohort's photos,
    so this is never a static directory."""
    photo = await prof_svc.get_photo(db, user_id)
    return _image_response(photo.content_type, photo.data)


def _image_response(content_type: str, data: bytes) -> Response:
    import hashlib

    etag = '"' + hashlib.md5(data).hexdigest() + '"'
    return Response(
        content=data,
        media_type=content_type,
        headers={
            "Cache-Control": "private, max-age=86400",
            "ETag": etag,
        },
    )


# ─── Reference data for the forms ────────────────────────────────────────────


@router.get("/courses", response_model=list[CourseOut])
async def list_courses(db: AsyncSession = Depends(get_db), _me: User = Depends(get_current_user)):
    return [CourseOut(id=c.id, name=c.name) for c in await db.scalars(select(Course).order_by(Course.name))]


@router.get("/skills", response_model=list[RefOut])
async def list_skills(
    q: str | None = None,
    db: AsyncSession = Depends(get_db),
    _me: User = Depends(get_current_user),
):
    from sqlalchemy import select

    stmt = select(Skill).order_by(Skill.name)
    if q:
        stmt = stmt.where(Skill.name.ilike(f"%{q.strip()}%"))
    return [RefOut(id=s.id, name=s.name) for s in await db.scalars(stmt.limit(200))]


@router.get("/interests", response_model=list[RefOut])
async def list_interests(
    q: str | None = None,
    db: AsyncSession = Depends(get_db),
    _me: User = Depends(get_current_user)):
    from sqlalchemy import select

    stmt = select(Interest).order_by(Interest.name)
    if q:
        stmt = stmt.where(Interest.name.ilike(f"%{q.strip()}%"))
    return [RefOut(id=i.id, name=i.name) for i in await db.scalars(stmt.limit(200))]


from sqlalchemy import select  # noqa: E402

__all__ = ["router"]