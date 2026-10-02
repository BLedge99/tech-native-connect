"""Shared fixtures. Integration tests run against a REAL Postgres — ADR 0002
and ADR 0010. Tests that pass against a different engine than production are
not worth having.

Everything here is function-scoped and on the same event loop. Mixing a
session-scoped engine with per-test sessions is what produces asyncpg's
"another operation is in progress": a pooled connection cannot cross event
loops. One engine per test is slower and completely unambiguous.
"""

import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("APP_ENV", "test")

# Must happen BEFORE app.config is imported: the engine is built at import time,
# so redirecting the URL afterwards would leave the app on the dev database.
from app.config import get_settings  # noqa: E402

TEST_URL = get_settings().test_database_url
os.environ["DATABASE_URL"] = TEST_URL

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool  # noqa: E402

import app.db as app_db  # noqa: E402
from app.db import Base, get_db  # noqa: E402
import app.models  # noqa: E402,F401  — registers every table

# create_all does not create enum types — the migration does. Mirror them here or
# inserts against the role and idea columns fail.
SCHEMA_SQL = [
    "CREATE EXTENSION IF NOT EXISTS pgcrypto",
    "CREATE EXTENSION IF NOT EXISTS citext",
    "DROP TYPE IF EXISTS user_role CASCADE",
    "DROP TYPE IF EXISTS connection_status CASCADE",
    "DROP TYPE IF EXISTS notification_type CASCADE",
    "DROP TYPE IF EXISTS idea_category CASCADE",
    "CREATE TYPE user_role AS ENUM ('software_developer','business_developer')",
    "CREATE TYPE connection_status AS ENUM ('pending','accepted','declined')",
    "CREATE TYPE notification_type AS ENUM ('connection_requested','connection_accepted',"
    "'connection_declined','new_message','idea_interest')",
    "CREATE TYPE idea_category AS ENUM ('find_problem','build_product','design_brand',"
    "'run_campaign','other')",
]

_schema_ready = False


@pytest_asyncio.fixture
async def engine():
    """One engine per test, on this test's loop. Schema built once per session."""
    global _schema_ready

    test_engine = create_async_engine(TEST_URL, poolclass=NullPool, echo=False)
    async with test_engine.begin() as conn:
        if not _schema_ready:
            for statement in SCHEMA_SQL:
                await conn.execute(text(statement))
            _schema_ready = True
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    # Point the app at this engine. The module-level one was created at import
    # time on a different loop and cannot be reused here.
    await app_db.engine.dispose()
    app_db.engine = test_engine
    app_db.SessionLocal.configure(bind=test_engine)

    yield test_engine

    await test_engine.dispose()


@pytest_asyncio.fixture
async def db(engine):
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        yield session


@pytest_asyncio.fixture
async def client(db):
    """An HTTP client wired to the same session the test uses, so writes are
    visible to both and never concurrent."""
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http
    app.dependency_overrides.clear()


def unique_email(prefix: str = "user") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}@example.com"


@pytest_asyncio.fixture
async def seeded_refs(db):
    """Courses, skills and interests. Stands in for app/seed.py in tests."""
    from app.models import Course, Interest, Skill

    db.add_all([Course(name="Software Development"), Course(name="Business Development")])
    for name in ("Python", "React", "SQL", "Figma"):
        db.add(Skill(name=name, category="Language"))
    db.add(Interest(name="Fintech"))
    await db.commit()
    return {
        "course": await db.scalar(select(Course.id).where(Course.name == "Software Development")),
        "other_course": await db.scalar(
            select(Course.id).where(Course.name == "Business Development")
        ),
    }


@pytest_asyncio.fixture
async def make_user(db):
    """Creates a user with a profile.

    `skills=1` (the default) is enough to make profile_complete true, which is
    the state most tests want.
    """

    async def _make(
        *,
        email: str | None = None,
        password: str = "correct-horse",
        display_name: str = "Test User",
        role: str | None = "software_developer",
        skills: int = 1,
        is_admin: bool = False,
        is_active: bool = True,
    ):
        from app.models import Profile, Skill, User, profile_skills
        from app.services.auth import hash_password

        user = User(
            email=email or unique_email(),
            password_hash=hash_password(password),
            display_name=display_name,
            first_name=display_name.split()[0],
            is_admin=is_admin,
            is_active=is_active,
        )
        db.add(user)
        await db.flush()

        profile = Profile(user_id=user.id, role=role)
        db.add(profile)
        await db.flush()

        if skills:
            rows = (await db.scalars(select(Skill.id).order_by(Skill.name))).all()
            for sid in rows[:skills]:
                await db.execute(
                    profile_skills.insert().values(profile_id=profile.id, skill_id=sid)
                )
        profile.profile_complete = bool(role) and skills > 0
        await db.commit()
        return user

    return _make


@pytest_asyncio.fixture
async def auth(db, make_user, seeded_refs):
    """Signs a user in and returns their OWN client, plus their CSRF header.

    Each call creates a separate AsyncClient because a cookie jar holds exactly
    one session. Two `auth` calls in one test means two browsers — which is what
    any test about two people actually needs.
    """

    async def _login(**kwargs) -> "dict":
        from app.main import app

        user = await make_user(**kwargs)
        app.dependency_overrides[get_db] = lambda: db
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as http:
            response = await http.post(
                "/api/v1/auth/login",
                json={"email": user.email, "password": kwargs.get("password", "correct-horse")},
            )
            assert response.status_code == 200, response.text
            me = await http.get("/api/v1/users/me")
            assert me.status_code == 200, me.text

        # The context manager closed the client, so hand back a fresh one that
        # shares the cookie header the login produced.
        session_cookie = http.cookies.get("session")
        browser = AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        )
        if session_cookie:
            browser.cookies.set("session", session_cookie)
        return {
            "user": user,
            # str(...) throughout: a UUID is not JSON serialisable and these get
            # interpolated straight into request bodies.
            "id": str(user.id),
            "email": user.email,
            "me": me.json(),
            "csrf": {"X-CSRF-Token": me.json()["csrf_token"]},
            "client": browser,
        }

    return _login

# ─── Live server, for WebSocket tests ─────────────────────────────────────────
# httpx's ASGITransport cannot do WebSockets, and the realtime layer is the one
# thing in this project that cannot be proven through HTTP alone. So these tests
# run the app as a real process and talk to it over the wire.
#
# The schema is created ONCE for the live server and truncated between tests —
# not dropped and recreated, because a running server holds prepared statements.

import json
import os as _os
import socket
import subprocess
import time


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for(url: str, timeout: float = 45.0) -> bool:
    deadline = time.time() + timeout
    import urllib.error
    import urllib.request

    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status == 200:
                    return True
        except (urllib.error.URLError, OSError):
            time.sleep(0.4)
    return False


@pytest.fixture(scope="module")
def live_server():
    """A real uvicorn process on the test database. Yields (http_base, ws_base)."""
    import asyncpg  # noqa: F401  — ensures the driver is importable

    port = _free_port()
    env = {**_os.environ, "DATABASE_URL": TEST_URL, "APP_ENV": "test", "SEED_ADMIN_PASSWORD": ""}

    # Build the schema before the server starts so it has something to serve.
    bootstrap = subprocess.run(
        [_os.sys.executable, "-c", _SCHEMA_BOOTSTRAP, str(ROOT), TEST_URL, json.dumps(SCHEMA_SQL)],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env=env,
        timeout=120,
    )
    if bootstrap.returncode != 0:
        raise RuntimeError(f"schema bootstrap failed:\n{bootstrap.stderr}")

    # Reference data. The live server's database is empty apart from the schema,
    # and a profile cannot be completed without skills to pick from.
    seeded = subprocess.run(
        [_os.sys.executable, "-c", _SEED_REFS, str(ROOT), TEST_URL],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env=env,
        timeout=60,
    )
    if seeded.returncode != 0:
        raise RuntimeError(f"reference seed failed:\n{seeded.stderr}")

    proc = subprocess.Popen(
        [
            _os.sys.executable, "-m", "uvicorn", "app.main:app",
            "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning",
        ],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    http_base = f"http://127.0.0.1:{port}"
    try:
        if not _wait_for(f"{http_base}/api/v1/health"):
            out = proc.stdout.read().decode() if proc.stdout else ""
            raise RuntimeError(f"live server did not start:\n{out[-2000:]}")
        yield http_base, f"ws://127.0.0.1:{port}/api/v1/ws"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


_SCHEMA_BOOTSTRAP = """
import asyncio, json, sys
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
sys.path.insert(0, sys.argv[1])
from app.db import Base
import app.models  # noqa

async def go():
    e = create_async_engine(sys.argv[2], poolclass=NullPool)
    async with e.begin() as c:
        for stmt in json.loads(sys.argv[3]):
            await c.execute(text(stmt))
        await c.run_sync(Base.metadata.drop_all)
        await c.run_sync(Base.metadata.create_all)
    await e.dispose()

asyncio.run(go())
"""


_TRUNCATE_BOOTSTRAP = """
import asyncio, sys
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
sys.path.insert(0, sys.argv[1])
from app.db import Base
import app.models  # noqa

async def go():
    e = create_async_engine(sys.argv[2], poolclass=NullPool)
    tables = ", ".join(f'"{t.name}"' for t in reversed(Base.metadata.sorted_tables))
    async with e.begin() as c:
        await c.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    await e.dispose()

asyncio.run(go())
"""


@pytest.fixture
def ws_client(live_server):
    """An httpx client against the live server.

    One per signed-in user, because a cookie jar holds exactly one session.
    """

    def factory(cookies: dict | None = None):
        import httpx

        http = httpx.Client(base_url=live_server[0], timeout=20)
        if cookies:
            for key, value in cookies.items():
                http.cookies.set(key, value)
        return http

    return factory


@pytest.fixture
def truncate_test_tables():
    """Empty every table.

    TRUNCATE, not drop-and-recreate: the live server holds prepared statements,
    and dropping tables under a running process is how you get confusing
    "relation does not exist" failures halfway through a test.

    Runs in a subprocess because the live server owns the only safe event loop
    for these connections.
    """

    def _truncate() -> None:
        result = subprocess.run(
            [_os.sys.executable, "-c", _TRUNCATE_BOOTSTRAP, str(ROOT), TEST_URL],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
            timeout=60,
        )
        # Truncate also empties the reference tables, and a profile cannot be
        # completed without skills to pick from. Re-seed in the same script.
        refs = subprocess.run(
            [_os.sys.executable, "-c", _SEED_REFS, str(ROOT), TEST_URL],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
            timeout=60,
        )
        if refs.returncode != 0:
            raise RuntimeError(f"reference seed failed:\n{refs.stderr[-2000:]}")
        if result.returncode != 0:
            raise RuntimeError(f"truncate failed:\n{result.stderr[-2000:]}")

    return _truncate


_SEED_REFS = """
import asyncio, sys
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
sys.path.insert(0, sys.argv[1])
from app.db import Base
from app.models import Course, Interest, Skill
import app.models  # noqa

async def go():
    e = create_async_engine(sys.argv[2], poolclass=NullPool)
    async with e.begin() as c:
        pass
    maker = __import__('sqlalchemy.ext.asyncio', fromlist=['async_sessionmaker'])
    async with maker.async_sessionmaker(e, expire_on_commit=False)() as db:
        for name in ("Software Development", "Business Development"):
            db.add(Course(name=name))
        for name, cat in (("Python", "Language"), ("React", "Framework"),
                          ("SQL", "Language"), ("Figma", "Design")):
            db.add(Skill(name=name, category=cat))
        db.add(Interest(name="Fintech"))
        await db.commit()
    await e.dispose()

asyncio.run(go())
"""
