import hashlib
from uuid import UUID

from fastapi import APIRouter, Depends, File, Header, Query, Response, UploadFile
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.auth import User
from app.models.domain import Course, Interest, Photo, Profile, Skill
from app.schemas.profiles import ProfileUpdate, UserPrivate, UserPublic
from app.services.profiles import (
    clean_text,
    detect_photo_type,
    get_or_create_profile,
    normalise_name,
    profile_payload,
    update_profile,
)
from app.services.pagination import decode_name_cursor, encode_name_cursor
from app.web import AuthContext, ApiError, get_current_user, get_optional_auth_context, require_csrf

router = APIRouter(prefix="/api/v1", tags=["profiles"])
MAX_PHOTO_BYTES = 2 * 1024 * 1024


@router.get("/users/me", response_model=UserPrivate)
async def get_my_profile(
    response: Response,
    context: AuthContext | None = Depends(get_optional_auth_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if context is None:
        raise ApiError(401, "unauthenticated", "Sign in to continue.")
    response.headers["X-CSRF-Token"] = context.session.csrf_token.decode("ascii")
    user = context.user
    result = await profile_payload(db, user, private=True)
    await db.commit()
    return result


@router.patch("/users/me", response_model=UserPrivate, dependencies=[Depends(require_csrf)])
async def patch_my_profile(
    payload: ProfileUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    values = payload.model_dump(exclude_unset=True)
    if "bio" in values:
        values["bio"] = clean_text(values["bio"], 500, "bio")
    if "looking_for" in values:
        values["looking_for"] = clean_text(values["looking_for"], 300, "looking_for")
    result = await update_profile(db, user, values)
    await db.commit()
    return result


@router.post("/users/me/photo", status_code=201, dependencies=[Depends(require_csrf)])
async def upload_photo(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    data = await file.read(MAX_PHOTO_BYTES + 1)
    if len(data) > MAX_PHOTO_BYTES:
        raise ApiError(413, "file_too_large", "Choose an image smaller than 2 MB.")
    if not data:
        raise ApiError(422, "validation_error", "Choose an image file.", {"file": "The file is empty."})
    content_type = detect_photo_type(data)
    if content_type is None:
        raise ApiError(415, "unsupported_media_type", "Upload a JPEG, PNG, or WebP image.")

    profile = await get_or_create_profile(db, user.id)
    old_photo = await db.scalar(select(Photo).where(Photo.user_id == user.id).with_for_update())
    if old_photo is not None:
        await db.delete(old_photo)
        await db.flush()
    photo = Photo(user_id=user.id, content_type=content_type, byte_size=len(data), data=data)
    db.add(photo)
    await db.flush()
    profile.photo_id = photo.id
    await db.commit()
    return {"photo_url": f"/api/v1/users/{user.id}/photo"}


@router.delete("/users/me/photo", status_code=204, dependencies=[Depends(require_csrf)])
async def delete_my_photo(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> Response:
    photo = await db.scalar(select(Photo).where(Photo.user_id == user.id).with_for_update())
    if photo is not None:
        await db.delete(photo)
        await db.commit()
    return Response(status_code=204)


async def photo_response(user_id: UUID, db: AsyncSession, if_none_match: str | None) -> Response:
    photo = await db.scalar(select(Photo).where(Photo.user_id == user_id))
    if photo is None:
        raise ApiError(404, "not_found", "Photo not found.")
    etag = f'"{hashlib.sha256(photo.data).hexdigest()}"'
    headers = {"Cache-Control": "private, max-age=86400", "ETag": etag}
    if if_none_match == etag:
        return Response(status_code=304, headers=headers)
    return Response(content=photo.data, media_type=photo.content_type, headers=headers)


@router.get("/users/me/photo")
async def get_my_photo(
    if_none_match: str | None = Header(default=None, alias="If-None-Match"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    return await photo_response(user.id, db, if_none_match)


@router.get("/users/{user_id}/photo")
async def get_user_photo(
    user_id: UUID,
    if_none_match: str | None = Header(default=None, alias="If-None-Match"),
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    owner = await db.scalar(select(User).where(User.id == user_id, User.is_active.is_(True)))
    if owner is None:
        raise ApiError(404, "not_found", "Photo not found.")
    return await photo_response(user_id, db, if_none_match)


@router.get("/users/{user_id}", response_model=UserPublic)
async def get_public_profile(
    user_id: UUID,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await db.scalar(select(User).where(User.id == user_id, User.is_active.is_(True)))
    if user is None:
        raise ApiError(404, "not_found", "User not found.")
    result = await profile_payload(db, user, private=False)
    await db.commit()
    return result


async def references(db: AsyncSession, model, limit: int, cursor: str | None) -> dict:
    query = select(model)
    if cursor:
        name, row_id = decode_name_cursor(cursor)
        query = query.where(or_(model.name > name, and_(model.name == name, model.id > row_id)))
    rows = list((await db.scalars(query.order_by(model.name, model.id).limit(limit + 1))).all())
    more = len(rows) > limit
    rows = rows[:limit]
    return {
        "items": [
            {
                "id": str(row.id),
                "name": row.name,
                **({"category": row.category} if isinstance(row, Skill) else {}),
            }
            for row in rows
        ],
        "next_cursor": encode_name_cursor(rows[-1].name, rows[-1].id) if more and rows else None,
    }


@router.get("/courses")
async def list_courses(
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await references(db, Course, limit, cursor)


@router.get("/skills")
async def list_skills(
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await references(db, Skill, limit, cursor)


@router.get("/interests")
async def list_interests(
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await references(db, Interest, limit, cursor)
