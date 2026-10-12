from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import User
from app.models.domain import Course, IdeaInterest, Interest, Profile, ProjectIdea, Skill
from app.services.notifications import notify
from app.web import ApiError


async def require_complete_profile(db: AsyncSession, user_id: UUID) -> Profile:
    profile = await db.scalar(select(Profile).where(Profile.user_id == user_id))
    if profile is None or not profile.profile_complete:
        raise ApiError(403, "profile_incomplete", "Choose a role and add at least one skill first.")
    return profile


async def create_idea(db: AsyncSession, user: User, values: dict) -> ProjectIdea:
    profile = await require_complete_profile(db, user.id)
    course_id = values.get("course_id") or profile.course_id
    if course_id is not None and await db.get(Course, course_id) is None:
        raise ApiError(422, "validation_error", "Select a valid course.", {"course_id": "Unknown course."})
    idea = ProjectIdea(author_id=user.id, course_id=course_id, **{key: value for key, value in values.items() if key != "course_id"})
    db.add(idea)
    await db.flush()
    return idea


async def update_idea(db: AsyncSession, idea_id: UUID, actor: User, values: dict) -> ProjectIdea:
    idea = await db.scalar(select(ProjectIdea).where(ProjectIdea.id == idea_id).with_for_update())
    if idea is None:
        raise ApiError(404, "not_found", "Project idea not found.")
    if idea.author_id != actor.id:
        raise ApiError(403, "not_idea_owner", "Only the author can edit this idea.")
    if "course_id" in values and values["course_id"] is not None and await db.get(Course, values["course_id"]) is None:
        raise ApiError(422, "validation_error", "Select a valid course.", {"course_id": "Unknown course."})
    for key, value in values.items():
        setattr(idea, key, value)
    idea.updated_at = datetime.now(UTC)
    await db.flush()
    return idea


async def delete_idea(db: AsyncSession, idea_id: UUID, actor: User) -> None:
    idea = await db.scalar(select(ProjectIdea).where(ProjectIdea.id == idea_id).with_for_update())
    if idea is None:
        raise ApiError(404, "not_found", "Project idea not found.")
    if idea.author_id != actor.id:
        raise ApiError(403, "not_idea_owner", "Only the author can delete this idea.")
    await db.delete(idea)


async def express_interest(db: AsyncSession, idea_id: UUID, actor: User) -> tuple[IdeaInterest | None, bool]:
    await require_complete_profile(db, actor.id)
    idea = await db.scalar(select(ProjectIdea).where(ProjectIdea.id == idea_id).with_for_update())
    if idea is None:
        raise ApiError(404, "not_found", "Project idea not found.")
    if idea.author_id == actor.id:
        raise ApiError(422, "validation_error", "You cannot express interest in your own idea.")
    if not idea.is_open:
        raise ApiError(409, "idea_closed", "This idea is no longer open for interest.")
    result = await db.execute(
        insert(IdeaInterest)
        .values(idea_id=idea.id, user_id=actor.id)
        .on_conflict_do_nothing(index_elements=["idea_id", "user_id"])
    )
    created = result.rowcount == 1
    interest = await db.get(IdeaInterest, (idea.id, actor.id))
    if created:
        author = await db.get(User, idea.author_id)
        await notify(
            db,
            idea.author_id,
            "idea_interest",
            actor,
            idea_id=idea.id,
            text=f'{actor.display_name} is interested in your idea "{idea.title}"',
        )
    await db.flush()
    return interest, created


async def withdraw_interest(db: AsyncSession, idea_id: UUID, user_id: UUID) -> None:
    interest = await db.get(IdeaInterest, (idea_id, user_id))
    if interest is not None:
        await db.delete(interest)


async def idea_payload(db: AsyncSession, idea: ProjectIdea, viewer_id: UUID) -> dict:
    author = await db.get(User, idea.author_id)
    profile = await db.scalar(select(Profile).where(Profile.user_id == idea.author_id))
    course = await db.get(Course, idea.course_id) if idea.course_id else None
    count = int(
        await db.scalar(select(func.count()).select_from(IdeaInterest).where(IdeaInterest.idea_id == idea.id)) or 0
    )
    interest = await db.get(IdeaInterest, (idea.id, viewer_id))
    return {
        "id": str(idea.id),
        "title": idea.title,
        "description": idea.description,
        "category": idea.category,
        "skills_needed": idea.skills_needed,
        "course": {"id": str(course.id), "name": course.name} if course else None,
        "is_open": idea.is_open,
        "interest_count": count,
        "created_at": idea.created_at,
        "updated_at": idea.updated_at,
        "author": {
            "id": str(author.id),
            "display_name": author.display_name,
            "first_name": author.first_name,
            "has_photo": bool(profile and profile.photo_id),
            "photo_url": f"/api/v1/users/{author.id}/photo" if profile and profile.photo_id else None,
        },
        "viewer_has_interested": interest is not None,
        "viewer_is_author": author.id == viewer_id,
    }
