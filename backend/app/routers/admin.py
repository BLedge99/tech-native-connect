"""Admin routes. Spec 09.

Admin manages the substrate, not other people's content: no profile editing, no
idea editing. Every route needs get_current_admin — one auth test per route.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_db
from app.dependencies import get_current_admin, require_csrf
from app.errors import Conflict, LastAdmin, NotFound, ValidationFailed
from app.models import (
    AdminAuditLog,
    ConnectionRequest,
    Course,
    Interest,
    Profile,
    ProjectIdea,
    Skill,
    User,
    profile_interests,
    profile_skills,
)
from app.models.enums import ConnectionStatus
from app.schemas import (
    AdminOverview,
    AdminUserOut,
    AuditOut,
    CourseOut,
    NamedRefIn,
    Page,
    RefOut,
)
from app.serializers import admin_user_out, audit_out
from app.services.profiles import recompute_profile_complete

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


async def audit(
    db: AsyncSession, admin: User, action: str, target_type: str | None = None,
    target_id: uuid.UUID | None = None, metadata: dict | None = None,
) -> None:
    """Written in the same transaction as the action — if the action rolls
    back, so does the audit row."""
    db.add(
        AdminAuditLog(
            admin_id=admin.id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            metadata_=metadata or {},
        )
    )


@router.get("/overview", response_model=AdminOverview)
async def overview(
    _admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)
):
    """Four counts, no charts. A bar chart needs a library and does not make
    the demo better."""
    from app.models import ConnectionRequest as CR

    total = await db.scalar(select(func.count()).select_from(User)) or 0
    active = await db.scalar(
        select(func.count()).select_from(User).where(User.is_active.is_(True))
    ) or 0
    week_ago = datetime.now(UTC) - timedelta(days=7)
    new_week = await db.scalar(
        select(func.count()).select_from(User).where(User.created_at > week_ago)
    ) or 0
    connections = await db.scalar(
        select(func.count())
        .select_from(CR)
        .where(CR.status == ConnectionStatus.ACCEPTED)
    ) or 0
    ideas = await db.scalar(select(func.count()).select_from(ProjectIdea)) or 0
    return AdminOverview(
        total_users=total,
        active_users=active,
        new_this_week=new_week,
        connections_made=connections,
        project_ideas=ideas,
    )


# ─── Users ───────────────────────────────────────────────────────────────────


@router.get("/users", response_model=Page)
async def list_users(
    q: str | None = None,
    is_active: bool | None = None,
    is_admin: bool | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(User)
        .options(
            selectinload(User.profile).selectinload(Profile.skills),
            selectinload(User.profile).selectinload(Profile.course),
        )
        .order_by(User.created_at.desc())
    )
    if q:
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(User.email.ilike(pattern) | User.display_name.ilike(pattern))
    if is_active is not None:
        stmt = stmt.where(User.is_active.is_(is_active))
    if is_admin is not None:
        stmt = stmt.where(User.is_admin.is_(is_admin))
    rows = list(await db.scalars(stmt.limit(limit)))
    return Page(items=[admin_user_out(u) for u in rows], next_cursor=None)


@router.get("/users/{user_id}", response_model=AdminUserOut)
async def get_admin_user(
    user_id: uuid.UUID,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """The only legitimate place another user's email is visible. Audited."""
    result = await db.execute(
        select(User)
        .options(
            selectinload(User.profile).selectinload(Profile.skills),
            selectinload(User.profile).selectinload(Profile.course),
        )
        .where(User.id == user_id)
    )
    target = result.scalar_one_or_none()
    if target is None:
        raise NotFound("That user does not exist.")
    await audit(db, admin, "view_user", "user", target.id)
    await db.commit()
    return admin_user_out(target)


@router.post("/users/{user_id}/deactivate", dependencies=[Depends(require_csrf)])
async def deactivate_user(
    user_id: uuid.UUID,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    if user_id == admin.id:
        raise ValidationFailed({"user": "You cannot deactivate your own account."})
    target = await db.get(User, user_id)
    if target is None:
        raise NotFound("That user does not exist.")
    target.is_active = False
    # Revoke sessions so the deactivation takes effect immediately.
    from app.services.auth import revoke_all_sessions

    await revoke_all_sessions(db, target.id)
    await audit(db, admin, "deactivate_user", "user", target.id)
    await db.commit()
    return {"ok": True}


@router.post("/users/{user_id}/reactivate", dependencies=[Depends(require_csrf)])
async def reactivate_user(
    user_id: uuid.UUID,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    target = await db.get(User, user_id)
    if target is None:
        raise NotFound("That user does not exist.")
    target.is_active = True
    await audit(db, admin, "reactivate_user", "user", target.id)
    await db.commit()
    return {"ok": True}


@router.post("/users/{user_id}/grant-admin", dependencies=[Depends(require_csrf)])
async def grant_admin(
    user_id: uuid.UUID,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    target = await db.get(User, user_id)
    if target is None:
        raise NotFound("That user does not exist.")
    target.is_admin = True
    await audit(db, admin, "grant_admin", "user", target.id)
    await db.commit()
    return {"ok": True}


@router.delete("/users/{user_id}/admin", dependencies=[Depends(require_csrf)])
async def revoke_admin(
    user_id: uuid.UUID,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    target = await db.get(User, user_id)
    if target is None:
        raise NotFound("That user does not exist.")
    if target.is_admin:
        remaining = await db.scalar(
            select(func.count())
            .select_from(User)
            .where(User.is_admin.is_(True), User.is_active.is_(True), User.id != target.id)
        )
        if (remaining or 0) == 0:
            raise LastAdmin()
    target.is_admin = False
    await audit(db, admin, "revoke_admin", "user", target.id)
    await db.commit()
    return {"ok": True}


# ─── Reference data ──────────────────────────────────────────────────────────


@router.get("/courses", response_model=list[CourseOut])
async def list_courses(_admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    return [CourseOut(id=c.id, name=c.name) for c in await db.scalars(select(Course).order_by(Course.name))]


@router.post("/courses", response_model=CourseOut, dependencies=[Depends(require_csrf)])
async def create_course(
    payload: NamedRefIn,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    name = payload.name.strip()
    if await db.scalar(select(Course.id).where(Course.name == name)):
        raise Conflict("That course already exists.")
    course = Course(name=name)
    db.add(course)
    await db.flush()
    await audit(db, admin, "create_course", "course", course.id, {"name": name})
    await db.commit()
    return CourseOut(id=course.id, name=course.name)


@router.patch("/courses/{course_id}", response_model=CourseOut, dependencies=[Depends(require_csrf)])
async def update_course(
    course_id: uuid.UUID,
    payload: NamedRefIn,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    course = await db.get(Course, course_id)
    if course is None:
        raise NotFound("That course does not exist.")
    old = course.name
    course.name = payload.name.strip()
    await audit(db, admin, "update_course", "course", course.id, {"from": old, "to": course.name})
    await db.commit()
    return CourseOut(id=course.id, name=course.name)


@router.get("/skills", response_model=list[RefOut])
async def list_skills(_admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    return [RefOut(id=s.id, name=s.name) for s in await db.scalars(select(Skill).order_by(Skill.name))]


@router.post("/skills", response_model=RefOut, dependencies=[Depends(require_csrf)])
async def create_skill(
    payload: NamedRefIn,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    name = payload.name.strip()
    if await db.scalar(select(Skill.id).where(Skill.name == name)):
        raise Conflict("That skill already exists.")
    skill = Skill(name=name, category=payload.category)
    db.add(skill)
    await db.flush()
    await audit(db, admin, "create_skill", "skill", skill.id, {"name": name})
    await db.commit()
    return RefOut(id=skill.id, name=skill.name)


@router.patch("/skills/{skill_id}", response_model=RefOut, dependencies=[Depends(require_csrf)])
async def update_skill(
    skill_id: uuid.UUID,
    payload: NamedRefIn,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Renaming is always safe — it is the operation people actually need."""
    skill = await db.get(Skill, skill_id)
    if skill is None:
        raise NotFound("That skill does not exist.")
    old = skill.name
    skill.name = payload.name.strip()
    if payload.category is not None:
        skill.category = payload.category
    await audit(db, admin, "update_skill", "skill", skill.id, {"from": old, "to": skill.name})
    await db.commit()
    return RefOut(id=skill.id, name=skill.name)


@router.delete("/skills/{skill_id}", status_code=204, dependencies=[Depends(require_csrf)])
async def delete_skill(
    skill_id: uuid.UUID,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    skill = await db.get(Skill, skill_id)
    if skill is None:
        raise NotFound("That skill does not exist.")
    # A cascade here would silently strip skills from profiles and change
    # everyone's match scores with no explanation.
    in_use = await db.scalar(
        select(func.count()).select_from(profile_skills).where(profile_skills.c.skill_id == skill_id)
    )
    if in_use:
        raise Conflict(f"This skill is on {in_use} profiles. Rename it instead.", code="skill_in_use")
    await db.delete(skill)
    await audit(db, admin, "delete_skill", "skill", skill_id, {"name": skill.name})
    await db.commit()
    return None


@router.get("/interests", response_model=list[RefOut])
async def list_interests(_admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    return [RefOut(id=i.id, name=i.name) for i in await db.scalars(select(Interest).order_by(Interest.name))]


@router.post("/interests", response_model=RefOut, dependencies=[Depends(require_csrf)])
async def create_interest(
    payload: NamedRefIn,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    name = payload.name.strip()
    if await db.scalar(select(Interest.id).where(Interest.name == name)):
        raise Conflict("That interest already exists.")
    interest = Interest(name=name)
    db.add(interest)
    await db.flush()
    await audit(db, admin, "create_interest", "interest", interest.id, {"name": name})
    await db.commit()
    return RefOut(id=interest.id, name=interest.name)


@router.patch("/interests/{interest_id}", response_model=RefOut, dependencies=[Depends(require_csrf)])
async def update_interest(
    interest_id: uuid.UUID,
    payload: NamedRefIn,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    interest = await db.get(Interest, interest_id)
    if interest is None:
        raise NotFound("That interest does not exist.")
    old = interest.name
    interest.name = payload.name.strip()
    await audit(db, admin, "update_interest", "interest", interest.id, {"from": old, "to": interest.name})
    await db.commit()
    return RefOut(id=interest.id, name=interest.name)


@router.delete("/interests/{interest_id}", status_code=204, dependencies=[Depends(require_csrf)])
async def delete_interest(
    interest_id: uuid.UUID,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    interest = await db.get(Interest, interest_id)
    if interest is None:
        raise NotFound("That interest does not exist.")
    in_use = await db.scalar(
        select(func.count())
        .select_from(profile_interests)
        .where(profile_interests.c.interest_id == interest_id)
    )
    if in_use:
        raise Conflict(f"This interest is on {in_use} profiles. Rename it instead.", code="skill_in_use")
    await db.delete(interest)
    await audit(db, admin, "delete_interest", "interest", interest_id, {"name": interest.name})
    await db.commit()
    return None


# ─── Audit ───────────────────────────────────────────────────────────────────

@router.get("/audit", response_model=Page)
async def list_audit(
    action: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    _admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Boring on purpose. Its job is to make "who looked at what" answerable."""
    stmt = select(AdminAuditLog).order_by(AdminAuditLog.created_at.desc())
    if action:
        stmt = stmt.where(AdminAuditLog.action == action)
    rows = list(await db.scalars(stmt.limit(limit)))
    return Page(items=[audit_out(r) for r in rows], next_cursor=None)


__all__ = ["router"]