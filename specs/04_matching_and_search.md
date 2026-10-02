# 04 — Matching and search

**Goal:** given two profiles, produce a ranked, explainable list of people
worth talking to. The reason string is as important as the ordering — a list
without explanations is a list nobody trusts.

**Depends on:** [03 — Profiles](03_profiles.md)
**Blocks:** [05 — Connection requests](05_connection_requests.md),
[01 — Home feed](01_landing_page.md)

**Implementation status:** Implemented 2 Oct 2026 — see the *As built* note at the end of this document for deviations from the spec.

---

## 1. Scope

| In | Out |
|---|---|
| Ranked matches by weighted overlap | Embeddings, vector search, semantic similarity |
| Filters: skill, role, course, interest | Free-text bio search |
| Plain-English `reason` per match | Free-text search across profiles |
| Deterministic ordering | Real-time re-ranking |
| Course-mates only | Filtering across courses |

### Why this is plain code and not an AI model

The brief lists AI-assisted matching as a *suggested* feature. We ship
deterministic scoring in the demo and spec AI separately:
[`deferred_ai_icebreakers.md`](deferred_ai_icebreakers.md).
Rationale: [`decisions/0009-deterministic-matching-first.md`](../decisions/0009-deterministic-matching-first.md).

One paragraph, because it comes up every time: a model ranking people is a
non-deterministic function with an API bill sitting in the request path, and
there is no way to write a unit test that asserts a specific person comes
first. Weighted overlap over four signals is one pure function, about forty
lines, free, instant, and returns a score plus the contributing factors — which
is exactly what the `reason` field needs. The AI version becomes reasonable the
moment there is a real corpus to learn from, and by then there is a test corpus
too. Decision recorded; move on.

## 2. Signals and weights

Four signals. All computable with a join; no external calls.

| Signal | Points | Rationale |
|---|---|---|
| **Complementary role** | **30** | The core premise: software developer ↔ business developer. One dev + one business dev = 30. Same role = 0. |
| **Shared skills** | **10 per skill, max 30** | Three overlapping skills is a strong signal. Capped so a person with 20 skills cannot dominate. |
| **Shared interests** | **5 per interest, max 15** | A weaker signal. Three shared interests is meaningful. |
| **Same course** | **20** | A cohort is a bounded, natural community. |

**Range: 0 to 95.**

### Complementary role scores 30. Same role scores 0

This is the highest-weighted signal and the reason the app exists. A developer
and a business developer with one shared skill score 40; two developers with
three shared skills score 30. The cross-side pairing wins, which is the product
working as intended.

**Same-role pairs are not excluded.** Just scored lower. The brief says
"connection" could be a collaboration, a partnership, or a friendship — a
pair of developers who both know Django is a legitimate match. Blocking
same-role would be inventing a rule the PRD explicitly rejected.

### Cap the per-skill and per-interest points

Without a cap, one user listing 20 skills could out-score a genuine
complementary match purely on volume. Capping makes the score measure
*depth of overlap*, not list length. Both caps matter and both are unit-tested.

### Weights are a named constant, not magic numbers

```python
# services/matching.py
WEIGHTS = MatchingWeights(
    complementary_role=30,
    shared_skill=10, max_shared_skill_points=30,
    shared_interest=5, max_shared_interest_points=15,
    same_course=20,
)
```

A reviewer can change a weight and see the effect in the unit tests. Inlined
literals in a comprehension is how a scoring function becomes unexplainable.

**One number, one place.** Document it in `PRD.md` and here. If someone asks
"why is this person first", the answer is this table.

## 3. The scoring function

A **pure function**. No database, no session, no clock. This is what makes it
testable.

```python
def score_match(viewer: ProfileView, candidate: ProfileView) -> MatchResult:
    """Deterministic. Same inputs, same output, always.

    MatchResult: score, reasons[], shared_skill_ids[], shared_interest_ids[]
    """
```

`ProfileView` is a flattened, pre-fetched projection — role, course, skill ids,
interest ids, name. Deliberately not a SQLAlchemy model: taking ORM objects
would make the function untestable without a database and couple it to the
schema.

### Steps

1. **Roles** — `+30` if roles differ and both are set, else `0`.
2. **Skills** — intersect the id sets, `+10` each, capped at `30`.
3. **Interests** — intersect, `+5` each, capped at `15`.
4. **Course** — `+20` if both are set and equal.
5. **Reasons** — build the strings, strongest contribution first.

### Reasons

Human-readable, and built from the factors that actually contributed. No
phrases that are not earned.

| Trigger | `reason` |
|---|---|
| Roles differ | `"You're both developers — Sam builds, you find the customers."` |
| Same course | `"Both on Software Development."` |
| ≥1 shared skill | `"You both know Python, React."` |
| ≥1 shared interest | `"Both interested in Climate tech."` |
| Only a score | `"Someone with skills that complement yours."` |

Render reasons as a list of strings, ordered by contribution descending, and
show the top two on a card. Putting the strings in the API rather than
assembling them in the frontend means the wording is testable and identical
everywhere a match appears — home feed, match list, notification email.

### Determinism

Same profiles and data always produce the same order. Ties break on
`candidate.id` ascending. A stable total order is what makes cursor pagination
correct ([`00_conventions.md`](00_conventions.md) §5) — a fuzzy tiebreak would
let page 2 repeat rows from page 1.

## 4. The profile-completeness gate

**`AGENTS.md` §5 rule 3.** If the viewer's `profile_complete` is `false`:

```
GET /api/v1/matches → 403
{ "error": { "code": "profile_incomplete",
             "message": "Choose a role and add at least one skill before browsing matches." } }
```

**Never return partial results.** An empty list would be indistinguishable from
"nobody to show you", and the user would sit there wondering. A `403` with an
actionable message tells them exactly what to do.

The check is in the service, not the router, so it cannot be bypassed by hitting
a different route. The home feed avoids making the request at all while
incomplete ([01](01_landing_page.md) §4) — that is a courtesy, not the
enforcement.

Candidates are **not** filtered on `profile_complete`. Someone with no bio and
one skill is still a legitimate match; requiring a rich profile to appear would
hide most of the cohort early on.

## 5. Exclusions

The viewer's own id and anyone already connected. Direction-agnostic.

| Excluded | Why |
|---|---|
| **Self** | You are not a match with yourself. |
| **Accepted connections** | Already connected; the UI shows the conversation instead. |
| **Pending requests, either direction** | Already asked or already asked you. The UI shows the pending state. |
| **Declined connections** | They said no. Re-suggesting them is ignoring an answer. |
| **Deactivated users** | `is_active = false` |

**Pending in both directions.** If Alice asked Bob, Bob's list must not contain
Alice as a suggestion — he already knows, and the card would say "Connect" on
someone he is waiting to hear back from. This is the most commonly missed
exclusion.

Check it in one SQL `NOT EXISTS` against `connections` covering all three states,
in both directions. Do not fetch candidates and filter in Python — with a large
cohort that is the whole table.

## 6. Endpoints

### `GET /api/v1/matches`

The ranked list. Auth required. Completeness gate applies (§4).

| Param | Type | Notes |
|---|---|---|
| `limit` | int | Default 20, max 100 |
| `cursor` | string | Opaque |
| `skill` | string | Skill **name**, repeatable |
| `role` | enum | `software_developer` \| `business_developer` |
| `course_id` | uuid | |
| `interest` | string | Interest **name**, repeatable |
| `exclude_connected` | bool | Default `true`. `false` returns connected people too, used by `/connections` |

Filters are **AND-combined**: `?skill=python&role=business_developer` returns
only people matching both. Repeated params are OR within a filter
(`?skill=python&skill=react` = either), AND between filters. The standard shape.

**Filters narrow the candidate set; scoring ranks within it.** Never score first
and filter after — that produces a short list and a broken total count.

```jsonc
// 200
{
  "items": [{
    "user": { "id": "…", "display_name": "Priya", "first_name": "Priya",
              "role": "business_developer", "course": { "name": "Software Development" },
              "bio": "…", "looking_for": "…", "has_photo": true,
              "photo_url": "/api/v1/users/…/photo",
              "skills": [{ "name": "Python" }], "interests": [{ "name": "Climate tech" }] },
    "score": 70,
    "reasons": ["You both know Python, React.", "Both on Software Development."],
    "shared_skills": [{ "id": "…", "name": "Python" }],
    "connection_state": "none"     // none | pending_incoming | pending_outgoing | connected
  }],
  "next_cursor": "eyJzY29yZSI6NzB9"
}
```

`connection_state` is pre-computed here so the card renders the right button
without a second request. One round trip beats two.

**No email, no `is_active`, no `is_admin`.** `UserPublic`
([03](03_profiles.md) §6).

### `GET /api/v1/matches/{user_id}`

One match with the full breakdown — the detail view when someone clicks
through. Same auth, same gate, same exclusions.

`404` if that user is not a candidate. Excluded users are `404`, not `403`:
existence as a match is not the caller's business.

### Name filters vs id filters

Public filters use **names** (`?skill=Python`) because they are typed. Internal
queries use ids. Resolve the name to an id once in the router, then filter in
SQL. An unknown skill name is `422`, not an empty list — a typo that silently
returns nothing is the worst possible failure.

## 7. Query shape

One pass. Fetch a bounded page of candidates with their skills and interests
via a join, compute scores in Python, sort, then slice.

```
candidates = db.query(ProfileView)
             .filter(exclusions)              # NOT EXISTS on connections, is_active
             .filter(filters)                 # skills / role / course / interests
             .limit(CANDIDATE_POOL)           # e.g. 200
             .all()
scored = [score_match(viewer, c) for c in candidates]
scored.sort(key=lambda m: (-m.score, m.user_id))
```

Two things follow from this that matter:

**Fetch a bounded pool, then score.** You cannot score in SQL — the cap logic
and reason building are Python. Bound the candidate pool so a 500-person cohort
cannot drag every request. At bootcamp scale 200 is generous. If the cohort ever
outgrows it, the fix is a materialised score column, not an unbounded query.

**Sorting is done in Python, so cursor pagination encodes the score.** Encode
`(score, user_id)` in the opaque cursor, not an offset. See
[`00_conventions.md`](00_conventions.md) §5.

The pool is a real ceiling — mark it:

```python
# ponytail: candidate pool capped at 200 rows. Fine for a bootcamp cohort.
# Upgrade path if a cohort exceeds ~500: precomputed score column, refreshed
# on profile update, then paginate in SQL.
CANDIDATE_POOL = 200
```

## 8. Frontend

### `/matches` — the list

Filter bar: skill multi-select, role toggle, course dropdown, interest
multi-select. Filters sync to the URL query string so a filtered list is
shareable and the back button works.

Each row is a `MatchCard`:

```
┌────────────────────────────────────────────┐
│ [photo]  Priya Sharma            [Connect] │
│          Business Developer · Software Dev │
│                                              │
│          "You both know Python, React."     │
│          "Both on Software Development."    │
│                                              │
│          Skills: Python · SQL · Figma      │
└────────────────────────────────────────────┘
```

Button state comes from `connection_state`:

| State | Rendering |
|---|---|
| `none` | "Connect" → [05](05_connection_requests.md) |
| `pending_outgoing` | "Request sent" + "Withdraw" |
| `pending_incoming` | "Wants to connect" + "View request" |
| `connected` | "Message" → [06](06_messaging.md) |

Never show "Connect" to someone with an existing request. That is the
confusing state this design exists to prevent.

**Show the score?** No. Users do not reason in points, and a bare number
invites "why is this 70 and that 65?". The reasons carry the same information in
language that makes sense. Keep the score in the API for tests and the admin
screen.

### `/matches/:userId` — detail

Full profile, the complete reason list, and the connection action. Reuse
`UserProfileView` from [03](03_profiles.md) plus the match breakdown.

### Home feed widget

Top 6 via `GET /matches?limit=6`. Same `MatchCard`. Independent loading, empty
and error states ([01](01_landing_page.md) §3).

### Loading more

Infinite scroll with the cursor. **A "Load more" button is fine too** — do not
build a virtualised list for 20 items.

## 9. Tests

### Unit — `services/matching.py`

The scoring function is pure, so this suite is fast and the highest-value tests
in the project.

| Test | Asserts |
|---|---|
| `test_complementary_role_scores_30` | dev + business = 30 role points |
| `test_same_role_scores_zero_role_points` | dev + dev = 0 |
| `test_each_shared_skill_scores_10` | Exactly `10 × n` |
| `test_shared_skill_points_capped_at_30` | 5 skills = 30, not 50 |
| `test_each_shared_interest_scores_5` | Exactly `5 × n` |
| `test_shared_interest_points_capped_at_15` | 6 interests = 15 |
| `test_same_course_scores_20` | |
| `test_missing_course_scores_zero` | One side null → 0 |
| `test_no_overlap_scores_zero` | |
| `test_maximum_score_is_95` | Upper bound sanity check |
| `test_deterministic_across_runs` | **100 runs, identical output.** Tie-break on id |
| `test_ties_break_on_candidate_id` | Stable total order |
| `test_reasons_only_mention_contributing_factors` | No shared skill → no skill sentence |
| `test_reason_ordering_is_contribution_first` | Role reason leads at 30 |

### Integration

| Test | Asserts |
|---|---|
| `test_incomplete_profile_forbidden` | **Rule 3.** `403 profile_incomplete` |
| `test_incomplete_profile_returns_no_items` | **Rule 3.** Not a partial list |
| `test_matches_require_session` | **Rule 1.** `401` |
| `test_excludes_self` | |
| `test_excludes_connected_both_directions` | |
| `test_excludes_pending_both_directions` | **The commonly missed one** |
| `test_excludes_declined` | |
| `test_excludes_deactivated_users` | |
| `test_filters_are_and_combined` | `skill=python&role=business` → both |
| `test_repeated_filter_is_or` | Two skills → either |
| `test_unknown_skill_filter` | `422`, not an empty list |
| `test_pagination_has_no_duplicates_or_gaps` | **Cursor correctness**, all pages |
| `test_match_omits_email` | **Rule 4.** No email in any match payload |
| `test_connection_state_present_on_every_item` | UI depends on it |
| `test_match_detail_404s_for_excluded_user` | |

### E2E

1. Complete a profile → matches appear.
2. Top match is the obviously-right person for the seeded data, with a reason.
3. Apply a filter → list narrows, URL updates.
4. Filter by role → only that role.
5. Incomplete profile → home feed prompts instead of listing matches.

## 10. Out of scope

Vector and embedding search, free-text search, collaborative filtering,
popularity and activity scoring, recommendation feedback loops, "people you
viewed also viewed", server-rendered matches for crawlers, pagination by page
number, a visible numeric score in the UI, blocking users
([`deferred_safety_moderation.md`](deferred_safety_moderation.md)).

## 11. Definition of done

- [x] `score_match` is pure, deterministic, and fully unit-tested
- [x] Weights are one named constant, matching the §2 table
- [x] `403 profile_incomplete`, never partial results
- [x] All five exclusions, pending checked in both directions
- [x] Filters AND-combined, names resolved to ids, unknown name → `422`
- [x] Cursor pagination with no duplicates or gaps across pages
- [x] `reason` on every match, built from contributing factors only
- [x] No email in any match payload
- [x] Every §9 test passes

## 12. Agent notes

- **Pure function, no database.** If you find yourself passing a `Profile` ORM
  object into `score_match`, stop — the unit tests will need a database.
- **The 30-point skill cap is load-bearing.** Without it a 20-skill profile
  outranks every genuine complementary match. There is a test.
- **Exclude pending in both directions.** Most-missed exclusion in this
  feature. Read §5 twice.
- **Filter first, score second.** The reverse gives short pages and wrong
  counts.
- **Never return partial results for an incomplete profile.** `403` only.
---

## 13. As built — 2 October 2026

No deviations from the scoring rules. §2's weights, §3's determinism and §5's
five exclusions are implemented exactly as written, and the `CANDIDATE_POOL`
ceiling is marked as ADR 0011 requires.

### 13.1 Cursor pagination is now real

§6 lists `cursor` as a parameter and §7 says the cursor encodes `(score,
user_id)`. Both are implemented via
[`services/pagination.py`](../backend/app/services/pagination.py). The service
fetches `limit + 1` rows so "is there another page" is answered without a second
`COUNT`.

The same helper serves the other list endpoints, keyed on `(created_at, id)`
instead — see specs 06, 07 and 08.

### 13.2 Connection state comes from `/connections`, not from the match list

**This was a real bug, and it is worth recording because the spec led to it.**

§6 tells the frontend to render the connect button from `connection_state`,
which §6 also says comes with each match. But §5 requires matching to **exclude**
anyone with a pending request in either direction. The two rules combined mean
that the moment a user sends a request, the person **disappears from
`/matches` entirely** — so a profile page deriving its state from the match list
silently falls back to "no connection" and offers **Connect** again.

The backend correctly rejects the second request with `409`, so no data was
lost, but the UI was simply wrong and a user could reasonably believe they had
never sent anything.

`PublicProfilePage` now reads state from `GET /connections`, which returns all
requests involving the caller including pending ones. The match list still
carries `connection_state` for cards, where the exclusion makes it redundant
anyway.

### 13.3 Other notes

`resolve_names` raises `422` for an unknown skill or interest name, as §6
requires — a filter typo must not silently return an empty list.

`score_match` takes `ProfileView`, not an ORM model, exactly as §3 requires, and
its unit suite runs with no database.

**Test coverage:** 16 unit tests in
[`tests/unit/test_matching.py`](../backend/tests/unit/test_matching.py) covering
every weight, both caps, the 95-point maximum, determinism over 100 runs, tie
ordering, and that reasons mention only contributing factors. Integration tests
cover the completeness gate returning `403` with no `items` key, all five
exclusions, filter combination, and the email scan.

**Known gaps:** no component tests for the filter bar; the two E2E matching tests
are deliberately loose, because seeded data changes and assertions on exact
cohort contents would break every time it is reseeded.
