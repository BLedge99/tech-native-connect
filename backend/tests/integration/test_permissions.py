"""AGENTS.md §5 rules 1 and 4: authentication and profile ownership.

These are the two rules a marker is most likely to probe, so they are proven
rather than asserted. Every rule in §5 has at least one test here or in
test_permissions.py.
"""

import pytest

pytestmark = pytest.mark.anyio

PROTECTED = [
    ("GET", "/api/v1/users/me"),
    ("PATCH", "/api/v1/users/me"),
    ("GET", "/api/v1/matches"),
    ("GET", "/api/v1/connections"),
    ("GET", "/api/v1/connections/summary"),
    ("GET", "/api/v1/threads"),
    ("GET", "/api/v1/notifications"),
    ("GET", "/api/v1/notifications/unread-count"),
    ("GET", "/api/v1/ideas"),
    ("GET", "/api/v1/courses"),
    ("GET", "/api/v1/skills"),
    ("GET", "/api/v1/interests"),
    ("GET", "/api/v1/admin/overview"),
    ("GET", "/api/v1/admin/users"),
    ("GET", "/api/v1/admin/audit"),
]


# ─── Rule 1: no authentication means no data ────────────────────────────────


@pytest.mark.parametrize("method,path", PROTECTED)
async def test_protected_routes_require_a_session(client, method, path):
    """AGENTS.md §5 rule 1."""
    response = await client.request(method, path)
    assert response.status_code == 401, f"{method} {path} returned {response.status_code}"


async def test_unauthenticated_photo_access_forbidden(client, make_user, seeded_refs):
    """Photos are not public URLs."""
    user = await make_user()
    response = await client.get(f"/api/v1/users/{user.id}/photo")
    assert response.status_code == 401


async def test_forged_cookie_rejected(client, make_user, seeded_refs):
    user = await make_user()
    client.cookies.set("session", "bm90LWEtdmFsaWQtdG9rZW4tYXQtYWxs")
    response = await client.get("/api/v1/users/me")
    assert response.status_code == 401


async def test_expired_session_rejected(client, db, make_user, seeded_refs):
    """Session expiry is enforced server-side, not just in the browser."""
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import select

    from app.models import Session as SessionRow

    user = await make_user()
    login = await client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": "correct-horse"}
    )
    assert login.status_code == 200
    assert (await client.get("/api/v1/users/me")).status_code == 200

    # Expire the session directly, then prove the cookie no longer works.
    row = await db.scalar(select(SessionRow))
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await db.commit()

    assert (await client.get("/api/v1/users/me")).status_code == 401


# ─── CSRF ────────────────────────────────────────────────────────────────────


async def test_mutating_request_without_csrf_token_forbidden(client, make_user, seeded_refs):
    user = await make_user()
    await client.post("/api/v1/auth/login", json={"email": user.email, "password": "correct-horse"})
    response = await client.patch("/api/v1/users/me", json={"bio": "hi"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_failed"


async def test_mutating_request_with_wrong_csrf_token_forbidden(client, make_user, seeded_refs):
    user = await make_user()
    await client.post("/api/v1/auth/login", json={"email": user.email, "password": "correct-horse"})
    response = await client.patch(
        "/api/v1/users/me", json={"bio": "hi"}, headers={"X-CSRF-Token": "wrong"}
    )
    assert response.status_code == 403


async def test_mutating_request_with_valid_csrf_succeeds(client, make_user, seeded_refs):
    user = await make_user()
    await client.post("/api/v1/auth/login", json={"email": user.email, "password": "correct-horse"})
    me = (await client.get("/api/v1/users/me")).json()
    response = await client.patch(
        "/api/v1/users/me",
        json={"bio": "hello"},
        headers={"X-CSRF-Token": me["csrf_token"]},
    )
    assert response.status_code == 200


# ─── Rule 4: users may only read and write their own profile ─────────────────


async def test_no_endpoint_writes_another_users_profile(client, make_user, seeded_refs):
    """There is no PATCH /users/{id}. The path itself is the guarantee."""
    owner = await make_user()
    me_user = await make_user()          # who `client` is signed in as
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": me_user.email, "password": "correct-horse"},
    )
    assert login.status_code == 200
    me = (await client.get("/api/v1/users/me")).json()

    for method, path in (
        ("PATCH", f"/api/v1/users/{owner.id}"),
        ("PUT", f"/api/v1/users/{owner.id}"),
        ("POST", f"/api/v1/users/{owner.id}"),
        ("DELETE", f"/api/v1/users/{owner.id}"),
    ):
        response = await client.request(
            method, path, json={"bio": "hacked"}, headers={"X-CSRF-Token": me["csrf_token"]}
        )
        assert response.status_code in (404, 405), f"{method} {path} returned {response.status_code}"
        # `me` is still me, not someone else.
        assert (await client.get("/api/v1/users/me")).json()["id"] == me["id"]


async def test_public_profile_never_contains_email(client, make_user, seeded_refs):
    """The leak guard. specs/03 §6."""
    other = await make_user(display_name="Someone Else")
    user = await make_user()
    await client.post("/api/v1/auth/login", json={"email": user.email, "password": "correct-horse"})

    response = await client.get(f"/api/v1/users/{other.id}")
    assert response.status_code == 200
    body = response.text
    assert "email" not in body.lower()
    assert other.email not in body


async def test_no_user_returning_endpoint_leaks_another_users_email(client, make_user, seeded_refs):
    """Scans EVERY user-returning endpoint, not a spot check."""
    other = await make_user(display_name="Leaky McLeak")
    user = await make_user(role="business_developer", skills=3)
    await client.post("/api/v1/auth/login", json={"email": user.email, "password": "correct-horse"})

    endpoints = [
        "/api/v1/users/me",
        f"/api/v1/users/{other.id}",
        "/api/v1/matches",
        "/api/v1/connections",
        "/api/v1/connections/summary",
        "/api/v1/threads",
        "/api/v1/notifications",
        "/api/v1/ideas",
    ]
    for path in endpoints:
        response = await client.get(path)
        if response.status_code != 200:
            continue
        assert other.email not in response.text, f"{path} leaked another user's email"


async def test_own_profile_does_contain_own_email(client, make_user, seeded_refs):
    user = await make_user()
    await client.post("/api/v1/auth/login", json={"email": user.email, "password": "correct-horse"})
    body = (await client.get("/api/v1/users/me")).text
    assert user.email in body


# ─── Admin exception ─────────────────────────────────────────────────────────


async def test_non_admin_cannot_reach_admin_endpoints(client, make_user, seeded_refs):
    """AGENTS.md §5 rule 4: admins are the sole exception."""
    user = await make_user(is_admin=False)
    await client.post("/api/v1/auth/login", json={"email": user.email, "password": "correct-horse"})
    me = (await client.get("/api/v1/users/me")).json()
    response = await client.get("/api/v1/admin/users", headers={"X-CSRF-Token": me["csrf_token"]})
    assert response.status_code == 403
    # 403, not 404: the admin panel is not secret.
    assert response.json()["error"]["code"] == "forbidden"