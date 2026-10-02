"""Profiles. Spec 03 §3-§8.

profile_complete = role IS NOT NULL AND count(skills) >= 1. Nothing else.
Cached and recomputed on every update; never trust a client-supplied value.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import delete, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.errors import (
    NotFound,
    UnsupportedMediaType,
    ValidationFailed,
)
from app.models import (
    Course,
    Interest,
    Photo,
    Profile,
    Skill,
    User,
    profile_interests,
    profile_skills,
)

ALLOWED_IMAGE_TYPES = {
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/webp": (b"RIFF",),
}
MAX_PROFILE_SKILLS = 20
MAX_PROFILE_INTERESTS = 20


# ─── Profile completeness ────────────────────────────────────────────────────


async def recompute_profile_complete(db: AsyncSession, profile: Profile) -> bool:
    count = await db.scalar(
        select(func.count())
        .select_from(profile_skills)
        .where(profile_skills.c.profile_id == profile.id)
    )
    complete = profile.role is not None and (count or 0) >= 1
    profile.profile_complete = complete
    return complete


# ─── Fetch ───────────────────────────────────────────────────────────────────


async def get_or_create_profile(db: AsyncSession, user: User) -> Profile:
    """Queries rather than touching user.profile. A just-created User has no
    loaded relationship state, so an attribute access there triggers a lazy
    load outside async context."""
    profile = await db.scalar(
        select(Profile)
        .options(
            selectinload(Profile.skills),
            selectinload(Profile.interests),
            selectinload(Profile.course),
        )
        .where(Profile.user_id == user.id)
    )
    if profile is None:
        db.add(Profile(user_id=user.id))
        await db.flush()
        # Re-query rather than returning the new object: eager-load options apply
        # to the SELECT, so a freshly inserted profile still has unloaded
        # collections that would raise on attribute access.
        profile = await db.scalar(
            select(Profile)
            .options(
                selectinload(Profile.skills),
                selectinload(Profile.interests),
                selectinload(Profile.course),
            )
            .where(Profile.user_id == user.id)
        )
    return profile


async def load_profiles(db: AsyncSession) -> dict[uuid.UUID, Profile]:
    """Eager-load skills/interests/course for a set of users in one pass."""
    result = await db.execute(
        select(Profile)
        .options(
            selectinload(Profile.skills),
            selectinload(Profile.interests),
            selectinload(Profile.course),
        )
        .where(Profile.user_id.in_(select(User.id)))
    )
    return {p.user_id: p for p in result.scalars().all()}


async def get_public_profile(db: AsyncSession, user_id: uuid.UUID) -> Profile:
    result = await db.execute(
        select(Profile)
        .options(
            selectinload(Profile.skills),
            selectinload(Profile.interests),
            selectinload(Profile.course),
        )
        .where(Profile.user_id == user_id)
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        raise NotFound("That person does not have a profile.")
    return profile


# ─── Update ──────────────────────────────────────────────────────────────────


async def update_profile(
    db: AsyncSession,
    user: User,
    *,
    bio: str | None = None,
    role: str | None = None,
    course_id: uuid.UUID | None = None,
    looking_for: str | None = None,
    skill_ids: list[uuid.UUID] | None = None,
    interest_ids: list[uuid.UUID] | None = None,
) -> Profile:
    settings = get_settings()
    profile = await get_or_create_profile(db, user)

    if bio is not None:
        cleaned = _strip_markup(bio)
        if len(cleaned) > settings.max_bio_chars:
            raise ValidationFailed({"bio": f"Must be {settings.max_bio_chars} characters or fewer."})
        profile.bio = cleaned or None

    if role is not None:
        profile.role = role or None

    if looking_for is not None:
        cleaned = looking_for.strip()
        if len(cleaned) > settings.max_looking_for_chars:
            raise ValidationFailed(
                {"looking_for": f"Must be {settings.max_looking_for_chars} characters or fewer."}
            )
        profile.looking_for = cleaned or None

    if course_id is not None:
        exists = await db.scalar(select(Course.id).where(Course.id == course_id))
        if not exists:
            raise ValidationFailed({"course_id": "Unknown course."})
        profile.course_id = course_id

    # Replacing wholesale rather than add/remove endpoints: one array in, one
    # array out, no diffing logic, no separate removal route.
    if skill_ids is not None:
        if len(skill_ids) > MAX_PROFILE_SKILLS:
            raise ValidationFailed({"skill_ids": f"At most {MAX_PROFILE_SKILLS} skills."})
        await _replace_refs(db, profile.id, skill_ids, Skill, profile_skills, "skill_id", "skill_ids")
    if interest_ids is not None:
        if len(interest_ids) > MAX_PROFILE_INTERESTS:
            raise ValidationFailed(
                {"interest_ids": f"At most {MAX_PROFILE_INTERESTS} interests."}
            )
        await _replace_refs(
            db,
            profile.id,
            interest_ids,
            Interest,
            profile_interests,
            "interest_id",
            "interest_ids",
        )

    await db.flush()
    await recompute_profile_complete(db, profile)
    await db.commit()
    return await get_public_profile(db, user.id)


async def _replace_refs(
    db: AsyncSession,
    profile_id: uuid.UUID,
    ids: list[uuid.UUID],
    model,
    table,
    column: str,
    field: str,
) -> None:
    unique_ids = list(dict.fromkeys(ids))
    if unique_ids:
        found = set(await db.scalars(select(model.id).where(model.id.in_(unique_ids))))
        missing = [i for i in unique_ids if i not in found]
        if missing:
            raise ValidationFailed({field: "Unknown skill or interest."})
    await db.execute(delete(table).where(table.c.profile_id == profile_id))
    for ref_id in unique_ids:
        await db.execute(
            insert(table).values(profile_id=profile_id, **{column: ref_id})
        )


def _strip_markup(text: str) -> str:
    """Bios are stored and rendered as plain text. React escapes by default, so
    there is no XSS hole — but strip tags anyway so stored data is clean."""
    import re

    return re.sub(r"<[^>]*>", "", text).strip()


# ─── Photos ──────────────────────────────────────────────────────────────────


def sniff_image_type(data: bytes) -> str | None:
    """Check the actual bytes. A client can send a shell script labelled
    image/png — this is the only control point. Spec 03 §4."""
    for content_type, magic in ALLOWED_IMAGE_TYPES.items():
        if data.startswith(magic):
            if content_type == "image/webp":
                # RIFF....WEBP
                if len(data) >= 12 and data[8:12] == b"WEBP":
                    return content_type
            else:
                return content_type
    return None


async def save_photo(
    db: AsyncSession, user: User, *, data: bytes, declared_type: str | None = None
) -> Photo:
    settings = get_settings()
    if not data:
        raise ValidationFailed({"file": "The file is empty."})
    if len(data) > settings.max_photo_bytes:
        from app.errors import PayloadTooLarge

        raise PayloadTooLarge(
            f"Photos must be {settings.max_photo_bytes // (1024 * 1024)} MB or smaller."
        )

    actual = sniff_image_type(data)
    if actual is None:
        raise UnsupportedMediaType("Photos must be JPEG, PNG or WebP.")

    # Replacing deletes the old row — one photo per user.
    await db.execute(delete(Photo).where(Photo.user_id == user.id))

    photo = Photo(
        user_id=user.id,
        content_type=actual,
        byte_size=len(data),
        data=data,
    )
    db.add(photo)
    await db.flush()

    profile = await get_or_create_profile(db, user)
    profile.photo_id = photo.id
    await db.commit()
    return photo


async def delete_photo(db: AsyncSession, user: User) -> None:
    await db.execute(delete(Photo).where(Photo.user_id == user.id))
    profile = await get_or_create_profile(db, user)
    profile.photo_id = None
    await db.commit()


async def get_photo(db: AsyncSession, user_id: uuid.UUID) -> Photo:
    photo = await db.scalar(select(Photo).where(Photo.user_id == user_id))
    if photo is None:
        raise NotFound("No photo.")
    return photo


def profile_photo_url(user_id: uuid.UUID) -> str:
    return f"/api/v1/users/{user_id}/photo"


async def has_photo(db: AsyncSession, user_ids: list[uuid.UUID]) -> set[uuid.UUID]:
    """Never select photos.data here — that would load every image into memory.
    decisions/0006-images-as-pg-blob.md."""
    if not user_ids:
        return set()
    result = await db.execute(
        select(Photo.user_id).where(Photo.user_id.in_(user_ids))
    )
    return set(result.scalars().all())


__all__ = [
    "recompute_profile_complete",
    "get_or_create_profile",
    "get_public_profile",
    "update_profile",
    "sniff_image_type",
    "save_photo",
    "delete_photo",
    "get_photo",
    "has_photo",
    "profile_photo_url",
    "ALLOWED_IMAGE_TYPES",
]