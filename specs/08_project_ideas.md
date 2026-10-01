# 08 — Project ideas board

**Goal:** business developers post what they want to build. Developers find
one they can build and say so. The second way the two groups find each other,
and the feature that gives the notification system a reason to exist beyond
connections.

**Depends on:** [03 — Profiles](03_profiles.md),
[07 — Notifications](07_notifications.md)
**Blocks:** nothing.

**Implementation status:** Not started.

---

## 1. Scope

| In | Out |
|---|---|
| Post, edit own, delete own ideas | Comments or replies |
| Browse, filter, paginate | Voting, ranking, featuring |
| Express / withdraw interest | Messaging an interested party |
| Notify the author | Editing someone else's idea |
| Draft states, tags | Draft states — deliberately excluded, see §3 |

### Interest does not open a conversation

**Do not create a connection or a thread when someone expresses interest.**
Interest is one-way and light; connection is mutual opt-in
([05](05_connection_requests.md)). If interest opened a chat, any developer
could message any business developer unilaterally, which breaks
`AGENTS.md` §5 rule 2.

The flow is: see an idea → interested → the author gets notified → **the author
sends a connection request if they want to talk.** Interest is a signal, not an
access grant.

## 2. Data model

### `project_ideas`

| Column | Type | Notes |
|---|---|---|
| `id` | `uuid` PK | |
| `author_id` | `uuid` FK → `users.id` | `ON DELETE CASCADE` |
| `title` | `varchar(120)` | |
| `description` | `text` | 50–2000 chars |
| `category` | enum | `find_problem` \| `build_product` \| `design_brand` \| `run_campaign` \| `other` |
| `skills_needed` | `varchar[]` free-text | **Not** foreign keys — see §3 |
| `course_id` | `uuid` FK nullable | Defaults to the author's course |
| `is_open` | `boolean` | Default `true`. `false` = found someone |
| `created_at` / `updated_at` | `timestamptz` | |

### `idea_interests`

| Column | Type | Notes |
|---|---|---|
| `idea_id` | `uuid` FK | Composite PK with `user_id` |
| `user_id` | `uuid` FK | |
| `created_at` | `timestamptz` | |

Composite PK `(idea_id, user_id)` makes double-interest structurally
impossible. Same pattern as the connection-request index
([05](05_connection_requests.md) §1) — a database constraint beats a
`SELECT`-before-`INSERT` race every time.

### Indexes

- `project_ideas(created_at DESC)` — the board's default order.
- `project_ideas(author_id)` — "my ideas".
- `project_ideas(is_open, created_at DESC)` — open ideas, the common query.
- `idea_interests(idea_id)` with a count aggregate for "N interested".

### `skills_needed` is free text, deliberately

It is **not** a join to the `skills` table. Two reasons:

1. An idea needs "a designer who knows Figma" — free text expresses the
   specific ask, where a controlled vocabulary forces a lossy choice.
2. It would mean the author's idea is invalid until someone creates a matching
   skill row. Ideas should not be blocked by admin reference-data hygiene.

The cost: idea skills cannot be searched with the same code as profile skills.
Acceptable — the board filters on `category` and free-text `search`, not on
skills.

### `category` is a real enum

Five values, closed set, used for filtering and shown as a label. Same reasoning
as `user_role` ([03](03_profiles.md) §3): let the database refuse anything else.

```sql
CREATE TYPE idea_category AS ENUM (
  'find_problem', 'build_product', 'design_brand', 'run_campaign', 'other'
);
```

## 3. No drafts

The brief does not ask for them, and they add a `status` column, a status
filter, an autosave mechanism and a draft list view. Post and edit, no draft.

The "is this public?" anxiety is handled by `is_open` (§7), which does the job
one boolean already does.

## 4. Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/api/v1/ideas` | session | Browse, filtered |
| `POST` | `/api/v1/ideas` | session | Create |
| `GET` | `/api/v1/ideas/{id}` | session | One idea |
| `PATCH` | `/api/v1/ideas/{id}` | session | **Author only** |
| `DELETE` | `/api/v1/ideas/{id}` | session | **Author only** |
| `POST` | `/api/v1/ideas/{id}/interest` | session | Express interest |
| `DELETE` | `/api/v1/ideas/{id}/interest` | session | Withdraw interest |

### `GET /ideas`

| Param | Type | Notes |
|---|---|---|
| `category` | enum | Repeatable |
| `search` | string | Title + description, `ILIKE` |
| `author_id` | uuid | "Ideas by this person" |
| `mine` | bool | Shorthand for `author_id = me` |
| `open_only` | bool | Default `true` |
| `limit` / `cursor` | | Default 20, max 50 |

Default `open_only=true` because the board's purpose is finding something to
work on. A closed idea is history. Pass `open_only=false` to see everything.

```jsonc
{
  "items": [{
    "id": "…", "title": "Carbon-aware logistics for local couriers",
    "description": "…",
    "category": "build_product",
    "skills_needed": ["Python", "Postgres"],
    "course": { "id": "…", "name": "Software Development" },
    "is_open": true, "interest_count": 4,
    "created_at": "2026-10-10T08:00:00Z",
    "author": { "id": "…", "display_name": "Priya", "has_photo": true, "photo_url": "…" },
    "viewer_has_interested": false
  }],
  "next_cursor": "…"
}
```

`viewer_has_interested` is computed per row so the button renders correctly
without a fetch per card. Same reasoning as `connection_state` in
[04](04_matching_and_search.md) §6.

**No email, no `is_active`.** `UserPublic` ([03](03_profiles.md) §6).

### `POST /ideas`

```jsonc
{
  "title": "Carbon-aware logistics for local couriers",
  "description": "…",
  "category": "build_product",
  "skills_needed": ["Python", "Postgres"],
  "course_id": null            // null = the author's course
}
// 201
```

Requires a complete profile. Posting an idea without skills on your profile
means matching cannot surface you to the developers it is for.

| Case | Status | `code` |
|---|---|---|
| Success | `201` | — |
| No session | `401` | `unauthenticated` |
| Incomplete profile | `403` | `profile_incomplete` |
| Invalid category | `422` | `validation_error` |
| Title too long | `422` | `validation_error` |
| Description too short | `422` | `validation_error` |

### `PATCH` / `DELETE /ideas/{id}`

**Author only.** Admin does not get an exception here — idea content is the
author's voice, and admin's powers are user management and reference data
([09](09_admin.md)).

| Case | Status | `code` |
|---|---|---|
| Success | `200` / `204` | — |
| **Not the author** | `403` | `not_idea_owner` |
| Unknown id | `404` | `not_found` |
| No session | `401` | `unauthenticated` |

`403` rather than `404` here, deliberately the opposite of threads
([06](06_messaging.md) §3). An idea is **public** — anyone signed in can read it.
There is no existence to protect, so the honest answer is "you are not the
author". `404` would be a lie that also hides a real authorisation failure.

Do not apply the thread rule to ideas. Pick per resource, on the question *"is
existence private?"*

Deleting an idea cascades to `idea_interests`. Notifications referencing it stay
(§5 of [07](07_notifications.md)) and their `url` 404s.

### `POST /ideas/{id}/interest`

```jsonc
// 201 on first, 200 if already interested
{ "idea_id": "…", "user_id": "…", "created_at": "…" }
```

Creates the interest and notifies the author **once**
([07](07_notifications.md) §3).

| Case | Status | `code` |
|---|---|---|
| Success | `201` / `200` | — |
| Own idea | `422` | `validation_error` |
| Unknown idea | `404` | `not_found` |
| **Closed idea** | `409` | `idea_closed` |
| Incomplete profile | `403` | `profile_incomplete` |
| No session | `401` | `unauthenticated` |

**Already-interested is `200`, not `409`.** The database's composite PK makes a
duplicate impossible; making the endpoint idempotent means a double-click or a
retried request cannot show an error to someone who just successfully expressed
interest. This is the one place the codebase should prefer idempotency over
conflict reporting.

`idea_closed` is `409` — the state changed and the action no longer applies.

### `DELETE /ideas/{id}/interest`

`204`, idempotent. Withdrawing is always allowed, even on a closed idea —
changing your mind should never be blocked by someone else's state change.

## 5. Frontend

### `/ideas` — the board

Newest first, cards in a responsive grid (1 column mobile, 2-3 desktop).

```
┌──────────────────────────────────────────┐
│ Carbon-aware logistics for local couriers │
│ [Build product]  · Software Development   │
│                                                 │
│ Route planning that accounts for…         │
│                                                 │
│ Needs: Python · Postgres · Maps API       │
│ [photo] Priya Sharma · 2 days ago          │
│                                                 │
│ 4 interested              [I'm interested] │
└──────────────────────────────────────────┘
```

Filter bar: category chips, search box, "my ideas" / "open only" toggles.
Filters in the URL query string, like `/matches` ([04](04_matching_and_search.md) §8).

States, all four:

| State | Rendering |
|---|---|
| Loading | Skeleton cards, not a spinner over the whole page |
| Empty, filtered | "No ideas match these filters." + clear filters |
| Empty, unfiltered | "No ideas yet. Be the first." + post button |
| Error | "Couldn't load ideas." + retry. **Other widgets still render** |

### `/ideas/:id` — detail

Full description, skills needed, author profile card linking to `/users/:id`,
interest count, interest / withdraw button, and "Edit" **only when the viewer is
the author** — the server decides, the client follows.

Author tools: edit, delete (with a confirm — deleting is destructive and unlike
declining a connection it *is* worth confirming), mark closed / reopen.

### `/ideas/new` and `/ideas/:id/edit`

Same form. Title, category (segmented control, five options with descriptions),
description (textarea, 2000 max, live counter), skills needed (tag input, free
text, ~8 max), course (prefilled with the author's).

`skills_needed` is a **tag input, not a multi-select** over the `skills` table.
Free text by design (§2). Free typing, chips, backspace to delete the last.

### Role-flavoured call to action

The board exists because business developers post and developers respond. Show
a role-appropriate primary action: **"Post an idea"** for business developers,
**"Browse ideas"** for software developers. Both can do both — this is a nudge,
not a permission.

### Interest button

Toggle, optimistic on express **and** withdraw, both trivially reversible and
both fire a single request.

```tsx
// Optimistic in both directions: expressing interest and withdrawing are
// equal-and-opposite and a failed one just flips the icon back.
```

Do not route interest through a connection request or a message. §1.

## 6. Tests

### Unit — `services/ideas.py`

| Test | Asserts |
|---|---|
| `test_create_requires_complete_profile` | `403 profile_incomplete` |
| `test_interest_requires_complete_profile` | `403` |
| `test_cannot_interested_in_own_idea` | `422` |
| `test_interest_creates_exactly_one_notification` | **Author, once** |
| `test_duplicate_interest_is_idempotent` | **Not `409`.** §4 |
| `test_interest_on_closed_idea_rejected` | `409 idea_closed` |
| `test_withdraw_is_always_allowed` | Even when closed |
| `test_category_must_be_valid_enum` | |
| `test_interests_cascade_on_idea_delete` | |

### Integration

| Test | Asserts |
|---|---|
| `test_create_idea` | `201` |
| `test_ideas_require_session` | **Rule 1** → `401` |
| `test_edit_own_idea` | `200` |
| `test_edit_other_users_idea` | **`403 not_idea_owner`** |
| `test_delete_other_users_idea` | **`403`** |
| `test_non_author_cannot_edit` | Author identity from session, **not the body** |
| `test_idea_list_omits_author_email` | **Rule 4** |
| `test_interest_flow` | `201`, count increments |
| `test_interest_twice` | Second `200`, **one** notification |
| `test_board_filters_by_category` | |
| `test_board_search_filters_by_title` | |
| `test_board_open_only_default` | |
| `test_board_pagination` | No duplicates or gaps |
| `test_cannot_interest_in_own_idea` | `422` |
| `test_interest_on_closed_idea` | `409` |
| `test_viewer_has_interested_present` | UI depends on it |

### E2E

1. Business developer posts an idea.
2. Developer browses the board, filters by category, opens it.
3. Developer expresses interest.
4. **Author's notification badge shows 1 live, no refresh.**
5. Author edits the idea; the change is visible.
6. Developer withdraws interest; the count drops.
7. Author closes the idea; interest is refused.
8. A third user cannot edit it (`403`).

## 7. Out of scope

Comments, replies, voting, ranking, featuring, drafts, image attachments,
messaging from an idea, idea following without interest, idea expiry, editing
after close, `skills_needed` linked to the `skills` table,
moderating ideas through the admin panel.

## 8. Definition of done

- [ ] Author-only create / edit / delete, all tested with a third party
- [ ] Interest is a composite PK — duplicates impossible, endpoint idempotent
- [ ] Interest never creates a connection or thread
- [ ] Interest notifies the author exactly once
- [ ] Four board states render: loading, empty-filtered, empty-unfiltered, error
- [ ] `skills_needed` is free text, not a skills join
- [ ] `is_open` blocks new interest but never blocks withdrawal
- [ ] Every §6 test passes

## 9. Agent notes

- **Interest does not open a chat.** The most important rule in this feature.
  If it did, `AGENTS.md` §5 rule 2 is broken.
- **`403` for a non-author, not `404`.** Ideas are public, so existence is not
  secret. Do not copy the thread rule here.
- **Already-interested is `200`, not `409`.** Idempotent beats a conflict error
  on a button someone just double-clicked.
- **`skills_needed` is free text on purpose.** Do not "improve" it into a join.
- **Posting requires a complete profile.** Easy to forget; it is the point of
  the gate.