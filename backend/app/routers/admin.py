from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.auth import User
from app.models.domain import (
    AdminAuditLog,
    ConnectionRequest,
    Course,
    Interest,
    Profile,
    ProjectIdea,
    Skill,
    profile_interests,
    profile_skills,
)
from app.schemas.admin import ReferenceCreate, ReferenceUpdate
from app.services.profiles import normalise_name
from app.services.pagination import (
    decode_datetime_cursor,
    decode_name_cursor,
    encode_datetime_cursor,
    encode_name_cursor,
)
from app.web import ApiError, get_current_admin, require_csrf

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


def audit(
    db: AsyncSession,
    admin: User,
    action: str,
    target_type: str | None = None,
    target_id: UUID | None = None,
    metadata: dict | None = None,
) -> None:
    db.add(
        AdminAuditLog(
            admin_id=admin.id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            metadata_json=metadata or {},
        )
    )


def user_data(user: User, profile: Profile | None) -> dict:
    return {
        "id": str(user.id),
        "email": user.email,
        "display_name": user.display_name,
        "first_name": user.first_name,
        "is_admin": user.is_admin,
        "is_active": user.is_active,
        "created_at": user.created_at,
        "role": profile.role if profile else None,
        "course_id": str(profile.course_id) if profile and profile.course_id else None,
        "profile_complete": profile.profile_complete if profile else False,
    }


@router.get("/overview")
async def get_overview(
    _: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)
) -> dict[str, int]:
    total = await db.scalar(select(func.count()).select_from(User))
    active = await db.scalar(select(func.count()).select_from(User).where(User.is_active.is_(True)))
    new_week = await db.scalar(
        select(func.count()).select_from(User).where(User.created_at >= func.now() - text("interval '7 days'"))
    )
    connections = await db.scalar(
        select(func.count()).select_from(ConnectionRequest).where(ConnectionRequest.status == "accepted")
    )
    ideas = await db.scalar(select(func.count()).select_from(ProjectIdea))
    return {
        "total_users": int(total or 0),
        "active_users": int(active or 0),
        "new_this_week": int(new_week or 0),
        "connections_made": int(connections or 0),
        "project_ideas": int(ideas or 0),
    }


@router.get("/users")
async def list_users(
    search: str | None = Query(default=None, max_length=100),
    role: str | None = Query(default=None, pattern="^(software_developer|business_developer)$"),
    is_active: bool | None = None,
    is_admin: bool | None = None,
    course_id: UUID | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    query = select(User, Profile).outerjoin(Profile, Profile.user_id == User.id)
    if search and search.strip():
        pattern = f"%{search.strip()}%"
        query = query.where(
            or_(
                User.email.ilike(pattern),
                User.display_name.ilike(pattern),
                exists_skill_search(pattern),
            )
        )
    if role:
        query = query.where(Profile.role == role)
    if is_active is not None:
        query = query.where(User.is_active.is_(is_active))
    if is_admin is not None:
        query = query.where(User.is_admin.is_(is_admin))
    if course_id:
        query = query.where(Profile.course_id == course_id)
    if cursor:
        created_at, row_id = decode_datetime_cursor(cursor)
        query = query.where(
            or_(User.created_at < created_at, and_(User.created_at == created_at, User.id < row_id))
        )
    rows = list(
        (
            await db.execute(
                query.order_by(User.created_at.desc(), User.id.desc()).limit(limit + 1)
            )
        ).all()
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    audit(db, admin, "view_user", "user", metadata={"count": len(rows), "view": "list"})
    await db.commit()
    return {
        "items": [user_data(user, profile) for user, profile in rows],
        "next_cursor": encode_datetime_cursor(rows[-1][0].created_at, rows[-1][0].id) if has_more and rows else None,
    }


def exists_skill_search(pattern):
    return select(profile_skills.c.profile_id).join(Skill, Skill.id == profile_skills.c.skill_id).join(
        Profile, Profile.id == profile_skills.c.profile_id
    ).where(Profile.user_id == User.id, Skill.name.ilike(pattern)).exists()


@router.get("/users/{user_id}")
async def get_user(
    user_id: UUID,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(
        select(User, Profile).outerjoin(Profile, Profile.user_id == User.id).where(User.id == user_id)
    )
    row = result.first()
    if row is None:
        raise ApiError(404, "not_found", "User not found.")
    user, profile = row
    audit(db, admin, "view_user", "user", user.id)
    await db.commit()
    return user_data(user, profile)


async def mutate_user(db: AsyncSession, admin: User, user_id: UUID, action: str) -> dict:
    target = await db.scalar(select(User).where(User.id == user_id).with_for_update())
    if target is None:
        raise ApiError(404, "not_found", "User not found.")
    if action == "deactivate_user" and target.id == admin.id:
        raise ApiError(422, "validation_error", "You cannot deactivate your own account.")
    if action in {"deactivate_user", "revoke_admin"} and target.is_admin and target.is_active:
        active_admins = await db.scalar(
            select(func.count()).select_from(User).where(User.is_admin.is_(True), User.is_active.is_(True))
        )
        if int(active_admins or 0) <= 1:
            raise ApiError(409, "last_admin", "The last active admin cannot be removed.")
    if action == "deactivate_user":
        target.is_active = False
    elif action == "reactivate_user":
        target.is_active = True
    elif action == "grant_admin":
        target.is_admin = True
    elif action == "revoke_admin":
        target.is_admin = False
    audit(db, admin, action, "user", target.id)
    await db.commit()
    profile = await db.scalar(select(Profile).where(Profile.user_id == target.id))
    return user_data(target, profile)


@router.post("/users/{user_id}/deactivate", dependencies=[Depends(require_csrf)])
async def deactivate_user(user_id: UUID, admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)) -> dict:
    return await mutate_user(db, admin, user_id, "deactivate_user")


@router.post("/users/{user_id}/reactivate", dependencies=[Depends(require_csrf)])
async def reactivate_user(user_id: UUID, admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)) -> dict:
    return await mutate_user(db, admin, user_id, "reactivate_user")


@router.post("/users/{user_id}/grant-admin", dependencies=[Depends(require_csrf)])
async def grant_admin(user_id: UUID, admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)) -> dict:
    return await mutate_user(db, admin, user_id, "grant_admin")


@router.delete("/users/{user_id}/admin", dependencies=[Depends(require_csrf)])
async def revoke_admin(user_id: UUID, admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)) -> dict:
    return await mutate_user(db, admin, user_id, "revoke_admin")


async def list_references(db: AsyncSession, model, limit: int, cursor: str | None) -> dict:
    query = select(model)
    if cursor:
        name, row_id = decode_name_cursor(cursor)
        query = query.where(or_(model.name > name, and_(model.name == name, model.id > row_id)))
    rows = list((await db.scalars(query.order_by(model.name, model.id).limit(limit + 1))).all())
    has_more = len(rows) > limit
    rows = rows[:limit]
    return {
        "items": [
            {"id": str(row.id), "name": row.name, **({"category": row.category} if isinstance(row, Skill) else {})}
            for row in rows
        ],
        "next_cursor": encode_name_cursor(rows[-1].name, rows[-1].id) if has_more and rows else None,
    }


@router.get("/courses")
async def admin_courses(
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await list_references(db, Course, limit, cursor)


@router.post("/courses", status_code=201, dependencies=[Depends(require_csrf)])
async def create_course(
    payload: ReferenceCreate, admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)
) -> dict:
    return await create_reference(db, admin, Course, payload.name, None, "create_course")


@router.patch("/courses/{item_id}", dependencies=[Depends(require_csrf)])
async def rename_course(
    item_id: UUID, payload: ReferenceUpdate, admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)
) -> dict:
    return await update_reference(db, admin, Course, item_id, payload, "update_course")


@router.get("/skills")
async def admin_skills(
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await list_references(db, Skill, limit, cursor)


@router.post("/skills", status_code=201, dependencies=[Depends(require_csrf)])
async def create_skill(
    payload: ReferenceCreate, admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)
) -> dict:
    return await create_reference(db, admin, Skill, payload.name, payload.category, "create_skill")


@router.patch("/skills/{item_id}", dependencies=[Depends(require_csrf)])
async def rename_skill(
    item_id: UUID, payload: ReferenceUpdate, admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)
) -> dict:
    return await update_reference(db, admin, Skill, item_id, payload, "update_skill")


@router.delete("/skills/{item_id}", status_code=204, dependencies=[Depends(require_csrf)])
async def delete_skill(
    item_id: UUID, admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)
) -> Response:
    return await delete_reference(db, admin, Skill, item_id, profile_skills.c.skill_id, "skill")


@router.get("/interests")
async def admin_interests(
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await list_references(db, Interest, limit, cursor)


@router.post("/interests", status_code=201, dependencies=[Depends(require_csrf)])
async def create_interest(
    payload: ReferenceCreate, admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)
) -> dict:
    return await create_reference(db, admin, Interest, payload.name, None, "create_interest")


@router.patch("/interests/{item_id}", dependencies=[Depends(require_csrf)])
async def rename_interest(
    item_id: UUID, payload: ReferenceUpdate, admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)
) -> dict:
    return await update_reference(db, admin, Interest, item_id, payload, "update_interest")


@router.delete("/interests/{item_id}", status_code=204, dependencies=[Depends(require_csrf)])
async def delete_interest(
    item_id: UUID, admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)
) -> Response:
    return await delete_reference(db, admin, Interest, item_id, profile_interests.c.interest_id, "interest")


async def create_reference(db: AsyncSession, admin: User, model, name: str, category: str | None, action: str) -> dict:
    if category is not None and model is not Skill:
        raise ApiError(422, "validation_error", "Only skills have categories.", {"category": "Remove this field."})
    max_length = 100 if model is Course else 50
    name = normalise_name(name, max_length)
    row = model(name=name, **({"category": category.strip() or None} if model is Skill and category else {}))
    db.add(row)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise ApiError(409, "already_exists", "A reference with this name already exists.") from exc
    audit(db, admin, action, model.__tablename__.removesuffix("s"), row.id, {"name": name})
    await db.commit()
    return {"id": str(row.id), "name": row.name, **({"category": row.category} if isinstance(row, Skill) else {})}


async def update_reference(db: AsyncSession, admin: User, model, item_id: UUID, payload: ReferenceUpdate, action: str) -> dict:
    row = await db.get(model, item_id)
    if row is None:
        raise ApiError(404, "not_found", "Reference not found.")
    old = {"name": row.name}
    values = payload.model_dump(exclude_unset=True)
    if "category" in values and model is not Skill:
        raise ApiError(422, "validation_error", "Only skills have categories.", {"category": "Remove this field."})
    if "name" in values:
        row.name = normalise_name(values["name"], 100 if model is Course else 50)
    if isinstance(row, Skill) and "category" in values:
        row.category = values["category"].strip() or None if values["category"] else None
    audit(db, admin, action, model.__tablename__.removesuffix("s"), row.id, {"old": old, "new": values})
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ApiError(409, "already_exists", "A reference with this name already exists.") from exc
    return {"id": str(row.id), "name": row.name, **({"category": row.category} if isinstance(row, Skill) else {})}


async def delete_reference(db: AsyncSession, admin: User, model, item_id: UUID, reference_column, label: str) -> Response:
    row = await db.get(model, item_id)
    if row is None:
        raise ApiError(404, "not_found", "Reference not found.")
    count = int(await db.scalar(select(func.count()).select_from(reference_column.table).where(reference_column == item_id)) or 0)
    if count:
        raise ApiError(409, f"{label}_in_use", f"This {label} is used by {count} profiles. Rename it instead.")
    audit(db, admin, f"delete_{label}", label, row.id, {"name": row.name})
    await db.delete(row)
    await db.commit()
    return Response(status_code=204)


@router.get("/audit")
async def list_audit(
    action: str | None = None,
    admin_id: UUID | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = None,
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    query = select(AdminAuditLog, User).join(User, User.id == AdminAuditLog.admin_id)
    if action:
        query = query.where(AdminAuditLog.action == action)
    if admin_id:
        query = query.where(AdminAuditLog.admin_id == admin_id)
    if cursor:
        created_at, row_id = decode_datetime_cursor(cursor)
        query = query.where(
            or_(AdminAuditLog.created_at < created_at, and_(AdminAuditLog.created_at == created_at, AdminAuditLog.id < row_id))
        )
    rows = list(
        (
            await db.execute(
                query.order_by(AdminAuditLog.created_at.desc(), AdminAuditLog.id.desc()).limit(limit + 1)
            )
        ).all()
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    return {
        "items": [
            {
                "id": str(log.id),
                "admin": {"id": str(user.id), "display_name": user.display_name},
                "action": log.action,
                "target_type": log.target_type,
                "target_id": str(log.target_id) if log.target_id else None,
                "metadata": log.metadata_json,
                "created_at": log.created_at,
            }
            for log, user in rows
        ],
        "next_cursor": encode_datetime_cursor(rows[-1][0].created_at, rows[-1][0].id) if has_more and rows else None,
    }
