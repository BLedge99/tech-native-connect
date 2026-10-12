import asyncio

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.config import get_settings
from app.db import SessionLocal
from app.models.auth import User
from app.models.domain import (
    Course,
    Interest,
    Profile,
    Skill,
    profile_interests,
    profile_skills,
)
from app.services.auth import hash_password


async def get_or_create_reference(db, model, name: str, category: str | None = None):
    row = await db.scalar(select(model).where(model.name == name))
    if row is None:
        row = model(name=name, **({"category": category} if model is Skill else {}))
        db.add(row)
        await db.flush()
    return row


async def seed_reference_data(db) -> tuple[Course, dict[str, Skill], dict[str, Interest]]:
    course = await get_or_create_reference(db, Course, "Software Development")
    skills = {
        name: await get_or_create_reference(db, Skill, name, category)
        for name, category in (
            ("Python", "Language"),
            ("React", "Framework"),
            ("PostgreSQL", "Database"),
            ("Figma", "Design"),
            ("Market research", "Business"),
            ("Pitching", "Business"),
        )
    }
    interests = {
        name: await get_or_create_reference(db, Interest, name)
        for name in ("Climate tech", "Education", "Local business")
    }
    return course, skills, interests


async def seed_demo_users(db, password: str, course: Course, skills: dict[str, Skill], interests: dict[str, Interest]) -> None:
    people = (
        ("sam.demo@example.com", "sam.demo@bootcampconnect.local", "Sam Taylor", "software_developer", ("Python", "React", "PostgreSQL"), ("Climate tech", "Education")),
        ("priya.demo@example.com", "priya.demo@bootcampconnect.local", "Priya Sharma", "business_developer", ("Python", "Market research", "Pitching"), ("Climate tech", "Local business")),
    )
    for email, legacy_email, name, role, skill_names, interest_names in people:
        user = await db.scalar(select(User).where(User.email == email))
        if user is None:
            user = await db.scalar(select(User).where(User.email == legacy_email))
            if user is not None:
                user.email = email
        if user is None:
            user = User(
                email=email,
                password_hash=hash_password(password),
                display_name=name,
                first_name=name.split()[0],
            )
            db.add(user)
            await db.flush()
        profile = await db.scalar(select(Profile).where(Profile.user_id == user.id))
        if profile is None:
            profile = Profile(user_id=user.id)
            db.add(profile)
            await db.flush()
        profile.role = role
        profile.course_id = course.id
        profile.profile_complete = True
        for skill_name in skill_names:
            await db.execute(
                insert(profile_skills)
                .values(profile_id=profile.id, skill_id=skills[skill_name].id)
                .on_conflict_do_nothing()
            )
        for interest_name in interest_names:
            await db.execute(
                insert(profile_interests)
                .values(profile_id=profile.id, interest_id=interests[interest_name].id)
                .on_conflict_do_nothing()
            )


async def seed_admins() -> None:
    settings = get_settings()
    password = settings.seed_admin_password
    emails = [email.strip().lower() for email in settings.admin_emails.split(",") if email.strip()]
    if not password:
        raise RuntimeError("SEED_ADMIN_PASSWORD is required; no default is provided.")
    if len(emails) != 5:
        raise RuntimeError("ADMIN_EMAILS must contain the five project participant addresses.")

    async with SessionLocal() as db:
        course, skills, interests = await seed_reference_data(db)
        for email in emails:
            user = await db.scalar(select(User).where(User.email == email))
            if user is None:
                first_name = email.split("@", 1)[0][:50]
                user = User(
                    email=email,
                    password_hash=hash_password(password),
                    display_name=first_name,
                    first_name=first_name,
                    is_admin=True,
                )
                db.add(user)
            else:
                user.is_admin = True
            await db.flush()
            if await db.scalar(select(Profile.id).where(Profile.user_id == user.id)) is None:
                db.add(Profile(user_id=user.id))
        if settings.demo_seed_password:
            await seed_demo_users(db, settings.demo_seed_password, course, skills, interests)
        await db.commit()


if __name__ == "__main__":
    asyncio.run(seed_admins())