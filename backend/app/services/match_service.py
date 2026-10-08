"""Matching service. Specs/04 §5-§7.

Candidates are fetched with one pass of exclusions + filters, bounded by
CANDIDATE_POOL, then scored in Python and sorted. Fetch-then-filter-in-Python
would read the whole table.
"""

from __future__ import annotations

import base64
import binascii
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.errors import BadRequest, ProfileIncomplete
from app.services.pagination import decode_cursor
from app.models import (
    ConnectionRequest,
    Interest,
    Profile,
    Skill,
    User,
    profile_interests,
    profile_skills,
)
from app.services import connections as conn_svc
from app.services.matching import (
    CANDIDATE_POOL,
    MatchResult,
    ProfileView,
    matches_filters,
    score_match,
    sort_key,
)
from app.services.profiles import has_photo


@dataclass
class MatchItem:
    user: User
    view: ProfileView
    score: int
    reasons: list[str]
    shared_skill_names: list[str]
    shared_interest_names: list[str]
    connection_state: str


def to_view(
    user: User,
    profile: Profile,
    *,
    skills: list[Skill] | None = None,
    interests: list[Interest] | None = None,
) -> ProfileView:
    skill_list = skills if skills is not None else list(profile.skills)
    interest_list = interests if interests is not None else list(profile.interests)
    return ProfileView(
        user_id=user.id,
        display_name=user.display_name,
        first_name=user.first_name,
        role=profile.role,
        course_id=profile.course_id,
        course_name=profile.course.name if profile.course else None,
        bio=profile.bio,
        looking_for=profile.looking_for,
        has_photo=profile.photo_id is not None,
        skills=tuple((s.id, s.name) for s in skill_list),
        interests=tuple((i.id, i.name) for i in interest_list),
    )


async def resolve_names(db: AsyncSession, kind: str, names: list[str]) -> set[uuid.UUID]:
    """Public filters use names because they are typed; queries use ids. An
    unknown name is 422, not an empty list — a typo returning nothing is the
    worst possible failure."""
    from app.errors import ValidationFailed

    model = Skill if kind == "skill" else Interest
    wanted = [n.strip() for n in names if n.strip()]
    if not wanted:
        return set()
    found = await db.execute(select(model.id, model.name).where(model.name.in_(wanted)))
    by_name = {name: ident for ident, name in found.all()}
    missing = [n for n in wanted if n not in by_name]
    if missing:
        raise ValidationFailed({kind: f"Unknown: {', '.join(missing)}"})
    return set(by_name.values())


async def fetch_candidates(
    db: AsyncSession,
    viewer_id: uuid.UUID,
    *,
    skill_ids: set[uuid.UUID] | None = None,
    interest_ids: set[uuid.UUID] | None = None,
    role: str | None = None,
    course_id: uuid.UUID | None = None,
    exclude_connected: bool = True,
) -> list[tuple[User, Profile]]:
    """One pass. The exclusions are a NOT EXISTS against connections covering
    all three states in BOTH directions (specs/04 §5)."""
    stmt = (
        select(User, Profile)
        .join(Profile, Profile.user_id == User.id)
        .options(selectinload(Profile.skills), selectinload(Profile.interests), selectinload(Profile.course))
        .where(
            User.id != viewer_id,
            User.is_active.is_(True),
        )
    )

    if exclude_connected:
        # Pairs are stored normalised in pair_lo/pair_hi, so one comparison
        # covers both directions: pending, accepted AND declined.
        stmt = stmt.where(
            ~exists().where(
                and_(
                    or_(
                        (ConnectionRequest.pair_lo == viewer_id)
                        & (ConnectionRequest.pair_hi == User.id),
                        (ConnectionRequest.pair_hi == viewer_id)
                        & (ConnectionRequest.pair_lo == User.id),
                    )
                )
            )
        )

    if role:
        stmt = stmt.where(Profile.role == role)
    if course_id:
        stmt = stmt.where(Profile.course_id == course_id)
    if skill_ids:
        stmt = stmt.where(
            Profile.id.in_(select(profile_skills.c.profile_id).where(
                profile_skills.c.skill_id.in_(skill_ids)
            ))
        )
    if interest_ids:
        stmt = stmt.where(
            Profile.id.in_(select(profile_interests.c.profile_id).where(
                profile_interests.c.interest_id.in_(interest_ids)
            ))
        )

    stmt = stmt.order_by(Profile.id).limit(CANDIDATE_POOL)
    return [(u, p) for u, p in (await db.execute(stmt)).all()]


async def rank_for_viewer(
    db: AsyncSession,
    viewer: User,
    *,
    skill_ids: set[uuid.UUID] | None = None,
    interest_ids: set[uuid.UUID] | None = None,
    role: str | None = None,
    course_id: uuid.UUID | None = None,
    exclude_connected: bool = True,
    limit: int = 20,
    cursor: str | None = None,
) -> list[MatchItem]:
    """Gated behind profile_complete. Never returns partial results for an
    incomplete profile — a 403 with an actionable message, not an empty list."""
    profile = viewer.profile
    if profile is None or not profile.profile_complete:
        raise ProfileIncomplete()

    viewer_view = to_view(viewer, profile)

    candidates = await fetch_candidates(
        db,
        viewer.id,
        skill_ids=skill_ids,
        interest_ids=interest_ids,
        role=role,
        course_id=course_id,
        exclude_connected=exclude_connected,
    )

    rows: list[tuple[MatchResult, User, ProfileView]] = []
    for user, cand_profile in candidates:
        view = to_view(user, cand_profile)
        if not matches_filters(
            view,
            skill_ids=skill_ids,
            interest_ids=interest_ids,
            role=role,
            course_id=course_id,
        ):
            continue
        result = score_match(viewer_view, view)
        rows.append((result, user, view))

    rows.sort(key=lambda row: sort_key(row[0], row[2].user_id))

    if cursor:
        # Keyset over (score, user_id). Offsets would skip or repeat rows when
        # the cohort changes between requests.
        after_score, after_id = decode_cursor(cursor)
        rows = [
            row
            for row in rows
            if sort_key(row[0], row[2].user_id) > (after_score, after_id)
        ]

    # States computed after ordering, in as few queries as we can.
    states: dict[uuid.UUID, str] = {}
    for _, user, _view in rows[:limit]:
        states[user.id] = await conn_svc.connection_state(db, viewer.id, user.id)

    return [
        MatchItem(
            user=user,
            view=view,
            score=result.score,
            reasons=result.reasons,
            shared_skill_names=result.shared_skill_names,
            shared_interest_names=result.shared_interest_names,
            connection_state=states.get(user.id, "none"),
        )
        for result, user, view in rows[:limit]
    ]


# ─── Cursor pagination ───────────────────────────────────────────────────────


def encode_cursor(score: int, user_id: uuid.UUID) -> str:
    payload = json.dumps({"s": score, "u": str(user_id)}).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[int, uuid.UUID]:
    try:
        padding = "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(cursor + padding))
        return int(payload["s"]), uuid.UUID(payload["u"])
    except (ValueError, TypeError, KeyError, OverflowError, binascii.Error) as exc:
        raise BadRequest("That pagination cursor is invalid.", code="invalid_cursor") from exc


__all__ = [
    "MatchItem",
    "to_view",
    "resolve_names",
    "fetch_candidates",
    "rank_for_viewer",
    "encode_cursor",
    "decode_cursor",
]
