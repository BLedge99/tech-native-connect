"""Dev seed data. Idempotent — safe to run repeatedly.

Creates the five project participants as admins (spec 09 §2: admins can promote
anyone else later), plus realistic demo data. Without demo data, matching has
nothing to rank and the demo shows empty screens.

Realistic, not "user1@...". Use names.
"""

from __future__ import annotations

import asyncio
import os
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import SessionLocal, engine
from app.models import (
    ConnectionRequest,
    Course,
    Interest,
    Message,
    Photo,
    Profile,
    ProjectIdea,
    Skill,
    Thread,
    User,
    profile_interests,
    profile_skills,
)
from app.models.enums import ConnectionStatus, IdeaCategory, UserRole
from app.services.auth import hash_password
from app.services.profiles import recompute_profile_complete

# EmailStr requires a valid-looking domain, so `.local` is rejected. Use the
# reserved example.com domain — it can never be a real address.
ADMIN_EMAILS = [
    "ben@bootcamp.example.com",
    "joey@bootcamp.example.com",
    "james@bootcamp.example.com",
    "alys@bootcamp.example.com",
    "mick@bootcamp.example.com",
]

COURSES = ["Software Development", "Business Development", "Data Science"]

SKILLS = [
    ("Python", "Language"), ("React", "Framework"), ("TypeScript", "Language"),
    ("Node.js", "Framework"), ("SQL", "Language"), ("PostgreSQL", "Tool"),
    ("Figma", "Design"), ("AWS", "Tool"), ("Docker", "Tool"),
    ("Machine Learning", "Framework"), ("Go", "Language"), ("Flutter", "Framework"),
    ("Excel", "Tool"), ("Market Research", "Business"), ("Pitching", "Business"),
    ("Financial Modelling", "Business"), ("Copywriting", "Business"),
    ("Java", "Language"), ("C#", "Language"), ("Swift", "Language"),
]

INTERESTS = [
    "Climate tech", "Fintech", "Health tech", "EdTech", "Gaming",
    "Social impact", "E-commerce", "AI", "Public transit", "Food",
]

# (name, email, role, display, skills, interests, course index, bio, looking_for)
DEMO_USERS = [
    (
        "Priya Sharma", "priya@example.com", UserRole.BUSINESS_DEVELOPER, "Priya",
        ["Market Research", "Pitching", "Financial Modelling"], ["Climate tech", "Fintech"],
        1,
        "Second-year business developer. I keep noticing small logistics companies "
        "losing money on empty return journeys and I cannot stop thinking about it.",
        "A developer who can build a route optimisation tool.",
    ),
    (
        "Tomas Nowak", "tomas@example.com", UserRole.SOFTWARE_DEVELOPER, "Tomas",
        ["Python", "PostgreSQL", "Docker"], ["Climate tech", "Fintech"],
        0,
        "Backend developer. I like data problems more than interface problems, which "
        "is probably why I keep ending up in logistics conversations.",
        "Someone with a real operational problem I can help with.",
    ),
    (
        "Aisha Bello", "aisha@example.com", UserRole.BUSINESS_DEVELOPER, "Aisha",
        ["Pitching", "Copywriting", "Market Research"], ["Health tech", "Social impact"],
        1,
        "Interested in preventive health. My grandmother was diagnosed with something "
        "a completely preventable disease and it has been on my mind for years.",
        "Someone who wants to build something that helps people catch illness early.",
    ),
    (
        "Liam O'Connor", "liam@example.com", UserRole.SOFTWARE_DEVELOPER, "Liam",
        ["React", "TypeScript", "Node.js"], ["EdTech", "AI"],
        0,
        "Full-stack developer. Built a study planner for my course that about half "
        "the cohort actually uses.",
        "A problem worth solving that I can point a codebase at.",
    ),
    (
        "Mei Chen", "mei@example.com", UserRole.SOFTWARE_DEVELOPER, "Mei",
        ["Python", "Machine Learning", "SQL"], ["AI", "Health tech"],
        2,
        "Data scientist moving towards engineering. Mostly self-taught, most confused "
        "about deployment.",
        "Someone to partner with who can build the thing I can only model.",
    ),
    (
        "Jordan Reyes", "jordan@example.com", UserRole.BUSINESS_DEVELOPER, "Jordan",
        ["Excel", "Financial Modelling", "Copywriting"], ["E-commerce", "Gaming"],
        1,
        "I run a small online shop on the side. Learned more about logistics in a "
        "month than in three years of coursework.",
        "Anyone who wants to make online retail less painful.",
    ),
    (
        "Sam Adeyemi", "sam@example.com", UserRole.SOFTWARE_DEVELOPER, "Sam",
        ["Go", "Docker", "PostgreSQL"], ["Gaming", "Public transit"],
        0,
        "Backend developer, currently rebuilding a bus timetable API because nobody "
        "else would.",
        "Someone who uses public transit and complains about it.",
    ),
    (
        "Elena Petrova", "elena@example.com", UserRole.BUSINESS_DEVELOPER, "Elena",
        ["Pitching", "Market Research"], ["Public transit", "Social impact"],
        1,
        "Business developer with a soft spot for anything that makes cities work "
        "better for the people already in them.",
        "A technical co-founder who wants to fix transit.",
    ),
    (
        "Ravi Patel", "ravi@example.com", UserRole.SOFTWARE_DEVELOPER, "Ravi",
        ["React", "Figma", "TypeScript"], ["EdTech", "Gaming"],
        0,
        "I think in components. Give me a problem and I will draw it.",
        "A business developer with an idea that needs designing.",
    ),
    (
        "Hana Kowalski", "hana@example.com", UserRole.BUSINESS_DEVELOPER, "Hana",
        ["Financial Modelling", "Excel", "Pitching"], ["Fintech", "E-commerce"],
        1,
        "I want to build something that makes boring financial infrastructure "
        "boring for everyone else too.",
        "An engineer who can survive a database schema.",
    ),
]

DEMO_IDEAS = [
    (
        "Carbon-aware routing for local couriers",
        "Route planning that accounts for the emissions of every stop, not just "
        "distance. Small courier firms optimise purely on time and end up burning "
        "fuel on empty return legs. I have spoken to three firms who would use this "
        "if it existed, and they would pay for it.",
        IdeaCategory.BUILD_PRODUCT, ["Python", "PostgreSQL", "Maps API"],
    ),
    (
        "Early-warning symptom checker for over-60s",
        "Not a diagnosis tool. A structured questionnaire that spots the handful of "
        "symptom combinations that warrant a GP visit, then books the appointment. "
        "My grandmother's diagnosis was preventable for about three years.",
        IdeaCategory.BUILD_PRODUCT, ["React", "Node.js", "Postgres"],
    ),
    (
        "Fair-share study planner for cohort timetables",
        "Every cohort loses a week to scheduling clashes. A planner that accounts "
        "for everyone in a cohort's availability, not just one person.",
        IdeaCategory.BUILD_PRODUCT, ["TypeScript", "React"],
    ),
    (
        "Margin-first pricing calculator for small online shops",
        "Most small shops set prices by feel and find out too late they are losing "
        "money on delivery. A calculator that accounts for the shipping costs nobody "
        "warned them about.",
        IdeaCategory.FIND_PROBLEM, ["React", "Excel"],
    ),
    (
        "Pitch night: five founders, five minutes each",
        "Running a pitch night for the cohort. Business developers pitch, developers "
        "ask questions, everyone leaves with contacts. Needs a venue and a sign-up "
        "sheet.",
        IdeaCategory.RUN_CAMPAIGN, [],
    ),
]


async def seed_reference(db: AsyncSession) -> dict[str, dict]:
    courses: dict[str, Course] = {}
    for name in COURSES:
        course = await db.scalar(select(Course).where(Course.name == name))
        if course is None:
            course = Course(name=name)
            db.add(course)
        courses[name] = course

    skills: dict[str, Skill] = {}
    for name, category in SKILLS:
        skill = await db.scalar(select(Skill).where(Skill.name == name))
        if skill is None:
            skill = Skill(name=name, category=category)
            db.add(skill)
        skills[name] = skill

    interests: dict[str, Interest] = {}
    for name in INTERESTS:
        interest = await db.scalar(select(Interest).where(Interest.name == name))
        if interest is None:
            interest = Interest(name=name)
            db.add(interest)
        interests[name] = interest

    await db.flush()
    return {"courses": courses, "skills": skills, "interests": interests}


async def seed_admins(db: AsyncSession, password: str) -> None:
    if not password:
        print(
            "SEED_ADMIN_PASSWORD is not set — skipping admin accounts.\n"
            "Set it in .env and run again. There is deliberately no default:\n"
            "a hardcoded default password is a committed secret.",
            file=sys.stderr,
        )
        return
    for email in ADMIN_EMAILS:
        existing = await db.scalar(select(User).where(User.email == email))
        if existing is not None:
            existing.is_admin = True
            continue
        local = email.split("@")[0]
        db.add(
            User(
                email=email,
                password_hash=hash_password(password),
                display_name=local.capitalize(),
                first_name=local.capitalize(),
                is_admin=True,
            )
        )
    await db.flush()
    print(f"  {len(ADMIN_EMAILS)} admin accounts ready")


async def seed_demo_users(
    db: AsyncSession, ref: dict[str, dict]
) -> list[tuple[User, Profile]]:
    out: list[tuple[User, Profile]] = []
    for (name, email, role, display, skills, interests, course_idx, bio, looking) in DEMO_USERS:
        user = await db.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(
                email=email,
                password_hash=hash_password("demo-password-123"),
                display_name=name,
                first_name=display,
            )
            db.add(user)
            await db.flush()
        profile = await db.scalar(
            select(Profile).options(selectinload(Profile.skills), selectinload(Profile.interests))
            .where(Profile.user_id == user.id)
        )
        if profile is None:
            profile = Profile(user_id=user.id)
            db.add(profile)
        profile.role = role.value
        profile.bio = bio
        profile.looking_for = looking
        profile.course_id = list(ref["courses"].values())[course_idx].id
        await db.flush()

        await db.execute(profile_skills.delete().where(profile_skills.c.profile_id == profile.id))
        for skill_name in skills:
            await db.execute(
                profile_skills.insert().values(
                    profile_id=profile.id, skill_id=ref["skills"][skill_name].id
                )
            )
        await db.execute(profile_interests.delete().where(profile_interests.c.profile_id == profile.id))
        for interest_name in interests:
            await db.execute(
                profile_interests.insert().values(
                    profile_id=profile.id, interest_id=ref["interests"][interest_name].id
                )
            )
        await recompute_profile_complete(db, profile)
        await db.commit()
        profile = await db.scalar(
            select(Profile)
            .options(selectinload(Profile.skills), selectinload(Profile.interests))
            .where(Profile.user_id == user.id)
        )
        out.append((user, profile))
    return out


async def seed_relationships(
    db: AsyncSession, people: list[tuple[User, Profile]]
) -> None:
    """A few connections in mixed states so the UI has something to show."""
    def idx(i: int) -> User:
        return people[i][0]

    async def make(
        sender_i: int, receiver_i: int, status: str, message: str | None
    ) -> None:
        sender, receiver = idx(sender_i), idx(receiver_i)
        lo, hi = sorted([sender.id, receiver.id])
        existing = await db.scalar(
            select(ConnectionRequest).where(
                ConnectionRequest.pair_lo == lo, ConnectionRequest.pair_hi == hi
            )
        )
        if existing is not None:
            return
        db.add(
            ConnectionRequest(
                sender_id=sender.id,
                receiver_id=receiver.id,
                pair_lo=lo,
                pair_hi=hi,
                status=status,
                message=message,
            )
        )

    await make(0, 1, ConnectionStatus.PENDING, "Saw your logistics idea — I've done route optimisation before.")
    await make(2, 3, ConnectionStatus.ACCEPTED, "Would love to build the symptom checker.")
    await make(4, 2, ConnectionStatus.DECLINED, "Interested in the health tech idea.")
    await make(5, 6, ConnectionStatus.ACCEPTED, None)
    await db.flush()

    # A conversation in one accepted thread, so /messages is not empty.
    accepted = await db.scalar(
        select(ConnectionRequest).where(ConnectionRequest.status == ConnectionStatus.ACCEPTED)
    )
    if accepted is not None:
        thread = await db.scalar(
            select(Thread).where(Thread.connection_request_id == accepted.id)
        )
        if thread is None:
            thread = Thread(connection_request_id=accepted.id)
            db.add(thread)
            await db.flush()
            sender = await db.get(User, accepted.sender_id)
            receiver = await db.get(User, accepted.receiver_id)
            db.add(
                Message(
                    thread_id=thread.id,
                    sender_id=receiver.id,
                    body="Hey — is this still something you'd want to build?",
                )
            )
            db.add(
                Message(
                    thread_id=thread.id,
                    sender_id=sender.id,
                    body="Absolutely. Do you want to sketch the data model this week?",
                )
            )


async def seed_ideas(db: AsyncSession, people: list[tuple[User, Profile]]) -> None:
    business = [u for u, p in people if p.role == UserRole.BUSINESS_DEVELOPER.value]
    existing = await db.scalar(select(ProjectIdea).limit(1))
    if existing is not None:
        return
    for i, (title, description, category, skills) in enumerate(DEMO_IDEAS):
        author = business[i % len(business)] if business else people[0][0]
        db.add(
            ProjectIdea(
                author_id=author.id,
                title=title,
                description=description,
                category=category.value,
                skills_needed=skills,
                is_open=i != 3,   # one closed idea so the board shows both states
            )
        )


async def main() -> None:
    from app.config import get_settings

    settings = get_settings()
    print(f"Seeding {settings.database_url}")

    async with SessionLocal() as db:
        ref = await seed_reference(db)
        await db.commit()
        await seed_admins(db, settings.seed_admin_password or os.environ.get("SEED_ADMIN_PASSWORD", ""))
        await db.commit()
        people = await seed_demo_users(db, ref)
        await db.commit()
        await seed_relationships(db, people)
        await db.commit()
        await seed_ideas(db, people)
        await db.commit()

        print(f"  {len(COURSES)} courses, {len(SKILLS)} skills, {len(INTERESTS)} interests")
        print(f"  {len(people)} demo users (password: demo-password-123)")
        print("  connections in mixed states + one sample conversation")
    await engine.dispose()
    print("Seed complete.")


if __name__ == "__main__":
    asyncio.run(main())