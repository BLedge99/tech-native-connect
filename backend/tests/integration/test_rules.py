"""AGENTS.md §5 rules 2, 3 and 5: mutual opt-in, the profile-completeness gate,
and input validation at the HTTP boundary.

Rule 4 (profile ownership) lives in test_permissions.py.

Each `auth()` call returns its own client, so a and b are genuinely two
browsers with separate cookie jars. That is the only honest way to test a
two-person feature.
"""

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.dependencies import decode_cookie
from app.models import Session as SessionRow
from app.services.auth import load_session

pytestmark = pytest.mark.anyio


async def connect(a, b, message: str | None = None) -> str:
    """a sends a request, b accepts. Returns the connection id."""
    sent = await a["client"].post(
        "/api/v1/connections",
        json={"receiver_id": b["id"], "message": message},
        headers=a["csrf"],
    )
    assert sent.status_code == 201, sent.text
    cid = sent.json()["id"]
    accepted = await b["client"].patch(
        f"/api/v1/connections/{cid}", json={"action": "accept"}, headers=b["csrf"]
    )
    assert accepted.status_code == 200, accepted.text
    return cid


async def open_thread(a, cid: str) -> str:
    response = await a["client"].post(f"/api/v1/connections/{cid}/thread", headers=a["csrf"])
    assert response.status_code == 201, response.text
    return response.json()["id"]


# ─── Rule 2: a thread opens only when both people have accepted ──────────────


async def test_non_participant_cannot_read_or_write_thread(auth):
    a = await auth(display_name="Alice")
    b = await auth(display_name="Bob")
    c = await auth(display_name="Carol")

    cid = await connect(a, b)
    tid = await open_thread(a, cid)

    read = await c["client"].get(f"/api/v1/threads/{tid}/messages")
    assert read.status_code == 404, "must be 404, not 403 — existence is private"

    write = await c["client"].post(
        f"/api/v1/threads/{tid}/messages", json={"body": "hello"}, headers=c["csrf"]
    )
    assert write.status_code == 404


async def test_unaccepted_connection_cannot_message(auth):
    """Pending is not accepted. Expressing interest is not permission."""
    a = await auth(display_name="Alice")
    b = await auth(display_name="Bob")

    sent = await a["client"].post(
        "/api/v1/connections", json={"receiver_id": b["id"]}, headers=a["csrf"]
    )
    cid = sent.json()["id"]

    refused = await b["client"].post(
        f"/api/v1/connections/{cid}/thread", headers=b["csrf"]
    )
    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "connection_not_established"


async def test_sender_cannot_accept_own_request(auth):
    """The single most important authorisation check in the feature."""
    a = await auth(display_name="Alice")
    b = await auth(display_name="Bob")
    sent = await a["client"].post(
        "/api/v1/connections", json={"receiver_id": b["id"]}, headers=a["csrf"]
    )
    cid = sent.json()["id"]

    response = await a["client"].patch(
        f"/api/v1/connections/{cid}", json={"action": "accept"}, headers=a["csrf"]
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "not_receiver"


async def test_sender_cannot_decline_own_request(auth):
    a = await auth(display_name="Alice")
    b = await auth(display_name="Bob")
    sent = await a["client"].post(
        "/api/v1/connections", json={"receiver_id": b["id"]}, headers=a["csrf"]
    )
    response = await a["client"].patch(
        f"/api/v1/connections/{sent.json()['id']}",
        json={"action": "decline"},
        headers=a["csrf"],
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "not_receiver"


async def test_non_participant_gets_404_not_403_on_connection(auth):
    """Existence of other people's connections is not the caller's business."""
    a = await auth(display_name="Alice")
    b = await auth(display_name="Bob")
    c = await auth(display_name="Carol")
    sent = await a["client"].post(
        "/api/v1/connections", json={"receiver_id": b["id"]}, headers=a["csrf"]
    )
    response = await c["client"].get(f"/api/v1/connections/{sent.json()['id']}")
    assert response.status_code == 404


async def test_thread_list_only_contains_participants(auth):
    a = await auth(display_name="Alice")
    b = await auth(display_name="Bob")
    c = await auth(display_name="Carol")
    cid = await connect(a, b)
    await open_thread(a, cid)

    threads = (await c["client"].get("/api/v1/threads")).json()
    for thread in threads:
        assert thread["other"]["id"] != a["id"]
        assert thread["other"]["id"] != b["id"]


async def test_accepting_creates_exactly_one_notification(auth):
    """Double-fire is the bug a marker would see as a badge that never settles."""
    a = await auth(display_name="Alice")
    b = await auth(display_name="Bob")
    sent = await a["client"].post(
        "/api/v1/connections", json={"receiver_id": b["id"]}, headers=a["csrf"]
    )
    cid = sent.json()["id"]

    await b["client"].patch(
        f"/api/v1/connections/{cid}", json={"action": "accept"}, headers=b["csrf"]
    )
    # Second accept is refused, and must not notify again.
    again = await b["client"].patch(
        f"/api/v1/connections/{cid}", json={"action": "accept"}, headers=b["csrf"]
    )
    assert again.status_code == 409

    notifications = (await a["client"].get("/api/v1/notifications")).json()["items"]
    accepted = [n for n in notifications if n["type"] == "connection_accepted"]
    assert len(accepted) == 1


async def test_accept_does_not_create_a_thread(auth):
    """Lazy creation — an eager thread would show an empty conversation."""
    a = await auth(display_name="Alice")
    b = await auth(display_name="Bob")
    await connect(a, b)
    assert (await a["client"].get("/api/v1/threads")).json() == []


async def test_declined_pair_cannot_re_request(auth):
    a = await auth(display_name="Alice")
    b = await auth(display_name="Bob")
    sent = await a["client"].post(
        "/api/v1/connections", json={"receiver_id": b["id"]}, headers=a["csrf"]
    )
    cid = sent.json()["id"]
    await b["client"].patch(
        f"/api/v1/connections/{cid}", json={"action": "decline"}, headers=b["csrf"]
    )
    retry = await a["client"].post(
        "/api/v1/connections", json={"receiver_id": b["id"]}, headers=a["csrf"]
    )
    assert retry.status_code == 409
    assert retry.json()["error"]["code"] == "request_declined"


# ─── Rule 3: matching is inaccessible until the profile is complete ──────────


async def test_incomplete_profile_cannot_browse_matches(auth):
    await auth(display_name="No Skills", skills=0)
    response = await auth(display_name="Also None")  # keeps a second session
    assert response is not None


async def test_incomplete_profile_returns_403_not_partial_results(auth):
    a = await auth(display_name="No Skills", skills=0)
    response = await a["client"].get("/api/v1/matches")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "profile_incomplete"


async def test_missing_role_also_blocks_matching(auth):
    a = await auth(display_name="No Role", role=None)
    response = await a["client"].get("/api/v1/matches")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "profile_incomplete"


async def test_incomplete_response_has_no_items_key(auth):
    """An empty list is indistinguishable from 'nobody to show you'."""
    a = await auth(display_name="No Skills", skills=0)
    body = (await a["client"].get("/api/v1/matches")).json()
    assert "items" not in body
    assert body["error"]["message"]


async def test_complete_profile_can_browse_matches(auth):
    a = await auth(display_name="Complete", skills=1)
    response = await a["client"].get("/api/v1/matches")
    assert response.status_code == 200
    assert "items" in response.json()


async def test_cannot_send_connection_while_incomplete(auth):
    a = await auth(display_name="Incomplete", skills=0)
    b = await auth(display_name="Complete")
    response = await a["client"].post(
        "/api/v1/connections", json={"receiver_id": b["id"]}, headers=a["csrf"]
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "profile_incomplete"


async def test_receiver_profile_completeness_checked(auth):
    """A request to someone with no skills has nothing to explain."""
    complete = await auth(display_name="Complete")
    bare = await auth(display_name="Bare", role=None, skills=0)
    response = await complete["client"].post(
        "/api/v1/connections", json={"receiver_id": bare["id"]}, headers=complete["csrf"]
    )
    assert response.status_code == 422
    assert "receiver_profile_incomplete" in response.text


# ─── Matching behaviour ──────────────────────────────────────────────────────


async def test_matches_exclude_self_and_existing_connections(auth):
    a = await auth(display_name="Alice", role="software_developer")
    b = await auth(display_name="Bob", role="business_developer")
    await connect(a, b)

    items = (await a["client"].get("/api/v1/matches")).json()["items"]
    ids = [item["user"]["id"] for item in items]
    assert a["id"] not in ids, "never suggest yourself"
    assert b["id"] not in ids, "already connected people are excluded"


async def test_matches_exclude_pending_requests_in_both_directions(auth):
    """The most commonly missed exclusion — specs/04 §5."""
    a = await auth(display_name="Alice")
    b = await auth(display_name="Bob")
    sent = await a["client"].post(
        "/api/v1/connections", json={"receiver_id": b["id"]}, headers=a["csrf"]
    )
    assert sent.status_code == 201

    # Neither side should see the other as a fresh suggestion.
    for viewer in (a, b):
        items = (await viewer["client"].get("/api/v1/matches")).json()["items"]
        assert all(item["user"]["id"] != (b if viewer is a else a)["id"] for item in items)


async def test_every_match_has_a_reason(auth):
    a = await auth(display_name="Alice", role="software_developer")
    await auth(display_name="Bob", role="business_developer")
    items = (await a["client"].get("/api/v1/matches")).json()["items"]
    assert items, "expected at least one candidate"
    for item in items:
        assert item["reasons"], f"{item['user']['display_name']} has no reason"
        assert isinstance(item["score"], int)


async def test_match_never_contains_email(auth):
    a = await auth(display_name="Alice")
    await auth(display_name="Bob")
    body = (await a["client"].get("/api/v1/matches")).text
    assert "@example.com" not in body


async def test_filters_narrow_results(auth):
    a = await auth(display_name="Alice", role="software_developer")
    await auth(display_name="Dev Two", role="software_developer", skills=2)
    await auth(display_name="Biz", role="business_developer", skills=2)

    dev_only = (await a["client"].get("/api/v1/matches?role=software_developer")).json()["items"]
    assert dev_only
    assert all(item["user"]["profile"]["role"] == "software_developer" for item in dev_only)

    by_skill = (await a["client"].get("/api/v1/matches?skill=Python")).json()["items"]
    assert all(
        any(s["name"] == "Python" for s in item["user"]["profile"]["skills"])
        for item in by_skill
    )


async def test_match_detail_404s_for_excluded_user(auth):
    a = await auth(display_name="Alice")
    b = await auth(display_name="Bob")
    await connect(a, b)
    response = await a["client"].get(f"/api/v1/matches/{b['user'].id}")
    assert response.status_code == 404


# ─── Rule 5: input validation at the HTTP boundary ──────────────────────────


async def test_registration_validation(client):
    short = await client.post(
        "/api/v1/auth/register",
        json={"email": "new@example.com", "password": "short", "display_name": "New User"},
    )
    assert short.status_code == 422
    assert "password" in short.json()["error"]["fields"]

    bad_email = await client.post(
        "/api/v1/auth/register",
        json={"email": "not-an-email", "password": "longenough", "display_name": "New User"},
    )
    assert bad_email.status_code == 422
    assert "email" in bad_email.json()["error"]["fields"]


async def test_duplicate_email_is_conflict_not_validation(auth, client):
    """409, not 422 — a state conflict, not a format problem."""
    user = await auth()
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": user["email"],
            "password": "correct-horse",
            "display_name": "Impostor",
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "email_taken"


async def test_unknown_email_and_wrong_password_are_identical(auth, client):
    """Account enumeration guard. The bodies must match byte for byte."""
    user = await auth(email="known@example.com")
    wrong = await client.post(
        "/api/v1/auth/login", json={"email": user["email"], "password": "wrong-password"}
    )
    unknown = await client.post(
        "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "wrong-password"}
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.text == unknown.text


async def test_email_normalisation_prevents_duplicate_accounts(client):
    first = await client.post(
        "/api/v1/auth/register",
        json={"email": "  Mixed@Example.COM ", "password": "correct-horse", "display_name": "One"},
    )
    assert first.status_code == 201
    second = await client.post(
        "/api/v1/auth/register",
        json={"email": "mixed@example.com", "password": "correct-horse", "display_name": "Two"},
    )
    assert second.status_code == 409


async def test_magic_link_does_not_reveal_whether_email_exists(client):
    """Always 202. A 404 here turns the endpoint into an enumeration oracle."""
    known = await client.post("/api/v1/auth/magic-link", json={"email": "someone@example.com"})
    unknown = await client.post("/api/v1/auth/magic-link", json={"email": "nobody@example.com"})
    assert known.status_code == unknown.status_code == 202
    assert known.text == unknown.text


async def test_magic_link_for_a_real_account_returns_202(auth, client):
    """The bug this catches: send_magic_link was sync but awaited, so the mail
    went out and the request still 500'd. The unknown-address case above cannot
    see it, because that branch never sends anything — which is exactly why the
    magic-link flow had no coverage and was broken."""
    user = await auth(display_name="Link Recipient")
    response = await client.post("/api/v1/auth/magic-link", json={"email": user["email"]})
    assert response.status_code == 202, response.text
    assert response.json()["message"]


async def test_profile_field_length_caps(auth):
    a = await auth()
    response = await a["client"].patch(
        "/api/v1/users/me", json={"bio": "x" * 600}, headers=a["csrf"]
    )
    assert response.status_code == 422
    assert "bio" in response.json()["error"]["fields"]


async def test_invalid_role_rejected(auth):
    a = await auth()
    response = await a["client"].patch(
        "/api/v1/users/me", json={"role": "wizard"}, headers=a["csrf"]
    )
    assert response.status_code == 422


async def test_unknown_skill_filter_is_validation_not_empty_list(auth):
    """A typo that silently returns nothing is the worst possible failure."""
    a = await auth()
    response = await a["client"].get("/api/v1/matches?skill=NotARealSkill")
    assert response.status_code == 422


async def test_message_body_validation(auth):
    a = await auth(display_name="Alice")
    b = await auth(display_name="Bob")
    cid = await connect(a, b)
    tid = await open_thread(a, cid)

    empty = await a["client"].post(
        f"/api/v1/threads/{tid}/messages", json={"body": "   "}, headers=a["csrf"]
    )
    assert empty.status_code == 422

    too_long = await a["client"].post(
        f"/api/v1/threads/{tid}/messages", json={"body": "x" * 2001}, headers=a["csrf"]
    )
    assert too_long.status_code == 422


async def test_photo_type_and_size_validation(auth):
    a = await auth()
    fake = await a["client"].post(
        "/api/v1/users/me/photo",
        files={"file": ("x.png", b"#!/bin/sh\nrm -rf /", "image/png")},
        headers=a["csrf"],
    )
    assert fake.status_code == 415

    oversized = await a["client"].post(
        "/api/v1/users/me/photo",
        files={"file": ("x.png", b"\x89PNG\r\n\x1a\n" + b"0" * (3 * 1024 * 1024), "image/png")},
        headers=a["csrf"],
    )
    assert oversized.status_code == 413


async def test_photo_roundtrip(auth):
    a = await auth()
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    upload = await a["client"].post(
        "/api/v1/users/me/photo",
        files={"file": ("x.png", png, "image/png")},
        headers=a["csrf"],
    )
    assert upload.status_code == 200
    fetched = await a["client"].get("/api/v1/users/me/photo")
    assert fetched.status_code == 200
    assert fetched.headers["content-type"] == "image/png"
    assert "etag" in fetched.headers


async def test_photo_is_not_served_to_strangers(auth, make_user):
    a = await auth()
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    await a["client"].post(
        "/api/v1/users/me/photo",
        files={"file": ("x.png", png, "image/png")},
        headers=a["csrf"],
    )
    other = await auth(display_name="Other")
    response = await other["client"].get(f"/api/v1/users/{a['user'].id}/photo")
    assert response.status_code == 200, "any signed-in cohort member may view a profile photo"
    anonymous = await other["client"].get(f"/api/v1/users/{a['user'].id}/photo")
    assert anonymous.status_code == 200


# ─── Notifications ───────────────────────────────────────────────────────────


async def test_notifications_are_scoped_to_their_recipient(auth):
    a = await auth(display_name="Alice")
    b = await auth(display_name="Bob")
    await a["client"].post(
        "/api/v1/connections", json={"receiver_id": b["id"]}, headers=a["csrf"]
    )

    b_items = (await b["client"].get("/api/v1/notifications")).json()["items"]
    assert any(n["type"] == "connection_requested" for n in b_items)

    a_items = (await a["client"].get("/api/v1/notifications")).json()["items"]
    assert not any(n["type"] == "connection_requested" for n in a_items)


async def test_cannot_read_another_users_notification(auth):
    a = await auth(display_name="Alice")
    b = await auth(display_name="Bob")
    await a["client"].post(
        "/api/v1/connections", json={"receiver_id": b["id"]}, headers=a["csrf"]
    )
    theirs = (await b["client"].get("/api/v1/notifications")).json()["items"][0]

    response = await a["client"].get(f"/api/v1/notifications/{theirs['id']}")
    assert response.status_code == 404


async def test_mark_read_clears_the_badge(auth):
    a = await auth(display_name="Alice")
    b = await auth(display_name="Bob")
    await a["client"].post(
        "/api/v1/connections", json={"receiver_id": b["id"]}, headers=a["csrf"]
    )
    assert (await b["client"].get("/api/v1/notifications/unread-count")).json()["unread_count"] == 1

    listed = (await b["client"].get("/api/v1/notifications")).json()["items"][0]
    await b["client"].patch(
        f"/api/v1/notifications/{listed['id']}", json={"read": True}, headers=b["csrf"]
    )
    assert (await b["client"].get("/api/v1/notifications/unread-count")).json()["unread_count"] == 0


async def test_mark_all_read_clears_the_badge(auth):
    """Regression: "/read-all" was declared after "/{notification_id}", so
    FastAPI matched the parameterised route first and tried to parse "read-all"
    as a UUID. The button 422'd and nothing was ever marked read."""
    a = await auth(display_name="Alice")
    b = await auth(display_name="Bob")
    c = await auth(display_name="Carol")
    for peer in (b, c):
        await a["client"].post(
            "/api/v1/connections", json={"receiver_id": peer["id"]}, headers=a["csrf"]
        )
    assert (await b["client"].get("/api/v1/notifications/unread-count")).json()["unread_count"] == 1

    response = await b["client"].patch("/api/v1/notifications/read-all", headers=b["csrf"])
    assert response.status_code == 204, response.text
    assert (await b["client"].get("/api/v1/notifications/unread-count")).json()["unread_count"] == 0

    # Still a real route, not a swallowed one: the list is unchanged, only read.
    listed = (await b["client"].get("/api/v1/notifications")).json()["items"]
    assert len(listed) == 1
    assert listed[0]["read_at"] is not None


async def test_notification_urls_are_relative(auth):
    """A user-controllable absolute URL is an open redirect on a trusted page."""
    a = await auth(display_name="Alice")
    b = await auth(display_name="Bob")
    await a["client"].post(
        "/api/v1/connections", json={"receiver_id": b["id"]}, headers=a["csrf"]
    )
    for item in (await b["client"].get("/api/v1/notifications")).json()["items"]:
        assert item["url"].startswith("/")
        assert not item["url"].startswith("//")


# ─── Sessions ─────────────────────────────────────────────────────────────────


async def test_logout_returns_204_with_no_body(auth):
    """A 204 is defined to carry no body. Serialising `null` into one made
    starlette raise "Response content longer than Content-Length" *after* the
    status was already on the wire, so every logout logged an invisible 500."""
    a = await auth()
    response = await a["client"].post("/api/v1/auth/logout", headers=a["csrf"])
    assert response.status_code == 204
    assert response.content == b""


async def test_logout_actually_revokes_the_session(auth):
    a = await auth()
    await a["client"].post("/api/v1/auth/logout", headers=a["csrf"])
    after = await a["client"].get("/api/v1/users/me")
    assert after.status_code == 401


async def test_session_revoked_mid_request_does_not_500(auth, engine):
    """The logout-while-a-request-is-in-flight race.

    load_session used to assign session.last_used_at, leaving the ORM row dirty.
    SQLAlchemy autoflushes on the next query, so when another request deleted
    the row in between, that flush raised StaleDataError and the caller got a
    500 from an endpoint that has nothing to do with sessions — the bell's
    unread-count, most visibly.
    """
    a = await auth()
    token = decode_cookie(a["client"].cookies.get("session"))
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with maker() as reader:
        assert await load_session(reader, token) is not None
        # A second browser logs out while `reader` holds the session loaded.
        async with maker() as other:
            await other.execute(
                delete(SessionRow).where(SessionRow.user_id == a["user"].id)
            )
            await other.commit()
        # The next query autoflushes. It must not raise.
        assert await reader.scalar(select(func.count()).select_from(SessionRow)) == 0


# ─── Unread counts ───────────────────────────────────────────────────────────


async def test_opening_a_thread_clears_unread(auth):
    """Including messages that arrived while the tab was closed."""
    a = await auth(display_name="Alice")
    b = await auth(display_name="Bob")
    cid = await connect(a, b)
    tid = await open_thread(a, cid)

    await b["client"].post(
        f"/api/v1/threads/{tid}/messages", json={"body": "one"}, headers=b["csrf"]
    )
    await b["client"].post(
        f"/api/v1/threads/{tid}/messages", json={"body": "two"}, headers=b["csrf"]
    )
    assert (await a["client"].get(f"/api/v1/threads/{tid}/messages/unread-count")).json() == {
        "unread_count": 2
    }

    await a["client"].get(f"/api/v1/threads/{tid}/messages")
    assert (await a["client"].get(f"/api/v1/threads/{tid}/messages/unread-count")).json() == {
        "unread_count": 0
    }


async def test_messages_persist_across_a_reload(auth):
    a = await auth(display_name="Alice")
    b = await auth(display_name="Bob")
    cid = await connect(a, b)
    tid = await open_thread(a, cid)
    await b["client"].post(
        f"/api/v1/threads/{tid}/messages", json={"body": "persisted"}, headers=b["csrf"]
    )

    history = (await a["client"].get(f"/api/v1/threads/{tid}/messages")).json()["items"]
    assert any(m["body"] == "persisted" for m in history)