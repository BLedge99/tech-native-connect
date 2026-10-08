"""Project ideas integration tests. specs/08_project_ideas.md §6.

The rule that matters most here is §1: **expressing interest must not open a
conversation.** If it did, any developer could message any business developer
unilaterally, which breaks AGENTS.md §5 rule 2.
"""

import pytest

pytestmark = pytest.mark.anyio

DESCRIPTION = (
    "Route planning that accounts for the emissions of every stop, not just distance. "
    "Three small courier firms said they would pay for this if it existed."
)


async def _author(auth, **kwargs):
    """A business developer with a complete profile — posting requires one."""
    return await auth(role="business_developer", **kwargs)


async def _make_idea(client, session, **overrides):
    body = {
        "title": "Carbon-aware routing for local couriers",
        "description": DESCRIPTION,
        "category": "build_product",
        "skills_needed": ["Python", "PostgreSQL"],
    }
    body.update(overrides)
    response = await session["client"].post("/api/v1/ideas", json=body, headers=session["csrf"])
    return response


# ─── Create ──────────────────────────────────────────────────────────────────


async def test_create_idea(client, auth, seeded_refs):
    author = await _author(auth)
    response = await _make_idea(client, author)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["title"] == "Carbon-aware routing for local couriers"
    assert body["is_open"] is True
    assert body["interest_count"] == 0
    assert body["author"]["id"] == author["id"]


async def test_create_requires_complete_profile(client, auth, seeded_refs):
    """Matching cannot surface you to the developers your idea is for."""
    incomplete = await auth(role="business_developer", skills=0)
    response = await _make_idea(client, incomplete)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "profile_incomplete"


async def test_short_description_rejected(client, auth, seeded_refs):
    author = await _author(auth)
    response = await _make_idea(client, author, description="too short")
    assert response.status_code == 422
    assert "description" in response.json()["error"]["fields"]


async def test_bad_category_rejected(client, auth, seeded_refs):
    author = await _author(auth)
    response = await _make_idea(client, author, category="nonsense")
    assert response.status_code == 422
    assert "category" in response.json()["error"]["fields"]


async def test_title_length_capped(client, auth, seeded_refs):
    author = await _author(auth)
    response = await _make_idea(client, author, title="x" * 200)
    assert response.status_code == 422


# ─── Ownership ───────────────────────────────────────────────────────────────


async def test_edit_own_idea(client, auth, seeded_refs):
    author = await _author(auth)
    created = (await _make_idea(client, author)).json()

    updated = await author["client"].patch(
        f"/api/v1/ideas/{created['id']}",
        json={"title": "Carbon-aware routing v2"},
        headers=author["csrf"],
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "Carbon-aware routing v2"


async def test_edit_other_users_idea(client, auth, seeded_refs):
    """403, not 404 — ideas are public, so existence is not secret."""
    author = await _author(auth)
    other = await auth(role="software_developer")
    created = (await _make_idea(client, author)).json()

    response = await other["client"].patch(
        f"/api/v1/ideas/{created['id']}", json={"title": "hijacked"}, headers=other["csrf"]
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "not_idea_owner"


async def test_delete_other_users_idea(client, auth, seeded_refs):
    author = await _author(auth)
    other = await auth(role="software_developer")
    created = (await _make_idea(client, author)).json()

    response = await other["client"].delete(
        f"/api/v1/ideas/{created['id']}", headers=other["csrf"]
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "not_idea_owner"


async def test_delete_own_idea(client, auth, seeded_refs):
    author = await _author(auth)
    created = (await _make_idea(client, author)).json()
    assert (
        await author["client"].delete(
            f"/api/v1/ideas/{created['id']}", headers=author["csrf"]
        )
    ).status_code == 204


# ─── Browse ──────────────────────────────────────────────────────────────────


async def test_board_defaults_to_open_ideas(client, auth, seeded_refs):
    author = await _author(auth)
    created = (await _make_idea(client, author)).json()

    listed = (await author["client"].get("/api/v1/ideas")).json()["items"]
    assert any(i["id"] == created["id"] for i in listed)

    await author["client"].patch(
        f"/api/v1/ideas/{created['id']}", json={"is_open": False}, headers=author["csrf"]
    )
    after = (await author["client"].get("/api/v1/ideas")).json()["items"]
    assert not any(i["id"] == created["id"] for i in after)

    all_ideas = (
        await author["client"].get("/api/v1/ideas?open_only=false")
    ).json()["items"]
    assert any(i["id"] == created["id"] for i in all_ideas)


async def test_filter_by_category(client, auth, seeded_refs):
    author = await _author(auth)
    await _make_idea(client, author, category="build_product")
    await _make_idea(client, author, category="design_brand", title="A brand for buses")

    items = (
        await author["client"].get("/api/v1/ideas?category=design_brand")
    ).json()["items"]
    assert items
    assert all(i["category"] == "design_brand" for i in items)


async def test_search_filters_by_title(client, auth, seeded_refs):
    author = await _author(auth)
    await _make_idea(client, author)
    await _make_idea(client, author, title="A brand for the bus network",
                     description="Branding and identity work for a regional bus operator.")

    items = (await author["client"].get("/api/v1/ideas?search=carbon")).json()["items"]
    assert len(items) == 1
    assert "Carbon-aware" in items[0]["title"]


async def test_mine_filter(client, auth, seeded_refs):
    mine = await _author(auth, display_name="Mine")
    theirs = await _author(auth, display_name="Theirs")
    await _make_idea(client, mine)
    await _make_idea(client, theirs, title="Someone else's idea")

    items = (await mine["client"].get("/api/v1/ideas?mine=true")).json()["items"]
    assert items
    assert all(i["author"]["id"] == mine["id"] for i in items)


async def test_ideas_require_a_session(client):
    assert (await client.get("/api/v1/ideas")).status_code == 401


async def test_board_pagination(client, auth, seeded_refs):
    author = await _author(auth)
    for i in range(3):
        await _make_idea(client, author, title=f"Paginated idea {i}")

    first = (await author["client"].get("/api/v1/ideas?limit=2")).json()
    assert len(first["items"]) == 2
    assert first["next_cursor"] is not None

    # Cursor, not offset — specs/00 §5. An offset skips rows when someone posts
    # an idea between requests.
    second = (
        await author["client"].get(f"/api/v1/ideas?limit=2&cursor={first['next_cursor']}")
    ).json()
    assert len(second["items"]) == 1
    first_ids = {i["id"] for i in first["items"]}
    second_ids = {i["id"] for i in second["items"]}
    assert not (first_ids & second_ids), "pages must not repeat rows"

    # And the last page reports no further cursor.
    assert second["next_cursor"] is None


# ─── Interest ────────────────────────────────────────────────────────────────


async def test_interest_flow(client, auth, seeded_refs):
    author = await _author(auth)
    developer = await auth(role="software_developer")
    created = (await _make_idea(client, author)).json()

    expressed = await developer["client"].post(
        f"/api/v1/ideas/{created['id']}/interest", headers=developer["csrf"]
    )
    assert expressed.status_code == 200

    listed = (
        await author["client"].get(f"/api/v1/ideas?search=Carbon")
    ).json()["items"][0]
    assert listed["interest_count"] == 1
    assert listed["viewer_has_interested"] is False  # the author's view


async def test_interest_is_idempotent(client, auth, seeded_refs):
    """A double-click must not show an error to someone who just succeeded."""
    author = await _author(auth)
    developer = await auth(role="software_developer")
    created = (await _make_idea(client, author)).json()

    first = await developer["client"].post(
        f"/api/v1/ideas/{created['id']}/interest", headers=developer["csrf"]
    )
    second = await developer["client"].post(
        f"/api/v1/ideas/{created['id']}/interest", headers=developer["csrf"]
    )
    assert first.status_code == second.status_code == 200

    listed = (await author["client"].get("/api/v1/ideas?search=Carbon")).json()["items"][0]
    assert listed["interest_count"] == 1


async def test_interest_notifies_the_author_exactly_once(client, auth, seeded_refs):
    author = await _author(auth)
    developer = await auth(role="software_developer")
    created = (await _make_idea(client, author)).json()

    await developer["client"].post(
        f"/api/v1/ideas/{created['id']}/interest", headers=developer["csrf"]
    )
    await developer["client"].post(
        f"/api/v1/ideas/{created['id']}/interest", headers=developer["csrf"]
    )

    items = (await author["client"].get("/api/v1/notifications")).json()["items"]
    interested = [n for n in items if n["type"] == "idea_interest"]
    assert len(interested) == 1
    assert interested[0]["actor_id"] == developer["id"]


async def test_interest_does_not_create_a_connection_or_thread(client, auth, seeded_refs):
    """THE rule of this feature. Interest is one-way and light; connection is
    mutual opt-in. If interest opened a chat, any developer could message any
    business developer unilaterally."""
    author = await _author(auth)
    developer = await auth(role="software_developer")
    created = (await _make_idea(client, author)).json()

    await developer["client"].post(
        f"/api/v1/ideas/{created['id']}/interest", headers=developer["csrf"]
    )

    assert (await developer["client"].get("/api/v1/threads")).json()["items"] == []

    author_connections = (
        await author["client"].get("/api/v1/connections?filter=received")
    ).json()["items"]
    assert author_connections == []


async def test_cannot_interested_in_own_idea(client, auth, seeded_refs):
    author = await _author(auth)
    created = (await _make_idea(client, author)).json()
    response = await author["client"].post(
        f"/api/v1/ideas/{created['id']}/interest", headers=author["csrf"]
    )
    assert response.status_code == 422


async def test_interest_requires_complete_profile(client, auth, seeded_refs):
    author = await _author(auth)
    bare = await auth(role="software_developer", skills=0)
    created = (await _make_idea(client, author)).json()

    response = await bare["client"].post(
        f"/api/v1/ideas/{created['id']}/interest", headers=bare["csrf"]
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "profile_incomplete"


async def test_withdraw_interest(client, auth, seeded_refs):
    author = await _author(auth)
    developer = await auth(role="software_developer")
    created = (await _make_idea(client, author)).json()

    await developer["client"].post(
        f"/api/v1/ideas/{created['id']}/interest", headers=developer["csrf"]
    )
    withdrawn = await developer["client"].delete(
        f"/api/v1/ideas/{created['id']}/interest", headers=developer["csrf"]
    )
    assert withdrawn.status_code == 204

    listed = (await author["client"].get("/api/v1/ideas?search=Carbon")).json()["items"][0]
    assert listed["interest_count"] == 0


async def test_closed_idea_rejects_new_interest(client, auth, seeded_refs):
    author = await _author(auth)
    developer = await auth(role="software_developer")
    created = (await _make_idea(client, author)).json()
    await author["client"].patch(
        f"/api/v1/ideas/{created['id']}", json={"is_open": False}, headers=author["csrf"]
    )

    response = await developer["client"].post(
        f"/api/v1/ideas/{created['id']}/interest", headers=developer["csrf"]
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "idea_closed"


async def test_withdrawal_allowed_even_when_closed(client, auth, seeded_refs):
    """Changing your mind should never be blocked by someone else's state."""
    author = await _author(auth)
    developer = await auth(role="software_developer")
    created = (await _make_idea(client, author)).json()

    await developer["client"].post(
        f"/api/v1/ideas/{created['id']}/interest", headers=developer["csrf"]
    )
    await author["client"].patch(
        f"/api/v1/ideas/{created['id']}", json={"is_open": False}, headers=author["csrf"]
    )
    withdrawn = await developer["client"].delete(
        f"/api/v1/ideas/{created['id']}/interest", headers=developer["csrf"]
    )
    assert withdrawn.status_code == 204


async def test_viewer_has_interested_is_present_on_every_item(client, auth, seeded_refs):
    """The UI depends on this flag to render the button."""
    author = await _author(auth)
    developer = await auth(role="software_developer")
    await _make_idea(client, author)
    await _make_idea(client, author, title="Second idea",
                     description="A different idea entirely, described at length.")

    items = (await developer["client"].get("/api/v1/ideas")).json()["items"]
    assert items
    assert all("viewer_has_interested" in item for item in items)
    assert all(item["viewer_has_interested"] is False for item in items)

    await developer["client"].post(
        f"/api/v1/ideas/{items[0]['id']}/interest", headers=developer["csrf"]
    )
    after = (await developer["client"].get("/api/v1/ideas")).json()["items"]
    flagged = [item for item in after if item["viewer_has_interested"]]
    assert len(flagged) == 1
    assert flagged[0]["id"] == items[0]["id"]


async def test_skills_needed_is_free_text_not_a_skills_join(client, auth, seeded_refs):
    """Deliberate: an idea needs "a designer who knows Figma", free text expresses
    the specific ask, and ideas must not be blocked by reference-data hygiene."""
    author = await _author(auth)
    response = await _make_idea(client, author, skills_needed=["Maps API", "Rust"])
    assert response.status_code == 201
    assert response.json()["skills_needed"] == ["Maps API", "Rust"]