import re
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import User
from app.models.domain import (
    Course,
    Interest,
    Photo,
    Profile,
    Skill,
    profile_interests,
    profile_skills,
)
from app.web import ApiError


def profile_is_complete(role: str | None, skill_count: int) -> bool:
    return role is not None and skill_count > 0


async def get_or_create_profile(db: AsyncSession, user_id: UUID) -> Profile:
    profile = await db.scalar(select(Profile).where(Profile.user_id == user_id).with_for_update())
    if profile is None:
        profile = Profile(user_id=user_id)
        db.add(profile)
        await db.flush()
    return profile


async def profile_payload(db: AsyncSession, user: User, private: bool) -> dict:
    profile = await db.scalar(select(Profile).where(Profile.user_id == user.id))
    if profile is None:
        profile = await get_or_create_profile(db, user.id)
    course = await db.get(Course, profile.course_id) if profile.course_id else None
    skills = list(
        (
            await db.scalars(
                select(Skill).join(profile_skills, profile_skills.c.skill_id == Skill.id)
                .where(profile_skills.c.profile_id == profile.id)
                .order_by(Skill.name)
            )
        ).all()
    )
    interests = list(
        (
            await db.scalars(
                select(Interest).join(profile_interests, profile_interests.c.interest_id == Interest.id)
                .where(profile_interests.c.profile_id == profile.id)
                .order_by(Interest.name)
            )
        ).all()
    )
    has_photo = profile.photo_id is not None
    result = {
        "id": str(user.id),
        "display_name": user.display_name,
        "first_name": user.first_name,
        "profile": {
            "bio": profile.bio,
            "role": profile.role,
            "course": {"id": str(course.id), "name": course.name} if course else None,
            "looking_for": profile.looking_for,
            "skills": [{"id": str(skill.id), "name": skill.name} for skill in skills],
            "interests": [{"id": str(interest.id), "name": interest.name} for interest in interests],
            "has_photo": has_photo,
            "photo_url": f"/api/v1/users/{user.id}/photo" if has_photo else None,
        },
    }
    if private:
        result.update(
            {
                "email": user.email,
                "is_admin": user.is_admin,
                "is_active": user.is_active,
                "created_at": user.created_at,
                "profile_complete": profile.profile_complete,
            }
        )
        result["profile"]["profile_complete"] = profile.profile_complete
    return result


async def update_profile(db: AsyncSession, user: User, values: dict) -> dict:
    profile = await get_or_create_profile(db, user.id)
    if "user_id" in values:
        raise ApiError(403, "not_profile_owner", "You can only update your own profile.")

    for field in ("bio", "looking_for", "role"):
        if field in values:
            setattr(profile, field, values[field])

    if "course_id" in values:
        course_id = values["course_id"]
        if course_id is not None and await db.get(Course, course_id) is None:
            raise ApiError(422, "validation_error", "Select a valid course.", {"course_id": "Unknown course."})
        profile.course_id = course_id

    if "skill_ids" in values:
        ids = values["skill_ids"]
        found = set((await db.scalars(select(Skill.id).where(Skill.id.in_(ids)))).all()) if ids else set()
        if len(found) != len(set(ids)):
            raise ApiError(422, "validation_error", "Select valid skills.", {"skill_ids": "One or more skills do not exist."})
        await db.execute(delete(profile_skills).where(profile_skills.c.profile_id == profile.id))
        for skill_id in set(ids):
            await db.execute(profile_skills.insert().values(profile_id=profile.id, skill_id=skill_id))

    if "interest_ids" in values:
        ids = values["interest_ids"]
        found = set((await db.scalars(select(Interest.id).where(Interest.id.in_(ids)))).all()) if ids else set()
        if len(found) != len(set(ids)):
            raise ApiError(
                422, "validation_error", "Select valid interests.", {"interest_ids": "One or more interests do not exist."}
            )
        await db.execute(delete(profile_interests).where(profile_interests.c.profile_id == profile.id))
        for interest_id in set(ids):
            await db.execute(profile_interests.insert().values(profile_id=profile.id, interest_id=interest_id))

    skill_count = await db.scalar(
        select(profile_skills.c.skill_id).where(profile_skills.c.profile_id == profile.id).limit(1)
    )
    profile.profile_complete = profile_is_complete(profile.role, int(skill_count is not None))
    profile.updated_at = datetime.now(UTC)
    await db.flush()
    return await profile_payload(db, user, private=True)


def detect_photo_type(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def clean_text(value: str | None, maximum: int, field: str) -> str | None:
    if value is None:
        return None
    trimmed = value.strip()
    if len(trimmed) > maximum:
        raise ApiError(422, "validation_error", f"{field} is too long.", {field: f"Use at most {maximum} characters."})
    return trimmed or None


def normalise_name(value: str, maximum: int = 50) -> str:
    value = re.sub(r"\s+", " ", value.strip())
    if not value or len(value) > maximum:
        raise ApiError(422, "validation_error", "Enter a valid name.")
    return value
