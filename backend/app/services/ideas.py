"""Project ideas. specs/08_project_ideas.md."""

from __future__ import annotations

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.pagination import decode_cursor
from app.errors import (
    Conflict,
    IdeaClosed,
    NotFound,
    NotIdeaOwner,
    ValidationFailed,
)
from app.models import ProjectIdea, User, idea_interests
from app.models.enums import IdeaCategory

MAX_TITLE = 120
MIN_DESCRIPTION = 50
MAX_DESCRIPTION = 2000
MAX_SKILLS_NEEDED = 8


async def get_idea(db: AsyncSession, idea_id: uuid.UUID) -> ProjectIdea:
    idea = await db.get(ProjectIdea, idea_id)
    if idea is None:
        raise NotFound("That idea does not exist.")
    return idea


async def list_ideas(
    db: AsyncSession,
    *,
    categories: list[str] | None = None,
    search: str | None = None,
    author_id: uuid.UUID | None = None,
    mine: bool = False,
    viewer_id: uuid.UUID | None = None,
    open_only: bool = True,
    limit: int = 20,
    cursor: str | None = None,
) -> list[tuple[ProjectIdea, int, bool]]:
    """Returns (idea, interest_count, viewer_has_interested)."""
    stmt = select(ProjectIdea)
    if open_only:
        stmt = stmt.where(ProjectIdea.is_open.is_(True))
    if categories:
        stmt = stmt.where(ProjectIdea.category.in_(categories))
    if search:
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(ProjectIdea.title.ilike(pattern), ProjectIdea.description.ilike(pattern))
        )
    if mine and viewer_id:
        stmt = stmt.where(ProjectIdea.author_id == viewer_id)
    elif author_id:
        stmt = stmt.where(ProjectIdea.author_id == author_id)
    if cursor:
        # Keyset, not offset: rows shift when someone posts or closes an idea
        # mid-scroll, and an offset then skips or repeats them.
        since, since_id = decode_cursor(cursor)
        stmt = stmt.where(
            (ProjectIdea.created_at < since)
            | (
                (ProjectIdea.created_at == since)
                & (ProjectIdea.id < since_id)
            )
        )
    # +1 to detect whether another page exists without a second COUNT query.
    stmt = stmt.order_by(ProjectIdea.created_at.desc(), ProjectIdea.id.desc()).limit(limit + 1)
    ideas = list(await db.scalars(stmt))

    if not ideas:
        return []
    ids = [i.id for i in ideas]

    counts = dict(
        (
            await db.execute(
                select(idea_interests.c.idea_id, func.count())
                .where(idea_interests.c.idea_id.in_(ids))
                .group_by(idea_interests.c.idea_id)
            )
        ).all()
    )

    mine_rows: set[uuid.UUID] = set()
    if viewer_id:
        mine_rows = set(
            await db.scalars(
                select(idea_interests.c.idea_id).where(
                    idea_interests.c.idea_id.in_(ids),
                    idea_interests.c.user_id == viewer_id,
                )
            )
        )

    return [(i, counts.get(i.id, 0), i.id in mine_rows) for i in ideas]


async def create_idea(
    db: AsyncSession,
    author: User,
    *,
    title: str,
    description: str,
    category: str,
    skills_needed: list[str] | None = None,
    course_id: uuid.UUID | None = None,
) -> ProjectIdea:
    clean_title = _validate_title(title)
    clean_desc = _validate_description(description)
    if category not in {c.value for c in IdeaCategory}:
        raise ValidationFailed({"category": "Unknown category."})
    skills = _clean_skills(skills_needed or [])

    idea = ProjectIdea(
        author_id=author.id,
        title=clean_title,
        description=clean_desc,
        category=category,
        skills_needed=skills,
        course_id=course_id,
    )
    db.add(idea)
    await db.commit()
    await db.refresh(idea)
    return idea


async def update_idea(
    db: AsyncSession, idea: ProjectIdea, author: User, **fields
) -> ProjectIdea:
    """Author only. Admins are NOT an exception — idea content is the author's
    voice (specs/08 §4)."""
    if idea.author_id != author.id:
        raise NotIdeaOwner()

    if "title" in fields:
        idea.title = _validate_title(fields["title"])
    if "description" in fields:
        idea.description = _validate_description(fields["description"])
    if "category" in fields:
        if fields["category"] not in {c.value for c in IdeaCategory}:
            raise ValidationFailed({"category": "Unknown category."})
        idea.category = fields["category"]
    if "skills_needed" in fields:
        idea.skills_needed = _clean_skills(fields["skills_needed"] or [])
    if "course_id" in fields:
        idea.course_id = fields["course_id"]
    if "is_open" in fields:
        idea.is_open = bool(fields["is_open"])

    await db.commit()
    await db.refresh(idea)
    return idea


async def delete_idea(db: AsyncSession, idea: ProjectIdea, author: User) -> None:
    if idea.author_id != author.id:
        raise NotIdeaOwner()
    await db.delete(idea)
    await db.commit()


async def express_interest(
    db: AsyncSession, idea: ProjectIdea, user: User, *, notify_author: bool = True
) -> tuple[ProjectIdea, bool]:
    """Idempotent: a double-click must not show an error. The composite PK makes
    duplicates impossible, so the endpoint reports success either way."""
    if idea.author_id == user.id:
        raise ValidationFailed({"idea": "You cannot express interest in your own idea."})
    if not idea.is_open:
        raise IdeaClosed()

    from sqlalchemy.dialects.postgresql import insert as pg_insert

    try:
        result = await db.execute(
            pg_insert(idea_interests)
            .values(idea_id=idea.id, user_id=user.id)
            .on_conflict_do_nothing()
            .returning(idea_interests.c.idea_id)
        )
        created = result.scalar_one_or_none() is not None
    except IntegrityError:
        await db.rollback()
        created = False

    if created and notify_author:
        from app.models.enums import NotificationType
        from app.services.notifications import notify

        await notify(
            db,
            user_id=idea.author_id,
            notification_type=NotificationType.IDEA_INTEREST,
            actor=user,
            project_idea_id=idea.id,
            url=f"/ideas/{idea.id}",
            extra={"title": idea.title},
        )
    else:
        await db.commit()

    return idea, created


async def withdraw_interest(
    db: AsyncSession, idea: ProjectIdea, user: User
) -> None:
    """Always allowed, even on a closed idea — changing your mind should never
    be blocked by someone else's state change."""
    await db.execute(
        idea_interests.delete().where(
            idea_interests.c.idea_id == idea.id, idea_interests.c.user_id == user.id
        )
    )
    await db.commit()


def interest_count(db: AsyncSession, idea_id: uuid.UUID):  # pragma: no cover - helper
    return db.scalar(
        select(func.count())
        .select_from(idea_interests)
        .where(idea_interests.c.idea_id == idea_id)
    )


def _validate_title(title: str) -> str:
    clean = (title or "").strip()
    if not clean:
        raise ValidationFailed({"title": "Give your idea a title."})
    if len(clean) > MAX_TITLE:
        raise ValidationFailed({"title": f"Must be {MAX_TITLE} characters or fewer."})
    return clean


def _validate_description(description: str) -> str:
    clean = (description or "").strip()
    if len(clean) < MIN_DESCRIPTION:
        raise ValidationFailed(
            {"description": f"Describe the idea in at least {MIN_DESCRIPTION} characters."}
        )
    if len(clean) > MAX_DESCRIPTION:
        raise ValidationFailed(
            {"description": f"Must be {MAX_DESCRIPTION} characters or fewer."}
        )
    return clean


def _clean_skills(skills: list[str]) -> list[str]:
    out: list[str] = []
    for raw in skills:
        name = str(raw).strip()
        if name and name not in out:
            out.append(name)
    if len(out) > MAX_SKILLS_NEEDED:
        raise ValidationFailed({"skills_needed": f"At most {MAX_SKILLS_NEEDED}."})
    return out


__all__ = [
    "get_idea",
    "list_ideas",
    "create_idea",
    "update_idea",
    "delete_idea",
    "express_interest",
    "withdraw_interest",
    "MAX_TITLE",
    "MIN_DESCRIPTION",
    "MAX_DESCRIPTION",
]