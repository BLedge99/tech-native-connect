from uuid import UUID

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import User
from app.models.domain import (
    ConnectionRequest,
    Course,
    Interest,
    Profile,
    Skill,
    profile_interests,
    profile_skills,
)
from app.services.matching import (
    CANDIDATE_POOL,
    ProfileView,
    decode_match_cursor,
    encode_match_cursor,
    score_match,
)
from app.web import ApiError


async def fetch_profile_views(
    db: AsyncSession, entries: list[tuple[Profile, User, Course | None]]
) -> dict[UUID, ProfileView]:
    if not entries:
        return {}
    profile_by_user = {user.id: profile for profile, user, _ in entries}
    profiles_by_id = {profile.id: profile for profile, _, _ in entries}
    courses = {user.id: course for _, user, course in entries}
    profile_ids = list(profiles_by_id)
    skill_rows = (
        await db.execute(
            select(profile_skills.c.profile_id, Skill.id, Skill.name)
            .join(profile_skills, profile_skills.c.skill_id == Skill.id)
            .where(profile_skills.c.profile_id.in_(profile_ids))
        )
    ).all()
    interest_rows = (
        await db.execute(
            select(profile_interests.c.profile_id, Interest.id, Interest.name)
            .join(profile_interests, profile_interests.c.interest_id == Interest.id)
            .where(profile_interests.c.profile_id.in_(profile_ids))
        )
    ).all()
    skills_by_profile: dict[UUID, dict[UUID, str]] = {profile_id: {} for profile_id in profile_ids}
    interests_by_profile: dict[UUID, dict[UUID, str]] = {profile_id: {} for profile_id in profile_ids}
    for profile_id, skill_id, name in skill_rows:
        skills_by_profile[profile_id][skill_id] = name
    for profile_id, interest_id, name in interest_rows:
        interests_by_profile[profile_id][interest_id] = name
    views = {}
    for _, user, course in entries:
        profile = profile_by_user[user.id]
        profile_skills_by_id = skills_by_profile[profile.id]
        profile_interests_by_id = interests_by_profile[profile.id]
        views[user.id] = ProfileView(
            user_id=user.id,
            display_name=user.display_name,
            role=profile.role,
            course_id=profile.course_id,
            course_name=course.name if course else None,
            skill_ids=frozenset(profile_skills_by_id),
            skill_names=profile_skills_by_id,
            interest_ids=frozenset(profile_interests_by_id),
            interest_names=profile_interests_by_id,
        )
    return views


async def get_matches(
    db: AsyncSession,
    viewer: User,
    *,
    limit: int,
    cursor: str | None,
    skills: list[str],
    role: str | None,
    course_id: UUID | None,
    interests: list[str],
    exclude_connected: bool,
    candidate_id: UUID | None = None,
) -> dict:
    viewer_profile = await db.scalar(select(Profile).where(Profile.user_id == viewer.id))
    if viewer_profile is None or not viewer_profile.profile_complete:
        raise ApiError(
            403,
            "profile_incomplete",
            "Choose a role and add at least one skill before browsing matches.",
        )

    viewer_course = await db.get(Course, viewer_profile.course_id) if viewer_profile.course_id else None
    viewer_view = (
        await fetch_profile_views(db, [(viewer_profile, viewer, viewer_course)])
    )[viewer.id]

    skill_ids: set[UUID] = set()
    if skills:
        matched = list((await db.scalars(select(Skill).where(func.lower(Skill.name).in_([item.lower() for item in skills])))).all())
        if len({item.lower() for item in skills}) != len({item.name.lower() for item in matched}):
            raise ApiError(422, "validation_error", "Unknown skill filter.", {"skill": "Choose an available skill."})
        skill_ids = {item.id for item in matched}
    interest_ids: set[UUID] = set()
    if interests:
        matched_interests = list(
            (
                await db.scalars(
                    select(Interest).where(func.lower(Interest.name).in_([item.lower() for item in interests]))
                )
            ).all()
        )
        if len({item.lower() for item in interests}) != len({item.name.lower() for item in matched_interests}):
            raise ApiError(422, "validation_error", "Unknown interest filter.", {"interest": "Choose an available interest."})
        interest_ids = {item.id for item in matched_interests}

    related_statuses = ["pending", "declined"]
    if exclude_connected:
        related_statuses.append("accepted")
    related = exists(
        select(ConnectionRequest.id).where(
            or_(
                and_(ConnectionRequest.sender_id == viewer.id, ConnectionRequest.receiver_id == User.id),
                and_(ConnectionRequest.receiver_id == viewer.id, ConnectionRequest.sender_id == User.id),
            ),
            ConnectionRequest.status.in_(related_statuses),
        )
    )
    statement = (
        select(Profile, User, Course)
        .join(User, User.id == Profile.user_id)
        .outerjoin(Course, Course.id == Profile.course_id)
        .where(User.is_active.is_(True), User.id != viewer.id, ~related)
    )
    if candidate_id is not None:
        statement = statement.where(User.id == candidate_id)
    if role:
        statement = statement.where(Profile.role == role)
    if course_id:
        statement = statement.where(Profile.course_id == course_id)
    if skill_ids:
        statement = statement.where(
            exists(
                select(profile_skills.c.profile_id).where(
                    profile_skills.c.profile_id == Profile.id,
                    profile_skills.c.skill_id.in_(skill_ids),
                )
            )
        )
    if interest_ids:
        statement = statement.where(
            exists(
                select(profile_interests.c.profile_id).where(
                    profile_interests.c.profile_id == Profile.id,
                    profile_interests.c.interest_id.in_(interest_ids),
                )
            )
        )
    candidates = (await db.execute(statement.order_by(User.id).limit(CANDIDATE_POOL))).all()

    candidate_views = await fetch_profile_views(db, candidates)
    scored = []
    for profile, user, course in candidates:
        view = candidate_views[user.id]
        result = score_match(viewer_view, view)
        scored.append((profile, user, course, view, result))
    scored.sort(key=lambda item: (-item[4].score, str(item[1].id)))

    if cursor:
        last_score, last_id = decode_match_cursor(cursor)
        scored = [
            item
            for item in scored
            if item[4].score < last_score or (item[4].score == last_score and str(item[1].id) > str(last_id))
        ]

    has_more = len(scored) > limit
    selected = scored[:limit]
    items = []
    next_cursor = None
    for profile, user, course, view, result in selected:
        state_row = await db.scalar(
            select(ConnectionRequest).where(
                or_(
                    and_(ConnectionRequest.sender_id == viewer.id, ConnectionRequest.receiver_id == user.id),
                    and_(ConnectionRequest.receiver_id == viewer.id, ConnectionRequest.sender_id == user.id),
                )
            )
        )
        state = "none"
        if state_row is not None:
            state = (
                "connected" if state_row.status == "accepted"
                else "pending_outgoing" if state_row.sender_id == viewer.id
                else "pending_incoming" if state_row.status == "pending"
                else "none"
            )
        items.append(
            {
                "user": {
                    "id": str(user.id),
                    "display_name": user.display_name,
                    "first_name": user.first_name,
                    "role": profile.role,
                    "course": {"id": str(course.id), "name": course.name} if course else None,
                    "bio": profile.bio,
                    "looking_for": profile.looking_for,
                    "has_photo": profile.photo_id is not None,
                    "photo_url": f"/api/v1/users/{user.id}/photo" if profile.photo_id else None,
                    "skills": [{"id": str(key), "name": value} for key, value in sorted(view.skill_names.items(), key=lambda p: p[1].lower())],
                    "interests": [{"id": str(key), "name": value} for key, value in sorted(view.interest_names.items(), key=lambda p: p[1].lower())],
                },
                "score": result.score,
                "reasons": result.reasons,
                "shared_skills": [
                    {"id": str(skill_id), "name": view.skill_names[skill_id]} for skill_id in result.shared_skill_ids
                ],
                "connection_state": state,
            }
        )
    if has_more and selected:
        next_cursor = encode_match_cursor(selected[-1][4].score, selected[-1][1].id)
    return {"items": items, "next_cursor": next_cursor}
