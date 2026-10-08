"""Regression tests for the §12 review findings.

Added 8 October 2026, **before any fix**. Every test here is expected to fail
against the code as it stands. See handoff.md §12 for the findings and §13 for
why each test is shaped the way it is.

  B2  unread_messages is hardcoded to 0
  B9  photo upload reads the whole body before the cap
  B10 dev video route has no path containment and the wrong error shape
  B11 renaming reference data onto an existing name is an unhandled 500
  B12 match reasons re-derive shared skills by NAME, not by id
  B13 delete_interest reports the skill error code
  B14 an unknown course_id on an idea is an unhandled 500, not a 422
  B17 one idea detail request sweeps the whole category
  B18 list endpoints run O(rows) queries

Three properties make these hard to satisfy by faking a response:

  * **Conservation laws, not literals.** `test_unread_message_count_is_a_...`
    does not assert `4`. It asserts equality with the thread list's own sum,
    and that one more message moves both by exactly one. A hardcoded `0`
    cannot track a state change.
  * **Database assertions.** Renames, uploads and idea writes are verified by
    reading the rows back. A status code can be hardcoded; a row cannot.
  * **Real query counts.** The N+1 tests count actual SQL statements emitted
    through a SQLAlchemy event listener.
"""

from __future__ import annotations

import base64
import contextlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Iterator

import pytest
from fastapi import FastAPI
from fastapi.exceptions import HTTPException
from sqlalchemy import event, func, select

from app.errors import AppError, app_error_handler, http_error_handler
from app.models import Course, Interest, Photo, ProjectIdea, Skill

pytestmark = pytest.mark.anyio

DESCRIPTION = (
    "A routing service that weights emissions per stop rather than total "
    "distance, so a courier running three short hops is not treated as the "
    "same as one long motorway leg. Two regional firms said they would pay."
)

# A real 1x1 PNG. The server sniffs magic bytes and never decodes, but the
# success cases should still upload something that is genuinely an image.
PNG_1X1 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAE"
    "hQGAhKmMIQAAAABJRU5ErkJggg=="
)


# ─── Shared helpers ──────────────────────────────────────────────────────────


async def _connect(a, b) -> str:
    """a sends a connection request, b accepts. Returns the connection id."""
    sent = await a["client"].post(
        "/api/v1/connections", json={"receiver_id": b["id"]}, headers=a["csrf"]
    )
    assert sent.status_code == 201, sent.text
    cid = sent.json()["id"]
    accepted = await b["client"].patch(
        f"/api/v1/connections/{cid}", json={"action": "accept"}, headers=b["csrf"]
    )
    assert accepted.status_code == 200, accepted.text
    return cid


async def _open_thread(session, cid: str) -> str:
    response = await session["client"].post(
        f"/api/v1/connections/{cid}/thread", headers=session["csrf"]
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _send(session, thread_id: str, body: str) -> None:
    response = await session["client"].post(
        f"/api/v1/threads/{thread_id}/messages", json={"body": body}, headers=session["csrf"]
    )
    assert response.status_code == 201, response.text


async def _unread_by_thread(session) -> dict[str, int]:
    """Unread counts keyed by thread, from the thread list itself.

    The reference comes from a different endpoint than the one under test —
    otherwise the assertion would be comparing a value with itself.
    """
    page = (await session["client"].get("/api/v1/threads")).json()
    return {thread["id"]: thread["unread_count"] for thread in page["items"]}


async def _summary_unread(session) -> int:
    body = (await session["client"].get("/api/v1/connections/summary")).json()
    return body["unread_messages"]


@contextlib.contextmanager
def count_statements(engine) -> Iterator[list[str]]:
    """Collect every SQL statement the engine emits inside the block."""
    statements: list[str] = []

    def _record(_conn, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", _record)
    try:
        yield statements
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _record)


# ─── B2: unread_messages ────────────────────────────────────────────────────


async def test_unread_message_count_is_a_conservation_law(auth, seeded_refs):
    """B2. `connection_summary` hardcodes `unread_messages=0`.

    specs/05_connection_requests.md §237 documents a real count. Nothing reads
    the field, so no test and no screen notices.

    Asserts a *relation* between live endpoints plus a state change, never a
    literal. Four ways a fake fails:

      1. it must equal the thread list's own sum,
      2. one new message must move both by exactly one,
      3. reading one thread must drop the summary by exactly that thread's
         count,
      4. the untouched thread's count must not move.
    """
    viewer = await auth(display_name="Watcher")
    first = await auth(display_name="First Partner")
    second = await auth(display_name="Second Partner")

    # Both partners send to the viewer, so the viewer is the receiver.
    tid_one = await _open_thread(viewer, await _connect(first, viewer))
    tid_two = await _open_thread(viewer, await _connect(second, viewer))

    for index in range(3):
        await _send(first, tid_one, f"first partner message {index}")
    await _send(second, tid_two, "second partner message")

    counts = await _unread_by_thread(viewer)
    assert counts[tid_one] == 3 and counts[tid_two] == 1, (
        f"fixture is wrong: {counts}"
    )
    assert sum(counts.values()) == 4
    assert await _summary_unread(viewer) == sum(counts.values()), (
        "connections/summary does not agree with the thread list it summarises"
    )

    # One more message moves both by exactly one.
    await _send(first, tid_one, "one more")
    counts = await _unread_by_thread(viewer)
    assert counts[tid_one] == 4
    assert await _summary_unread(viewer) == sum(counts.values()) == 5, (
        "the summary did not track a new unread message"
    )

    # Reading one thread clears exactly that thread and disturbs nothing else.
    await viewer["client"].get(f"/api/v1/threads/{tid_two}/messages")

    after = await _unread_by_thread(viewer)
    assert after[tid_two] == 0, "reading a thread did not clear its unread count"
    assert after[tid_one] == 4, "reading one thread disturbed the other"
    assert await _summary_unread(viewer) == sum(after.values()) == 4


async def test_unread_message_count_is_zero_when_nothing_is_unread(auth, seeded_refs):
    """The value must be derived, not merely non-zero. Once everything is read
    the correct answer genuinely is zero, so this distinguishes a real
    computation from a constant that happens to match somewhere."""
    viewer = await auth(display_name="Quiet")
    partner = await auth(display_name="Chatty")
    tid = await _open_thread(viewer, await _connect(partner, viewer))
    await _send(partner, tid, "read me")

    assert await _summary_unread(viewer) == 1
    await viewer["client"].get(f"/api/v1/threads/{tid}/messages")
    assert await _summary_unread(viewer) == 0
    assert sum((await _unread_by_thread(viewer)).values()) == 0


async def test_unread_message_count_ignores_my_own_messages(auth, seeded_refs):
    """Unread means "not mine". A summary that simply counted every message
    would satisfy the conservation test above, so this pins the harder half."""
    viewer = await auth(display_name="Talker")
    partner = await auth(display_name="Listener")
    tid = await _open_thread(viewer, await _connect(partner, viewer))

    for index in range(4):
        await _send(viewer, tid, f"mine {index}")

    assert sum((await _unread_by_thread(viewer)).values()) == 0, (
        "the viewer counted their own messages as unread"
    )
    assert await _summary_unread(viewer) == 0


async def test_unread_message_count_spans_every_thread(auth, seeded_refs):
    """Not just the busiest thread. A summary that read one row would pass the
    other tests."""
    viewer = await auth(display_name="Spread Thin")
    partners = [await auth(display_name=f"Spread Partner {index}") for index in range(3)]

    threads = []
    for index, partner in enumerate(partners):
        tid = await _open_thread(viewer, await _connect(partner, viewer))
        threads.append(tid)
        for message in range(index + 1):
            await _send(partner, tid, f"partner {index} message {message}")

    counts = await _unread_by_thread(viewer)
    assert set(counts.values()) == {1, 2, 3}, f"fixture is wrong: {counts}"
    assert await _summary_unread(viewer) == 6, (
        f"expected the sum across all {len(threads)} threads, got "
        f"{await _summary_unread(viewer)}"
    )


# ─── B11: renaming reference data ────────────────────────────────────────────


async def test_renaming_a_skill_onto_an_existing_name_is_a_conflict(auth, seeded_refs, db):
    """B11. `update_skill` never checks for a collision and `skills.name` is
    `unique=True`, so the commit raises an unhandled IntegrityError -> 500.

    The database read is the point. Asserting only the status code would let a
    handler that returned 409 without touching anything pass, and would not
    catch a 500 that happened to leave the rows alone.
    """
    admin = await auth(is_admin=True)

    kept = await admin["client"].post(
        "/api/v1/admin/skills", json={"name": "Zephyr"}, headers=admin["csrf"]
    )
    moved = await admin["client"].post(
        "/api/v1/admin/skills", json={"name": "Quicksilver"}, headers=admin["csrf"]
    )
    assert kept.status_code == 201, kept.text
    assert moved.status_code == 201, moved.text

    response = await admin["client"].patch(
        f"/api/v1/admin/skills/{moved.json()['id']}",
        json={"name": "Zephyr"},
        headers=admin["csrf"],
    )
    assert response.status_code == 409, (
        f"renaming onto a taken name returned {response.status_code}: {response.text[:300]}"
    )
    assert response.json()["error"]["code"] == "already_exists"

    stored = dict(
        (
            await db.execute(
                select(Skill.id, Skill.name).where(
                    Skill.id.in_([kept.json()["id"], moved.json()["id"]])
                )
            )
        ).all()
    )
    assert set(stored.values()) == {"Zephyr", "Quicksilver"}, (
        f"the rejected rename still changed stored data: {stored}"
    )


async def test_renaming_an_interest_onto_an_existing_name_is_a_conflict(
    auth, seeded_refs, db
):
    """B11 for interests. Same defect, same assertion."""
    admin = await auth(is_admin=True)

    kept = await admin["client"].post(
        "/api/v1/admin/interests", json={"name": "Aeronautics"}, headers=admin["csrf"]
    )
    moved = await admin["client"].post(
        "/api/v1/admin/interests", json={"name": "Hydroponics"}, headers=admin["csrf"]
    )
    assert kept.status_code == 201 and moved.status_code == 201

    response = await admin["client"].patch(
        f"/api/v1/admin/interests/{moved.json()['id']}",
        json={"name": "Aeronautics"},
        headers=admin["csrf"],
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "already_exists"

    stored = set(
        await db.scalars(
            select(Interest.name).where(
                Interest.id.in_([kept.json()["id"], moved.json()["id"]])
            )
        )
    )
    assert stored == {"Aeronautics", "Hydroponics"}, f"stored names changed: {stored}"


async def test_renaming_a_course_onto_an_existing_name_is_a_conflict(auth, seeded_refs, db):
    """B11 for courses. `create_course` checks for a collision; `update_course`
    does not, and `courses.name` is `unique=True`."""
    admin = await auth(is_admin=True)

    kept = await admin["client"].post(
        "/api/v1/admin/courses", json={"name": "Underwater Basket Weaving"}, headers=admin["csrf"]
    )
    moved = await admin["client"].post(
        "/api/v1/admin/courses", json={"name": "Advanced Kite Design"}, headers=admin["csrf"]
    )
    assert kept.status_code == 201 and moved.status_code == 201

    response = await admin["client"].patch(
        f"/api/v1/admin/courses/{moved.json()['id']}",
        json={"name": "Underwater Basket Weaving"},
        headers=admin["csrf"],
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "already_exists"

    stored = set(
        await db.scalars(
            select(Course.name).where(
                Course.id.in_([kept.json()["id"], moved.json()["id"]])
            )
        )
    )
    assert stored == {"Underwater Basket Weaving", "Advanced Kite Design"}, f"changed: {stored}"


async def test_renaming_to_a_free_name_still_works(auth, seeded_refs):
    """The fix must not turn rename into a no-op. Renaming is the operation
    admins actually need — see the comment on `update_skill`."""
    admin = await auth(is_admin=True)
    created = await admin["client"].post(
        "/api/v1/admin/skills", json={"name": "Ephemeral"}, headers=admin["csrf"]
    )
    assert created.status_code == 201

    response = await admin["client"].patch(
        f"/api/v1/admin/skills/{created.json()['id']}",
        json={"name": "Ephemeral Prime"},
        headers=admin["csrf"],
    )
    assert response.status_code == 200, response.text
    assert response.json()["name"] == "Ephemeral Prime"

    # Renaming to its own current name is not a self-collision.
    same = await admin["client"].patch(
        f"/api/v1/admin/skills/{created.json()['id']}",
        json={"name": "Ephemeral Prime"},
        headers=admin["csrf"],
    )
    assert same.status_code == 200, same.text


# ─── B12: shared skills must be matched by id ────────────────────────────────


async def test_shared_skills_are_reported_by_id_not_by_name(auth, seeded_refs, db):
    """B12. `match_out` rebuilds the shared-skill list by comparing *names*,
    because `MatchItem` drops the `shared_skill_ids` that `MatchResult` already
    computed.

    The duplicate is inserted straight into the database on purpose: that is
    exactly what the table looks like today, because `update_skill` lets an
    admin create a duplicate in the first place. Fixing B11 stops new
    duplicates but does nothing about existing ones, so this stays a real case.
    """
    viewer = await auth(display_name="By Id")
    candidate = await auth(display_name="Duplicate Names")

    original = await db.scalar(select(Skill).where(Skill.name == "Python"))
    assert original is not None

    clone = Skill(name="Python", category="Duplicate")
    db.add(clone)
    await db.commit()

    async def _hold(session, skill_ids: list[str]) -> None:
        response = await session["client"].patch(
            "/api/v1/users/me", json={"skill_ids": skill_ids}, headers=session["csrf"]
        )
        assert response.status_code == 200, response.text

    await _hold(viewer, [str(original.id)])
    await _hold(candidate, [str(original.id), str(clone.id)])

    page = (await viewer["client"].get("/api/v1/matches?limit=100")).json()
    entry = next(
        item for item in page["items"] if item["user"]["id"] == candidate["id"]
    )

    shared_ids = {skill["id"] for skill in entry["shared_skills"]}
    assert shared_ids == {str(original.id)}, (
        "the shared-skill list was matched by name, so a second skill that "
        f"happens to share a name was reported as shared: {entry['shared_skills']}"
    )

    # The reason text must not invent a second shared skill either.
    joined = " ".join(entry["reasons"])
    assert joined.count("Python") <= 1, f"the reason names Python twice: {entry['reasons']}"


# ─── B13: the interest in-use error code ─────────────────────────────────────


async def test_deleting_an_in_use_interest_reports_an_interest_error(auth, seeded_refs):
    """B13. `delete_interest` raises `code="skill_in_use"` — copy-pasted from
    `delete_skill` — so a client switching on the code takes the wrong branch.

    Expected value is `interest_in_use`, mirroring `skill_in_use`.
    """
    admin = await auth(is_admin=True)
    holder = await auth(display_name="Interest Holder")

    created = await admin["client"].post(
        "/api/v1/admin/interests", json={"name": "Bookbinding"}, headers=admin["csrf"]
    )
    assert created.status_code == 201, created.text

    held = await holder["client"].patch(
        "/api/v1/users/me",
        json={"interest_ids": [created.json()["id"]]},
        headers=holder["csrf"],
    )
    assert held.status_code == 200, held.text

    deleted = await admin["client"].delete(
        f"/api/v1/admin/interests/{created.json()['id']}", headers=admin["csrf"]
    )
    assert deleted.status_code == 409, deleted.text
    code = deleted.json()["error"]["code"]
    assert code == "interest_in_use", (
        f"deleting an in-use interest reported code={code!r}; the interest path "
        "reuses the skill path's code"
    )


async def test_deleting_an_in_use_skill_still_reports_the_skill_error(auth, seeded_refs):
    """The other half of B13: fixing the copy-paste must not break the original."""
    admin = await auth(is_admin=True)
    holder = await auth(display_name="Skill Holder")

    skills = (await holder["client"].get("/api/v1/skills")).json()
    held = skills[0]

    deleted = await admin["client"].delete(
        f"/api/v1/admin/skills/{held['id']}", headers=admin["csrf"]
    )
    assert deleted.status_code == 409, deleted.text
    assert deleted.json()["error"]["code"] == "skill_in_use"


# ─── B14: an unknown course_id is a 422, not a 500 ───────────────────────────


async def test_creating_an_idea_with_an_unknown_course_is_a_validation_error(
    auth, seeded_refs
):
    """B14. `project_ideas.course_id` is a foreign key, so a well-formed UUID
    naming no course is an unhandled IntegrityError -> 500. AGENTS.md §5 rule 5
    says every input is validated at the HTTP boundary.

    `profiles.update_profile` gets this right; the idea service does not.
    """
    author = await auth(display_name="Bad Course", role="business_developer")
    response = await author["client"].post(
        "/api/v1/ideas",
        json={
            "title": "An idea attached to nothing",
            "description": DESCRIPTION,
            "category": "build_product",
            "course_id": str(uuid.uuid4()),
        },
        headers=author["csrf"],
    )
    assert response.status_code == 422, (
        f"unknown course_id returned {response.status_code}: {response.text[:300]}"
    )
    assert response.json()["error"]["code"] == "validation_error"
    assert "course_id" in response.json()["error"].get("fields", {})


async def test_updating_an_idea_to_an_unknown_course_changes_nothing(
    auth, seeded_refs, db
):
    """B14, with the database read that makes it a real test: a 500 that
    happened to leave the row alone still fails here, and so does a 422 that
    changed the row."""
    author = await auth(display_name="Course Changer", role="business_developer")
    course = await db.scalar(select(Course).where(Course.name == "Software Development"))

    created = await author["client"].post(
        "/api/v1/ideas",
        json={
            "title": "Legitimately on a course",
            "description": DESCRIPTION,
            "category": "build_product",
            "course_id": str(course.id),
        },
        headers=author["csrf"],
    )
    assert created.status_code == 201, created.text

    response = await author["client"].patch(
        f"/api/v1/ideas/{created.json()['id']}",
        json={"course_id": str(uuid.uuid4())},
        headers=author["csrf"],
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "validation_error"

    stored = await db.get(ProjectIdea, uuid.UUID(created.json()["id"]))
    assert stored is not None and stored.course_id == course.id, (
        "the rejected update still changed the stored course"
    )


async def test_an_idea_with_no_course_is_still_accepted(auth, seeded_refs):
    """Guard: the B14 fix must not reject an omitted course."""
    author = await auth(display_name="Courseless", role="business_developer")
    response = await author["client"].post(
        "/api/v1/ideas",
        json={
            "title": "No course attached, which is allowed",
            "description": DESCRIPTION,
            "category": "build_product",
        },
        headers=author["csrf"],
    )
    assert response.status_code == 201, response.text
    assert response.json()["course"] is None


# ─── B9: the upload cap ──────────────────────────────────────────────────────


async def test_an_oversized_photo_is_rejected_and_stores_nothing(auth, seeded_refs, db):
    """B9. `upload_photo` does `await file.read()` — the entire body — and only
    then checks `max_photo_bytes`. The row assertion is the point."""
    user = await auth(display_name="Oversized")

    over_cap = b"\x89PNG\r\n\x1a\n" + b"\x00" * (3 * 1024 * 1024)
    response = await user["client"].post(
        "/api/v1/users/me/photo",
        files={"file": ("big.png", over_cap, "image/png")},
        headers=user["csrf"],
    )
    assert response.status_code == 413, (
        f"a 3 MB upload returned {response.status_code}: {response.text[:300]}"
    )
    assert response.json()["error"]["code"] == "file_too_large"

    stored = await db.scalar(
        select(func.count())
        .select_from(Photo)
        .where(Photo.user_id == uuid.UUID(user["id"]))
    )
    assert stored == 0, f"a rejected upload left {stored} row(s) in photos"


async def test_a_rejected_upload_does_not_destroy_the_existing_photo(
    auth, seeded_refs, db
):
    """The stronger half of B9. `save_photo` checks the size before deleting the
    old row, so a rejected upload must leave the current avatar byte-identical.
    """
    user = await auth(display_name="Careful Uploader")
    good = base64.b64decode(PNG_1X1)

    first = await user["client"].post(
        "/api/v1/users/me/photo",
        files={"file": ("avatar.png", good, "image/png")},
        headers=user["csrf"],
    )
    assert first.status_code == 200, first.text

    over_cap = b"\x89PNG\r\n\x1a\n" + b"\x00" * (3 * 1024 * 1024)
    rejected = await user["client"].post(
        "/api/v1/users/me/photo",
        files={"file": ("big.png", over_cap, "image/png")},
        headers=user["csrf"],
    )
    assert rejected.status_code == 413

    stored = await db.scalar(select(Photo).where(Photo.user_id == uuid.UUID(user["id"])))
    assert stored is not None, "the rejected upload deleted the existing photo"
    assert stored.byte_size == len(good)
    assert bytes(stored.data) == good, "the stored photo bytes changed"

    served = await user["client"].get("/api/v1/users/me/photo")
    assert served.status_code == 200
    assert served.content == good


async def test_an_accepted_photo_records_its_exact_byte_count(auth, seeded_refs, db):
    """Round trip: the size in the database must equal the size that was sent."""
    user = await auth(display_name="Exact Bytes")
    payload = base64.b64decode(PNG_1X1)

    response = await user["client"].post(
        "/api/v1/users/me/photo",
        files={"file": ("avatar.png", payload, "image/png")},
        headers=user["csrf"],
    )
    assert response.status_code == 200, response.text

    stored = await db.scalar(select(Photo).where(Photo.user_id == uuid.UUID(user["id"])))
    assert stored is not None
    assert stored.byte_size == len(payload)
    assert stored.content_type == "image/png"


async def test_a_disguised_non_image_is_rejected(auth, seeded_refs, db):
    """The other half of rule 5 on this endpoint: bytes, not the declared type.

    Cheap here because it belongs next to the size tests, which are the ones
    that got the review's attention.
    """
    user = await auth(display_name="Disguised")

    response = await user["client"].post(
        "/api/v1/users/me/photo",
        files={"file": ("evil.png", b"#!/bin/sh\nrm -rf /\n", "image/png")},
        headers=user["csrf"],
    )
    assert response.status_code == 415, response.text
    assert response.json()["error"]["code"] == "unsupported_media_type"

    stored = await db.scalar(
        select(func.count())
        .select_from(Photo)
        .where(Photo.user_id == uuid.UUID(user["id"]))
    )
    assert stored == 0


# ─── B10: the dev video route ────────────────────────────────────────────────


@pytest.fixture
def dev_app(tmp_path, monkeypatch):
    """The dev router on its own app, pointed at a temporary videos directory.

    The router is only mounted when APP_ENV=development and the suite runs as
    APP_ENV=test, so mounting it here is what makes the route reachable at all.
    `_VIDEOS_DIR` is resolved at import time, so it is patched on the module.

    The app's real exception handlers are registered, so the error-shape
    assertion below holds whichever way the route is fixed — raising `NotFound`
    or returning the envelope by hand.
    """
    import app.dev as dev_module

    videos = tmp_path / "videos"
    videos.mkdir()
    monkeypatch.setattr(dev_module, "_VIDEOS_DIR", videos)

    application = FastAPI()
    application.add_exception_handler(AppError, app_error_handler)
    application.add_exception_handler(HTTPException, http_error_handler)
    application.include_router(dev_module.router)
    return application, videos


# `..\\secret.txt` is the payload that matters: Starlette's path converter
# excludes `/` but not `\`, and Windows treats `\` as a separator.
TRAVERSALS = [
    "../secret.txt",
    "..%2fsecret.txt",
    "..%2Fsecret.txt",
    "%2e%2e%2fsecret.txt",
    "....//secret.txt",
    "..\\secret.txt",
    "..\\..\\secret.txt",
    "subdir/../../secret.txt",
    "..",
]


async def test_dev_video_route_never_serves_a_file_outside_the_directory(dev_app):
    """B10, first half. The handler's only check is `.exists()` on an
    un-resolved join, and its comment claims that prevents traversal.

    This is a regression guard rather than a live failure on Linux, where
    Starlette rejects `/` in a path segment before the handler runs. On Windows
    the backslash payloads reach the handler and do traverse. The positive
    control proves the route still works, so a fix cannot pass by breaking it.
    """
    from httpx import ASGITransport, AsyncClient

    application, videos = dev_app
    secret = videos.parent / "secret.txt"
    secret.write_text("TOP SECRET MARKER VALUE", encoding="utf-8")
    (videos / "evidence.mp4").write_bytes(b"not-really-a-video")

    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://dev") as http:
        good = await http.get("/api/v1/dev/videos/evidence.mp4")
        assert good.status_code == 200, good.text
        assert good.content == b"not-really-a-video"

        for payload in TRAVERSALS:
            response = await http.get(f"/api/v1/dev/videos/{payload}")
            assert response.status_code != 200, (
                f"{payload!r} returned 200 — the route served a file from outside "
                "the videos directory"
            )
            assert b"TOP SECRET MARKER VALUE" not in response.content, (
                f"{payload!r} leaked the contents of a file outside the videos directory"
            )


async def test_dev_video_route_uses_the_standard_error_envelope(dev_app):
    """B10, second half. The handler returns `{"error": "not_found"}, 404`,
    which breaks specs/00_conventions.md §2: every error is
    `{"error": {"code", "message"}}`.
    """
    from httpx import ASGITransport, AsyncClient

    application, _videos = dev_app
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://dev") as http:
        response = await http.get("/api/v1/dev/videos/definitely-missing.mp4")

    assert response.status_code == 404
    body = response.json()
    assert isinstance(body.get("error"), dict), (
        f"the error envelope is a bare string: {body} — specs/00_conventions.md "
        "§2 requires {error: {code, message}}"
    )
    assert body["error"]["code"] == "not_found"
    assert isinstance(body["error"]["message"], str) and body["error"]["message"]


async def test_dev_video_listing_stays_inside_the_directory(dev_app):
    """The sibling route: it must list only what is actually in the directory."""
    from httpx import ASGITransport, AsyncClient

    application, videos = dev_app
    (videos / "one.mp4").write_bytes(b"x")
    (videos / "notes.txt").write_bytes(b"x")
    (videos.parent / "outside.mp4").write_bytes(b"x")

    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://dev") as http:
        body = (await http.get("/api/v1/dev/videos")).json()

    assert body["videos"] == ["one.mp4"], body
    assert "notes.txt" not in body["videos"], "the listing is not restricted to .mp4"


# ─── B17: an idea detail request must not sweep its category ────────────────


async def test_idea_detail_is_correct_past_the_detail_sweep_window(
    auth, seeded_refs, db
):
    """B17. `get_idea` re-derives interest counts by calling
    `list_ideas(categories=[idea.category], limit=200)` and searching the
    result. Past 201 ideas in one category the idea being asked about is not in
    that window, the search silently fails, and the response falls back to "no
    interests, you have not expressed interest" while the board shows the real
    numbers.

    The rows go in directly with controlled `created_at`, so which idea falls off
    the end of the window is deterministic rather than timing-dependent.
    """
    author = await auth(display_name="Prolific Author", role="business_developer")
    viewer = await auth(display_name="Interested Viewer")

    # `limit=200` in the handler means the window is the newest 201.
    base = datetime(2020, 1, 1, tzinfo=UTC)
    rows = [
        ProjectIdea(
            author_id=author.id,
            title=f"Bulk proposal {index}",
            description=DESCRIPTION,
            category="build_product",
            skills_needed=[],
            created_at=base + timedelta(minutes=index),
        )
        for index in range(205)
    ]
    db.add_all(rows)
    await db.commit()

    oldest = min(rows, key=lambda idea: idea.created_at)
    assert oldest is not None

    expressed = await viewer["client"].post(
        f"/api/v1/ideas/{oldest.id}/interest", headers=viewer["csrf"]
    )
    assert expressed.status_code == 200, expressed.text

    detail = await viewer["client"].get(f"/api/v1/ideas/{oldest.id}")
    assert detail.status_code == 200, detail.text
    body = detail.json()

    assert body["viewer_has_interested"] is True, (
        "the detail page says the viewer has not expressed interest, while the "
        "interest row exists — the detail route swept only the newest 201 ideas "
        "in the category and did not find this one"
    )
    assert body["interest_count"] == 1, (
        f"detail reports interest_count={body['interest_count']}, expected 1"
    )

    # And the board must agree with the detail page about the same idea.
    board = (
        await viewer["client"].get("/api/v1/ideas?limit=50&search=Bulk proposal 0")
    ).json()
    listed = [item for item in board["items"] if item["id"] == str(oldest.id)]
    assert listed, "the idea is missing from the board entirely"
    assert listed[0]["interest_count"] == body["interest_count"], (
        "the board and the detail page disagree about the same idea"
    )
    assert listed[0]["viewer_has_interested"] == body["viewer_has_interested"]


# ─── B18: list endpoints must not scale with the row count ──────────────────


async def test_connection_list_query_count_is_bounded_by_the_page(
    auth, seeded_refs, engine
):
    """B18. `list_connections` calls `_other` and `_thread_id` per row — two
    queries each — so a 20-row page costs roughly sixty statements.

    Counts real SQL through a SQLAlchemy event listener, so no response body
    can influence it. The bound is generous enough to cover session loading and
    the profile eager-loads, and still far below two-per-row plus overhead.
    """
    viewer = await auth(display_name="Query Budget")
    for index in range(20):
        await _connect(viewer, await auth(display_name=f"Query Partner {index}"))

    with count_statements(engine) as statements:
        response = await viewer["client"].get("/api/v1/connections?limit=20")

    assert response.status_code == 200, response.text
    assert len(response.json()["items"]) == 20

    assert len(statements) < 30, (
        f"/connections issued {len(statements)} SQL statements for 20 rows. The "
        "per-row lookups make this O(rows): batch them or join them."
    )


async def test_matches_query_count_is_bounded_by_the_page(auth, seeded_refs, engine):
    """B18. `rank_for_viewer` awaits `connection_state` once per returned row,
    so the query count grows with `limit`."""
    viewer = await auth(display_name="Match Budget")
    for index in range(20):
        await auth(display_name=f"Budget Candidate {index}")

    with count_statements(engine) as statements:
        response = await viewer["client"].get("/api/v1/matches?limit=20")

    assert response.status_code == 200, response.text
    assert len(response.json()["items"]) == 20

    assert len(statements) < 20, (
        f"/matches issued {len(statements)} SQL statements for 20 rows. "
        "`connection_state` is awaited per row; fetch the states in one query."
    )


async def test_raising_the_page_size_does_not_raise_the_query_count(
    auth, seeded_refs, engine
):
    """The shape of the bug rather than its presence. A correct implementation
    has a constant query count, so quadrupling the page size changes nothing.
    A per-row lookup cannot pass this whatever the constants are."""

    async def measure(session, limit: int) -> int:
        with count_statements(engine) as statements:
            await session["client"].get(f"/api/v1/connections?limit={limit}")
        return len(statements)

    viewer = await auth(display_name="Scaling Budget")
    for index in range(10):
        await _connect(viewer, await auth(display_name=f"Scaling Partner {index}"))

    small = await measure(viewer, 2)
    large = await measure(viewer, 10)

    assert large <= small + 2, (
        f"query count grew with the page size: {small} statements for 2 rows vs "
        f"{large} for 10. A list endpoint must be O(1) in queries, not O(rows)."
    )


# ─── Client input never becomes a 500 ────────────────────────────────────────


async def test_no_endpoint_answers_5xx_for_bad_client_input(auth, seeded_refs):
    """A sweep, because a 500 on a demo screen is worse than a 422 and the
    failure only appears when someone types the wrong thing."""
    user = await auth(display_name="Fuzzer", role="business_developer")
    admin = await auth(is_admin=True)

    # Real collisions, so the rename cases are the ones that matter.
    skill_kept = await admin["client"].post(
        "/api/v1/admin/skills", json={"name": "Sweep Alpha"}, headers=admin["csrf"]
    )
    skill_moved = await admin["client"].post(
        "/api/v1/admin/skills", json={"name": "Sweep Beta"}, headers=admin["csrf"]
    )
    course_kept = await admin["client"].post(
        "/api/v1/admin/courses", json={"name": "Sweep Course A"}, headers=admin["csrf"]
    )
    course_moved = await admin["client"].post(
        "/api/v1/admin/courses", json={"name": "Sweep Course B"}, headers=admin["csrf"]
    )
    assert skill_kept.status_code == 201 and skill_moved.status_code == 201
    assert course_kept.status_code == 201 and course_moved.status_code == 201

    interest = await admin["client"].post(
        "/api/v1/admin/interests", json={"name": "Sweep Interest"}, headers=admin["csrf"]
    )
    assert interest.status_code == 201

    idea = await user["client"].post(
        "/api/v1/ideas",
        json={"title": "Sweep fixture", "description": DESCRIPTION, "category": "build_product"},
        headers=user["csrf"],
    )
    assert idea.status_code == 201, idea.text

    missing = "00000000-0000-0000-0000-000000000000"
    cases = [
        ("POST", "/api/v1/connections", {"receiver_id": str(uuid.uuid4())}, user),
        ("POST", "/api/v1/connections", {"receiver_id": "not-a-uuid"}, user),
        ("POST", "/api/v1/connections", {}, user),
        ("PATCH", f"/api/v1/connections/{missing}", {"action": "accept"}, user),
        ("PATCH", f"/api/v1/connections/{missing}", {"action": "explode"}, user),
        ("POST", f"/api/v1/connections/{missing}/thread", None, user),
        ("PATCH", "/api/v1/users/me", {"role": "wizard"}, user),
        ("PATCH", "/api/v1/users/me", {"course_id": str(uuid.uuid4())}, user),
        ("PATCH", "/api/v1/users/me", {"skill_ids": [str(uuid.uuid4())]}, user),
        ("PATCH", "/api/v1/users/me", {"bio": "x" * 5000}, user),
        (
            "POST",
            "/api/v1/ideas",
            {"title": "", "description": "x", "category": "nope", "course_id": str(uuid.uuid4())},
            user,
        ),
        ("PATCH", f"/api/v1/ideas/{idea.json()['id']}", {"course_id": str(uuid.uuid4())}, user),
        ("PATCH", f"/api/v1/ideas/{missing}", {"title": "nope"}, user),
        (
            "PATCH",
            f"/api/v1/admin/skills/{skill_moved.json()['id']}",
            {"name": "Sweep Alpha"},
            admin,
        ),
        (
            "PATCH",
            f"/api/v1/admin/interests/{interest.json()['id']}",
            {"name": "Sweep Alpha"},
            admin,
        ),
        (
            "PATCH",
            f"/api/v1/admin/courses/{course_moved.json()['id']}",
            {"name": "Sweep Course A"},
            admin,
        ),
        ("DELETE", f"/api/v1/admin/skills/{missing}", None, admin),
        ("POST", "/api/v1/auth/login", {"email": "nope", "password": ""}, user),
        ("POST", "/api/v1/auth/magic-link", {"email": "nope"}, user),
        ("PATCH", f"/api/v1/notifications/{missing}", {"read": True}, user),
        ("POST", f"/api/v1/ideas/{missing}/interest", None, user),
    ]

    for method, path, body, session in cases:
        response = await session["client"].request(
            method, path, json=body, headers=session["csrf"]
        )
        assert response.status_code < 500, (
            f"{method} {path} returned {response.status_code}: {response.text[:300]}"
        )
        if response.status_code >= 400:
            error = response.json().get("error")
            assert isinstance(error, dict), f"{method} {path}: {response.text[:300]}"
            assert error.get("code"), response.text[:300]
            assert error.get("message"), response.text[:300]