"""Admin integration tests. specs/09_admin.md §5.

The point of this file is the auth tests: one per route, not one in a loop that
somebody widens later without noticing. A forgotten guard on an admin route is a
real vulnerability, not a style issue.

Also covers the boundary — admin manages the substrate, not other people's
content — and the audit log.
"""

import uuid

import pytest

pytestmark = pytest.mark.anyio


# Every admin route. If you add one, add it here.
ADMIN_READ_ROUTES = [
    "/api/v1/admin/overview",
    "/api/v1/admin/users",
    "/api/v1/admin/audit",
    "/api/v1/admin/courses",
    "/api/v1/admin/skills",
    "/api/v1/admin/interests",
]

ADMIN_WRITE_ROUTES = [
    ("POST", "/api/v1/admin/skills", {"name": "Rust"}),
    ("POST", "/api/v1/admin/courses", {"name": "Cyber Security"}),
    ("POST", "/api/v1/admin/interests", {"name": "Robotics"}),
]


# ─── Auth, one test per route ────────────────────────────────────────────────


@pytest.mark.parametrize("path", ADMIN_READ_ROUTES)
async def test_admin_read_routes_reject_non_admin(client, auth, make_user, seeded_refs, path):
    """Every read route. AGENTS.md §5 rule 4."""
    a = await auth(is_admin=False)
    response = await a["client"].get(path)
    assert response.status_code == 403, f"{path} returned {response.status_code}"


@pytest.mark.parametrize("method,path,body", ADMIN_WRITE_ROUTES)
async def test_admin_write_routes_reject_non_admin(
    client, auth, make_user, seeded_refs, method, path, body
):
    a = await auth(is_admin=False)
    response = await a["client"].request(method, path, json=body, headers=a["csrf"])
    assert response.status_code == 403, f"{method} {path} returned {response.status_code}"


@pytest.mark.parametrize("path", ADMIN_READ_ROUTES)
async def test_admin_read_routes_require_a_session(client, path):
    """AGENTS.md §5 rule 1 on the admin surface too."""
    response = await client.get(path)
    assert response.status_code == 401


@pytest.mark.parametrize("path", ADMIN_READ_ROUTES)
async def test_admin_routes_allow_an_admin(client, auth, seeded_refs, path):
    admin = await auth(is_admin=True)
    response = await admin["client"].get(path)
    assert response.status_code == 200, f"{path} returned {response.status_code}: {response.text}"


async def test_non_admin_gets_403_not_404(client, auth, seeded_refs):
    """The admin panel is not secret. A signed-in user who finds the URL should
    be told they are not permitted, not left guessing whether it exists."""
    user = await auth(is_admin=False)
    response = await user["client"].get("/api/v1/admin/overview")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


# ─── Users ───────────────────────────────────────────────────────────────────


async def test_admin_can_list_users(client, auth, make_user, seeded_refs):
    admin = await auth(is_admin=True)
    target = await make_user(display_name="Somebody")
    items = (await admin["client"].get("/api/v1/admin/users")).json()["items"]
    ids = [u["id"] for u in items]
    assert str(target.id) in ids


async def test_admin_user_detail_includes_email(client, auth, make_user, seeded_refs):
    """The one legitimate place another user's email is visible. Audited."""
    admin = await auth(is_admin=True)
    target = await make_user(email="target@example.com")
    response = await admin["client"].get(f"/api/v1/admin/users/{target.id}")
    assert response.status_code == 200
    assert response.json()["email"] == "target@example.com"


async def test_admin_reference_lists_use_cursor_pagination(client, auth, seeded_refs):
    """Every collection uses the shared cursor envelope and stable paging."""
    admin = await auth(is_admin=True)
    created_interest = await admin["client"].post(
        "/api/v1/admin/interests",
        json={"name": f"Pagination-{uuid.uuid4().hex}"},
        headers=admin["csrf"],
    )
    assert created_interest.status_code == 200, created_interest.text

    for path in ("courses", "skills", "interests"):
        baseline = (await admin["client"].get(f"/api/v1/admin/{path}?limit=100")).json()
        assert isinstance(baseline, dict) and "items" in baseline
        malformed = await admin["client"].get(f"/api/v1/admin/{path}?cursor=not-a-cursor")
        assert malformed.status_code == 400
        assert malformed.json()["error"]["code"] == "invalid_cursor"
        seen: list[str] = []
        cursor = None
        while True:
            query = "?limit=1" + (f"&cursor={cursor}" if cursor else "")
            page = (await admin["client"].get(f"/api/v1/admin/{path}{query}")).json()
            ids = [item["id"] for item in page["items"]]
            assert not set(ids).intersection(seen), f"{path} repeated an item across pages"
            seen.extend(ids)
            cursor = page["next_cursor"]
            if cursor is None:
                break
        assert set(seen) == {item["id"] for item in baseline["items"]}


async def test_non_admin_cannot_list_users(client, auth, seeded_refs):
    user = await auth(is_admin=False)
    assert (await user["client"].get("/api/v1/admin/users")).status_code == 403


async def test_deactivate_blocks_login(client, auth, seeded_refs):
    admin = await auth(is_admin=True)
    target = await auth(is_admin=False)

    response = await admin["client"].post(
        f"/api/v1/admin/users/{target['id']}/deactivate", headers=admin["csrf"]
    )
    assert response.status_code == 200

    # The target's existing session is dead.
    assert (await target["client"].get("/api/v1/users/me")).status_code == 401


async def test_reactivate_restores_login(client, auth, seeded_refs):
    admin = await auth(is_admin=True)
    target = await auth(is_admin=False)
    await admin["client"].post(
        f"/api/v1/admin/users/{target['id']}/deactivate", headers=admin["csrf"]
    )
    await admin["client"].post(
        f"/api/v1/admin/users/{target['id']}/reactivate", headers=admin["csrf"]
    )

    # A completely fresh login, not the stale session.
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": target["email"], "password": "correct-horse"},
    )
    assert login.status_code == 200, login.text


async def test_deactivated_user_hidden_from_public_profile(client, auth, make_user, seeded_refs):
    """A deactivated user 404s rather than showing a ghost profile."""
    admin = await auth(is_admin=True)
    viewer = await auth(is_admin=False)
    target = await make_user()

    await admin["client"].post(
        f"/api/v1/admin/users/{target.id}/deactivate", headers=admin["csrf"]
    )
    response = await viewer["client"].get(f"/api/v1/users/{target.id}")
    assert response.status_code == 404


async def test_cannot_deactivate_self(client, auth, seeded_refs):
    """You cannot see your own way back in."""
    admin = await auth(is_admin=True)
    response = await admin["client"].post(
        f"/api/v1/admin/users/{admin['id']}/deactivate", headers=admin["csrf"]
    )
    assert response.status_code == 422


async def test_grant_admin_works(client, auth, seeded_refs):
    admin = await auth(is_admin=True)
    target = await auth(is_admin=False)
    assert (await target["client"].get("/api/v1/admin/overview")).status_code == 403

    granted = await admin["client"].post(
        f"/api/v1/admin/users/{target['id']}/grant-admin", headers=admin["csrf"]
    )
    assert granted.status_code == 200
    assert (await target["client"].get("/api/v1/admin/overview")).status_code == 200


async def test_revoke_admin_removes_access(client, auth, seeded_refs):
    admin = await auth(is_admin=True)
    target = await auth(is_admin=False)
    await admin["client"].post(
        f"/api/v1/admin/users/{target['id']}/grant-admin", headers=admin["csrf"]
    )
    assert (await target["client"].get("/api/v1/admin/overview")).status_code == 200

    revoked = await admin["client"].delete(
        f"/api/v1/admin/users/{target['id']}/admin", headers=admin["csrf"]
    )
    assert revoked.status_code == 200
    assert (await target["client"].get("/api/v1/admin/overview")).status_code == 403


async def test_cannot_remove_the_last_admin(client, auth, seeded_refs):
    """An app with no way back in is a demo over."""
    admin = await auth(is_admin=True)
    response = await admin["client"].delete(
        f"/api/v1/admin/users/{admin['id']}/admin", headers=admin["csrf"]
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "last_admin"


# ─── Reference data ──────────────────────────────────────────────────────────


async def test_create_skill_appears_in_profile_form(client, auth, seeded_refs):
    """The real value of the feature: add a skill, and it is in the picker."""
    admin = await auth(is_admin=True)
    created = await admin["client"].post(
        "/api/v1/admin/skills", json={"name": "Rust", "category": "Language"}, headers=admin["csrf"]
    )
    assert created.status_code == 200

    user = await auth(is_admin=False)
    skills = (await user["client"].get("/api/v1/skills")).json()
    assert any(s["name"] == "Rust" for s in skills)


async def test_rename_skill_updates_display(client, auth, seeded_refs):
    admin = await auth(is_admin=True)
    created = await admin["client"].post(
        "/api/v1/admin/skills", json={"name": "Node.js"}, headers=admin["csrf"]
    )
    sid = created.json()["id"]
    renamed = await admin["client"].patch(
        f"/api/v1/admin/skills/{sid}", json={"name": "Node 20"}, headers=admin["csrf"]
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Node 20"


async def test_duplicate_skill_name_rejected(client, auth, seeded_refs):
    admin = await auth(is_admin=True)
    await admin["client"].post(
        "/api/v1/admin/skills", json={"name": "Rust"}, headers=admin["csrf"]
    )
    again = await admin["client"].post(
        "/api/v1/admin/skills", json={"name": "Rust"}, headers=admin["csrf"]
    )
    assert again.status_code == 409


async def test_delete_skill_in_use_rejected(client, auth, seeded_refs):
    """A cascade here would silently strip skills from profiles and change
    everyone's match scores with no explanation."""
    admin = await auth(is_admin=True)
    # make_user sorts skills alphabetically and takes the first, so this user
    # holds "Figma". Delete that one and the guard is genuinely exercised.
    user = await auth(is_admin=False)
    held = (await user["client"].get("/api/v1/users/me")).json()["profile"]["skills"]
    assert held, "the fixture user should have a skill"

    skills = (await admin["client"].get("/api/v1/admin/skills")).json()["items"]
    in_use = next(s for s in skills if s["name"] == held[0]["name"])
    response = await admin["client"].delete(
        f"/api/v1/admin/skills/{in_use['id']}", headers=admin["csrf"]
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "skill_in_use"
    # The count, not the name: the UI resolves the name from the skill row.
    assert "1 profile" in response.json()["error"]["message"] or "profiles" in response.json()["error"]["message"]

    # And the profile still has it.
    mine = (await user["client"].get("/api/v1/users/me")).json()
    assert any(s["name"] == held[0]["name"] for s in mine["profile"]["skills"])


async def test_delete_unused_skill_allowed(client, auth, seeded_refs):
    admin = await auth(is_admin=True)
    created = await admin["client"].post(
        "/api/v1/admin/skills", json={"name": "Elixir"}, headers=admin["csrf"]
    )
    response = await admin["client"].delete(
        f"/api/v1/admin/skills/{created.json()['id']}", headers=admin["csrf"]
    )
    assert response.status_code == 204


async def test_courses_and_interests_crud(client, auth, seeded_refs):
    admin = await auth(is_admin=True)
    course = await admin["client"].post(
        "/api/v1/admin/courses", json={"name": "Cyber Security"}, headers=admin["csrf"]
    )
    assert course.status_code == 200
    renamed = await admin["client"].patch(
        f"/api/v1/admin/courses/{course.json()['id']}",
        json={"name": "Cybersecurity"},
        headers=admin["csrf"],
    )
    assert renamed.json()["name"] == "Cybersecurity"

    interest = await admin["client"].post(
        "/api/v1/admin/interests", json={"name": "Robotics"}, headers=admin["csrf"]
    )
    assert interest.status_code == 200
    deleted = await admin["client"].delete(
        f"/api/v1/admin/interests/{interest.json()['id']}", headers=admin["csrf"]
    )
    assert deleted.status_code == 204


async def test_delete_interest_in_use_rejected(client, auth, seeded_refs):
    admin = await auth(is_admin=True)
    user = await auth(is_admin=False)

    interest = (await admin["client"].get("/api/v1/admin/interests")).json()["items"][0]
    attached = await user["client"].patch(
        "/api/v1/users/me",
        json={"interest_ids": [interest["id"]]},
        headers=user["csrf"],
    )
    assert attached.status_code == 200

    response = await admin["client"].delete(
        f"/api/v1/admin/interests/{interest['id']}", headers=admin["csrf"]
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "skill_in_use"


# ─── The boundary: admin manages the substrate, not content ──────────────────


async def test_admin_cannot_edit_user_profile(client, auth, make_user, seeded_refs):
    """If admin can rewrite a bio, every content field in the app is really
    editable by staff. That is a much bigger product decision than this."""
    admin = await auth(is_admin=True)
    target = await make_user(display_name="Target")

    for method in ("PATCH", "PUT", "POST"):
        response = await admin["client"].request(
            method, f"/api/v1/users/{target.id}", json={"bio": "rewritten"}, headers=admin["csrf"]
        )
        assert response.status_code in (404, 405), f"{method} returned {response.status_code}"

    me = (await admin["client"].get("/api/v1/users/me")).json()
    assert me["id"] != str(target.id)
    assert me["profile"]["bio"] != "rewritten"


async def test_admin_cannot_edit_project_idea(client, auth, seeded_refs):
    admin = await auth(is_admin=True)
    author = await auth(is_admin=False, role="business_developer")
    idea = await author["client"].post(
        "/api/v1/ideas",
        json={
            "title": "Carbon-aware routing for local couriers",
            "description": "Route planning that accounts for the emissions of every stop, "
            "not just distance. Three firms would pay for this.",
            "category": "build_product",
        },
        headers=author["csrf"],
    )
    assert idea.status_code == 201, idea.text

    hijack = await admin["client"].patch(
        f"/api/v1/ideas/{idea.json()['id']}", json={"title": "hijacked"}, headers=admin["csrf"]
    )
    assert hijack.status_code == 403
    assert hijack.json()["error"]["code"] == "not_idea_owner"


async def test_admin_cannot_read_someone_elses_messages(client, auth, seeded_refs):
    """There is deliberately no endpoint for this."""
    admin = await auth(is_admin=True)
    for path in ("/api/v1/admin/messages", "/api/v1/admin/threads"):
        response = await admin["client"].get(path)
        assert response.status_code == 404


# ─── Audit ───────────────────────────────────────────────────────────────────


async def test_audit_log_records_admin_view(client, auth, make_user, seeded_refs):
    """AGENTS.md §5 rule 4: admin reads of user data are audited."""
    admin = await auth(is_admin=True)
    target = await make_user()

    before = (await admin["client"].get("/api/v1/admin/audit")).json()["items"]
    await admin["client"].get(f"/api/v1/admin/users/{target.id}")

    after = (await admin["client"].get("/api/v1/admin/audit")).json()["items"]
    assert len(after) == len(before) + 1
    assert after[0]["action"] == "view_user"
    assert after[0]["target_id"] == str(target.id)
    assert after[0]["admin_id"] == admin["id"]


async def test_audit_log_records_grant_admin(client, auth, seeded_refs):
    admin = await auth(is_admin=True)
    target = await auth(is_admin=False)
    await admin["client"].post(
        f"/api/v1/admin/users/{target['id']}/grant-admin", headers=admin["csrf"]
    )
    items = (await admin["client"].get("/api/v1/admin/audit")).json()["items"]
    assert any(row["action"] == "grant_admin" for row in items)


async def test_audit_log_records_deactivation(client, auth, seeded_refs):
    admin = await auth(is_admin=True)
    target = await auth(is_admin=False)
    await admin["client"].post(
        f"/api/v1/admin/users/{target['id']}/deactivate", headers=admin["csrf"]
    )
    items = (await admin["client"].get("/api/v1/admin/audit")).json()["items"]
    assert any(row["action"] == "deactivate_user" for row in items)


async def test_audit_log_only_visible_to_admins(client, auth, seeded_refs):
    user = await auth(is_admin=False)
    assert (await user["client"].get("/api/v1/admin/audit")).status_code == 403
    assert (await client.get("/api/v1/admin/audit")).status_code == 401


async def test_audit_does_not_log_plain_listing(client, auth, make_user, seeded_refs):
    """Boring on purpose: logging every GET would bury the entries that matter."""
    admin = await auth(is_admin=True)
    await make_user()
    before = (await admin["client"].get("/api/v1/admin/audit")).json()["items"]
    await admin["client"].get("/api/v1/admin/users")
    after = (await admin["client"].get("/api/v1/admin/audit")).json()["items"]
    assert len(after) == len(before)


async def test_failed_admin_action_leaves_no_audit_row(client, auth, seeded_refs):
    """The audit row is written in the same transaction, so a rolled-back action
    does not leave a record claiming it happened."""
    admin = await auth(is_admin=True)
    before = (await admin["client"].get("/api/v1/admin/audit")).json()["items"]

    # Deactivating yourself is refused with 422.
    refused = await admin["client"].post(
        f"/api/v1/admin/users/{admin['id']}/deactivate", headers=admin["csrf"]
    )
    assert refused.status_code == 422

    after = (await admin["client"].get("/api/v1/admin/audit")).json()["items"]
    assert len(after) == len(before)


# ─── Overview ────────────────────────────────────────────────────────────────


async def test_overview_counts_match_reality(client, auth, make_user, seeded_refs):
    admin = await auth(is_admin=True)
    await make_user()
    await make_user()

    overview = (await admin["client"].get("/api/v1/admin/overview")).json()
    listed = (await admin["client"].get("/api/v1/admin/users?limit=100")).json()["items"]
    assert overview["total_users"] == len(listed)
    assert overview["total_users"] >= 3   # two admins plus the extras
    assert (await admin["client"].get("/api/v1/admin/users?limit=101")).status_code == 422
