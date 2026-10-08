"""The pagination contract, applied generically to every list endpoint.

Added 8 October 2026 with the §12 review, before the fix, to expose **B1**:
`/matches` cursor pagination always returns an empty page 2+.

Why this file is generic rather than a one-off for `/matches`: every other list
family already had *some* cursor test and `/matches` still shipped broken.
`test_malformed_list_cursor_returns_client_error` includes `/matches`, which is
exactly why it looked covered — a garbage cursor fails to **decode** and raises
before the comparison bug is reached. No test sent `/matches` a *valid* cursor,
and `MatchesPage` never sends one either. One list family had no coverage, and
that family had the bug.

The contract, for every list family:

  1. Paging with a small `limit` reaches every row.
  2. No row appears on two pages.
  3. The paged order equals the unpaged (`limit=100`) order.
  4. The last page reports `next_cursor is None`.
  5. The page count equals the row count, so a page is never silently short.

Anti-hardcoding: expected values are *derived*, never literals. Nothing here
asserts "4 rows" as a fact about the response — it asserts the paged walk agrees
with the same endpoint called with `limit=100`, and the tied-score test
additionally compares against the set of user rows the test itself inserted. A
response returning plausible hardcoded rows cannot agree with both.

specs/00_conventions.md §5.
"""

from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.anyio

# Rows created per family. More than one, because a family with a single row
# cannot distinguish "paged correctly" from "returned everything".
ROWS = 4

# Every list endpoint in the app. If you add one, add it here — that is the
# entire point of this file.
FAMILIES = [
    "connections",
    "threads",
    "notifications",
    "ideas",
    "matches",
    "admin/users",
    "admin/audit",
    "admin/skills",
    "admin/courses",
    "admin/interests",
]

DESCRIPTION = (
    "A routing service that weights emissions per stop rather than total "
    "distance, so a courier running three short hops is not treated as the "
    "same as one long motorway leg. Two regional firms said they would pay."
)


# ─── The walk ────────────────────────────────────────────────────────────────


async def walk(client, path: str, limit: int = 1) -> tuple[list[str], int]:
    """Page `path` until next_cursor is None. Returns (ids, page_count).

    A hard page ceiling: a cursor that never terminates is a bug, and the
    ceiling turns that into a readable assertion failure instead of a hung
    test run.
    """
    ids: list[str] = []
    cursor: str | None = None
    pages = 0
    while True:
        query = f"?limit={limit}" + (f"&cursor={cursor}" if cursor else "")
        response = await client.get(f"{path}{query}")
        assert response.status_code == 200, f"{path}{query} -> {response.status_code}: {response.text}"
        body = response.json()
        ids.extend(item["id"] for item in body["items"])
        pages += 1
        cursor = body.get("next_cursor")
        if cursor is None:
            return ids, pages
        assert pages < 200, f"{path} pagination did not terminate"


# ─── Per-family seeding ──────────────────────────────────────────────────────


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


async def _seed(auth, family: str, count: int = ROWS):
    """Create `count` rows in `family`. Returns (session, path)."""
    if family == "connections":
        viewer = await auth(display_name="Pager")
        for index in range(count):
            peer = await auth(display_name=f"Peer{index}")
            await _connect(viewer, peer)
        return viewer, "/api/v1/connections"

    if family == "threads":
        viewer = await auth(display_name="Threader")
        for index in range(count):
            peer = await auth(display_name=f"ThreadPeer{index}")
            cid = await _connect(viewer, peer)
            await _open_thread(viewer, cid)
        return viewer, "/api/v1/threads"

    if family == "notifications":
        # Each peer sends a request to the viewer, so the viewer receives one
        # notification per peer.
        viewer = await auth(display_name="Inbox")
        for index in range(count):
            peer = await auth(display_name=f"Admirer{index}")
            await _connect(peer, viewer)
        return viewer, "/api/v1/notifications"

    if family == "ideas":
        author = await auth(display_name="Idealist", role="business_developer")
        for index in range(count):
            response = await author["client"].post(
                "/api/v1/ideas",
                json={
                    "title": f"Emissions-aware routing proposal {index}",
                    "description": DESCRIPTION,
                    "category": "build_product",
                },
                headers=author["csrf"],
            )
            assert response.status_code == 201, response.text
        return author, "/api/v1/ideas"

    if family == "matches":
        # Every user gets the identical default profile, so every candidate
        # scores the same. Only the candidate id separates them, which is
        # precisely the tiebreaker cursor pagination depends on.
        viewer = await auth(display_name="Matcher")
        for index in range(count):
            await auth(display_name=f"Candidate{index}")
        return viewer, "/api/v1/matches"

    if family.startswith("admin/"):
        admin = await auth(is_admin=True, display_name="The Admin")
        kind = family.split("/", 1)[1]
        if kind == "users":
            for index in range(count):
                await auth(display_name=f"Listed{index}")
        elif kind == "audit":
            # Each successful create writes exactly one audit row.
            for index in range(count):
                response = await admin["client"].post(
                    "/api/v1/admin/skills",
                    json={"name": f"Skill{index}"},
                    headers=admin["csrf"],
                )
                assert response.status_code == 201, response.text
        else:
            for index in range(count):
                response = await admin["client"].post(
                    f"/api/v1/admin/{kind}",
                    json={"name": f"{kind.title()} {index}"},
                    headers=admin["csrf"],
                )
                assert response.status_code == 201, response.text
        return admin, f"/api/v1/admin/{kind}"

    raise AssertionError(f"no seeding defined for {family}")


# ─── The contract ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("family", FAMILIES)
async def test_every_list_family_pages_to_exhaustion_without_repeats(
    auth, seeded_refs, family
):
    """The whole contract, in one parameterised sweep."""
    session, path = await _seed(auth, family)

    # The unpaged answer is the reference. limit=100 is the documented cap.
    everything = await session["client"].get(f"{path}?limit=100")
    assert everything.status_code == 200, everything.text
    full = everything.json()
    assert full["next_cursor"] is None, f"{path} advertised another page at limit=100"

    # Seeding sanity, not an exact count: admin families also carry seeded
    # reference rows, and pinning those numbers would break whenever seed.py
    # changes. The point is only that there is more than one row to page.
    assert len(full["items"]) >= ROWS, (
        f"{path} returned {len(full['items'])} rows, fewer than the {ROWS} this "
        "test created — the seeding is wrong, so pagination is not being measured"
    )

    walked, pages = await walk(session["client"], path, limit=1)

    assert len(set(walked)) == len(walked), (
        f"{path} repeated a row across pages: "
        f"{len(walked) - len(set(walked))} duplicate(s)"
    )
    assert walked == [item["id"] for item in full["items"]], (
        f"{path} paged order differs from the unpaged order — rows were skipped "
        f"or reordered (walked {len(walked)} of {len(full['items'])})"
    )
    assert pages == len(full["items"]), (
        f"{path} took {pages} pages for {len(full['items'])} rows at limit=1"
    )


@pytest.mark.parametrize("family", FAMILIES)
async def test_every_list_family_accepts_its_own_valid_cursor(auth, seeded_refs, family):
    """A valid cursor must be accepted, not just a malformed one rejected.

    The existing `test_malformed_list_cursor_returns_client_error` includes
    `/matches` and passes while `/matches` is broken, because a garbage cursor
    fails to *decode*. This closes that gap by round-tripping a real one.
    """
    session, path = await _seed(auth, family)

    first = (await session["client"].get(f"{path}?limit=1")).json()
    cursor = first.get("next_cursor")
    assert cursor, f"{path} produced no cursor with more than one row and limit=1"

    second = await session["client"].get(f"{path}?limit=1&cursor={cursor}")
    assert second.status_code == 200, second.text
    items = second.json()["items"]
    assert len(items) == 1, (
        f"{path} returned {len(items)} rows on page 2, expected 1 — the cursor "
        "filtered out everything, which is the B1 failure mode"
    )
    assert items[0]["id"] not in {item["id"] for item in first["items"]}


async def test_matches_pages_tied_scores_without_skipping_anyone(auth, seeded_refs):
    """B1, named directly.

    Every candidate has an identical profile, so every score ties and the
    `(score, user_id)` tiebreaker is the only thing ordering them. The encoder
    writes the **positive** score; the comparator compares against `sort_key`,
    which **negates** it. Nothing ever sorts after the cursor, so page 2 is
    empty.

    The expected set is the set of user rows this test inserted, so a response
    with hardcoded plausible-looking rows still fails.
    """
    from app.services.match_service import decode_cursor, encode_cursor
    from app.services.matching import sort_key

    viewer = await auth(display_name="TieBreaker")
    created = [await auth(display_name=f"Tied{index}") for index in range(6)]

    everything = (await viewer["client"].get("/api/v1/matches?limit=100")).json()

    # Prove the precondition rather than assuming it. If these ever stop tying,
    # the tiebreaker is no longer what is under test and everything below
    # becomes vacuous.
    assert len(everything["items"]) == len(created), (
        f"expected {len(created)} candidates, got {len(everything['items'])}"
    )
    assert len({item["score"] for item in everything["items"]}) == 1, (
        "candidates did not score equally, so this test no longer exercises the "
        "score tiebreaker"
    )

    # 1. End to end through HTTP: paging must reach every tied candidate.
    walked, _pages = await walk(viewer["client"], "/api/v1/matches", limit=2)
    expected = {user.id for user in created}
    assert set(walked) == expected, (
        f"paging returned {len(walked)} of {len(expected)} candidates — cursor "
        "pagination dropped the rest"
    )

    # 2. The encoder and the comparator, directly, so the failure message names
    #    the sign error instead of only reporting a count. Cut in the middle so
    #    there is provably something on each side.
    ordered = sorted(
        everything["items"],
        key=lambda item: sort_key(item["score"], uuid.UUID(item["user"]["id"])),
    )
    cut = ordered[len(ordered) // 2]
    cursor = encode_cursor(cut["score"], uuid.UUID(cut["user"]["id"]))
    after_score, after_id = decode_cursor(cursor)

    later = [
        item
        for item in ordered
        if sort_key(item["score"], uuid.UUID(item["user"]["id"])) > (after_score, after_id)
    ]
    assert later, (
        f"no candidate sorts after its own cursor: the encoder stored "
        f"score={after_score} but sort_key returns a negated score, so "
        "(-score, id) can never exceed (score, id) and every subsequent page "
        "is empty"
    )


async def test_matches_reports_no_cursor_when_the_page_is_the_whole_set(auth, seeded_refs):
    """B15: `has_more = len(items) == limit` advertises a page that cannot exist.

    Every other list endpoint tests `len(rows) > limit` *before* slicing. This
    one slices first and compares the slice length, so a result set that fits
    the page exactly is misreported as having more.
    """
    viewer = await auth(display_name="ExactPage")
    for index in range(3):
        await auth(display_name=f"WholeSet{index}")

    body = (await viewer["client"].get("/api/v1/matches?limit=3")).json()
    assert len(body["items"]) == 3, body
    assert body["next_cursor"] is None, (
        "exactly `limit` rows exist and the response still advertised another "
        "page, which sends the client one guaranteed-empty request"
    )


async def test_matches_has_no_cursor_when_nothing_matches(auth, seeded_refs):
    """The degenerate end of the same rule."""
    viewer = await auth(display_name="Nobody")
    body = (await viewer["client"].get("/api/v1/matches")).json()
    assert body["items"] == []
    assert body["next_cursor"] is None


async def test_continuing_from_a_cursor_does_not_repeat_when_the_set_grows(auth, seeded_refs):
    """The reason keyset is used instead of offset (specs/00_conventions.md §5):
    offsets skip and repeat when the underlying set shifts, which is exactly
    what happens when someone posts during the demo.

    A row created after page 1 is the newest, so it sorts *ahead* of the
    cursor and must never appear on a continuation.
    """
    author = await auth(display_name="Shifty", role="business_developer")

    def idea(title: str) -> dict:
        return {"title": title, "description": DESCRIPTION, "category": "build_product"}

    for index in range(3):
        response = await author["client"].post(
            "/api/v1/ideas", json=idea(f"Original proposal {index}"), headers=author["csrf"]
        )
        assert response.status_code == 201, response.text

    page1 = (await author["client"].get("/api/v1/ideas?limit=1")).json()
    assert page1["next_cursor"], "expected more than one idea"
    seen = [item["id"] for item in page1["items"]]

    newcomer = await author["client"].post(
        "/api/v1/ideas", json=idea("Posted mid-scroll"), headers=author["csrf"]
    )
    assert newcomer.status_code == 201, newcomer.text
    newcomer_id = newcomer.json()["id"]

    cursor = page1["next_cursor"]
    while cursor:
        body = (await author["client"].get(f"/api/v1/ideas?limit=1&cursor={cursor}")).json()
        seen.extend(item["id"] for item in body["items"])
        cursor = body.get("next_cursor")
        assert len(seen) < 50, "cursor did not terminate after the set grew"

    assert len(set(seen)) == len(seen), f"repeated a row after the set grew: {seen}"
    assert newcomer_id not in seen, (
        "a row created after page 1 turned up on a later page — the cursor is "
        "not ordering by created_at"
    )
    assert len(seen) == 3, f"expected the three original ideas, walked {len(seen)}"


async def test_paging_reference_data_drops_nothing_a_profile_uses(auth, seeded_refs):
    """A skill missing from a page silently changes every match score in the
    cohort. That is the exact hazard `admin.delete_skill` guards against in a
    comment, and it must not be reachable by paging instead.
    """
    admin = await auth(is_admin=True, display_name="Counter")
    for index in range(ROWS):
        await admin["client"].post(
            "/api/v1/admin/skills", json={"name": f"Paged {index}"}, headers=admin["csrf"]
        )

    walked, _pages = await walk(admin["client"], "/api/v1/admin/skills", limit=1)

    public = (await admin["client"].get("/api/v1/skills")).json()
    assert set(walked) == {skill["id"] for skill in public}, (
        "the admin reference list and the public skills list disagree — paging "
        "the admin list loses skills that profiles can hold"
    )