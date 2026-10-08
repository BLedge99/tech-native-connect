# 03 — Profiles

**Goal:** a profile carries enough information for matching to rank people
sensibly, and enough for someone to decide whether they want to talk to you.

**Depends on:** [02 — Registration](02_registration_and_login.md)
**Blocks:** [04 — Matching](04_matching_and_search.md),
[05 — Connection requests](05_connection_requests.md),
[08 — Project ideas](08_project_ideas.md), [09 — Admin](09_admin.md)

**Implementation status:** Implemented 2 Oct 2026 — see the *As built* note at the end of this document for deviations from the spec.

---

## 1. Scope

| In | Out |
|---|---|
| Photo upload as a Postgres blob | Multiple photos, cropping UI, cover images |
| Bio | Markdown rendering — store and display as plain text |
| Skills, interests | Skill endorsements, proficiency levels, skill ratings |
| Course, role | Changing course after signup — see §7 |
| `profile_complete` flag | Profile views counter, profile visibility settings — [`deferred_privacy_settings.md`](deferred_privacy_settings.md) |
| Public read view of another profile | Editing another user's profile (except admin) |

## 2. Why profile fields are not collected at signup

Registration takes email, password and display name only
([02](02_registration_and_login.md) §1). Profile fields arrive afterwards, on a
dedicated screen, for three reasons:

1. **One place to change them.** No field ends up validated in two endpoints.
2. **Signup stays fast.** Three fields, not nine. A long form loses people at
   the very first step of the demo.
3. **The incomplete state is intentional.** A profile with no role and no
   skills is exactly what a brand-new user has, and the app has a defined
   response to it: matching returns `403 profile_incomplete`
   ([04](04_matching_and_search.md)).

A new user registers, lands on the home feed, sees "add a role and at least one
skill", does so, and then matching unlocks. That flow is the demo.

## 3. Data model

Profiles are **one-to-one with users**, but a separate table. Keeps auth
([02](02_registration_and_login.md) §2) from growing into a profile model, and
makes the nullable-column question go away: an incomplete profile is a row with
nulls, not a user missing a row.

### `profiles`

| Column | Type | Notes |
|---|---|---|
| `id` | `uuid` PK | |
| `user_id` | `uuid` FK → `users.id` | Unique. `ON DELETE CASCADE` |
| `bio` | `varchar(500)` nullable | Plain text |
| `role` | enum nullable | `software_developer` \| `business_developer` |
| `course_id` | `uuid` FK nullable | → `courses.id` |
| `looking_for` | `varchar(300)` nullable | "What are you looking for?" — feeds match reasons |
| `photo_id` | `uuid` nullable | → `photos.id`, decoupled so upload can change without touching the profile |
| `profile_complete` | `boolean` | Default `false`. See §5 |
| `created_at` / `updated_at` | `timestamptz` | |

### `photos`

Separate so photo storage can change without touching the profile, and so
multiple photos could be added later without a migration.

| Column | Type | Notes |
|---|---|---|
| `id` | `uuid` PK | |
| `user_id` | `uuid` FK → `users.id` | `ON DELETE CASCADE` |
| `content_type` | `varchar(50)` | From the request. Whitelisted — never trust the client's claim blindly |
| `byte_size` | `integer` | Enforce the 2 MB cap in the column too |
| `data` | `bytea` | The image. Never base64 in an API response |
| `created_at` | `timestamptz` | |

### `skills` and `interests`

Admin-managed reference data ([09](09_admin.md)), joined through join tables.

### `profile_skills` / `profile_interests`

| Column | Type | Notes |
|---|---|---|
| `profile_id` | `uuid` FK | Composite PK with the ref id |
| `skill_id` / `interest_id` | `uuid` FK | `ON DELETE CASCADE` |
| `created_at` | `timestamptz` | |

Composite primary key `(profile_id, skill_id)` means the same skill cannot be
added twice — the database enforces it, not a check in a route.

### Reference tables

```sql
CREATE TYPE user_role AS ENUM ('software_developer', 'business_developer');

courses   (id uuid PK, name varchar(100) UNIQUE, created_at)
skills    (id uuid PK, name varchar(50) UNIQUE, category varchar(50) NULL, created_at)
interests (id uuid PK, name varchar(50) UNIQUE, created_at)
```

**A real Postgres `ENUM`, not a `varchar` with a check.** Roles are a closed set
the app understands; the database should refuse anything else, so an invalid
role can never reach the database even if a route has a bug.

## 4. Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/api/v1/users/me` | session | Own full profile |
| `PATCH` | `/api/v1/users/me` | session | Update own profile |
| `POST` | `/api/v1/users/me/photo` | session | Upload or replace photo |
| `DELETE` | `/api/v1/users/me/photo` | session | Remove photo |
| `GET` | `/api/v1/users/me/photo` | session | Serve own photo |
| `GET` | `/api/v1/users/{user_id}` | session | **Public** view of another profile |
| `GET` | `/api/v1/users/{user_id}/photo` | session | Serve another's photo |
| `GET` | `/api/v1/courses` | session | For the dropdown |
| `GET` | `/api/v1/skills` | session | For the picker |
| `GET` | `/api/v1/interests` | session | For the picker |

### `GET /users/me` — private

Everything, including fields a non-owner never sees:

```jsonc
{
  "id": "…", "email": "sam@example.com", "display_name": "Sam",
  "first_name": "Sam", "is_admin": false, "is_active": true,
  "created_at": "2026-10-02T10:00:00Z",
  "profile": {
    "bio": "…", "role": "software_developer",
    "course": { "id": "…", "name": "Software Development" },
    "looking_for": "A business partner for a fintech idea",
    "skills": [{ "id": "…", "name": "Python" }],
    "interests": [{ "id": "…", "name": "Climate tech" }],
    "profile_complete": true,
    "has_photo": true,
    "photo_url": "/api/v1/users/me/photo"
  }
}
```

**Only this endpoint returns an email address.** Not `GET /users/{id}`, not
matches, not threads. See §6.

### `GET /users/{user_id}` — public

Same shape **minus** `email`, `is_active`, and the profile-internal fields.
Anyone signed in may read any profile — the app is a cohort network and
profiles are not private. That is a deliberate decision; per-user privacy
settings are [`deferred_privacy_settings.md`](deferred_privacy_settings.md).

| Case | Status | `code` |
|---|---|---|
| Success | `200` | — |
| No session | `401` | `unauthenticated` |
| Unknown id | `404` | `not_found` |
| Deactivated user | `404` | `not_found` |

A deactivated user `404`s rather than `200`-ing a ghost profile. This is the
`404`-for-private-existence rule from [`00_conventions.md`](00_conventions.md) §2.

### `PATCH /users/me`

```jsonc
// request — all fields optional, only what you send is changed
{ "bio": "…", "role": "business_developer", "course_id": "…",
  "looking_for": "…", "skill_ids": ["…"], "interest_ids": ["…"] }

// 200 — updated profile
```

Replacing `skill_ids` wholesale rather than adding and removing individually.
One array in, one array out, no diffing logic, no endpoint for removal.
Setting `skill_ids: []` clears skills. This is the laziest correct shape and it
is also the least ambiguous.

Recompute `profile_complete` after every update (§5).

| Case | Status | `code` |
|---|---|---|
| Success | `200` | — |
| Invalid role | `422` | `validation_error` |
| Unknown `course_id`/`skill_id` | `422` | `validation_error` |
| **Another user's id in the body** | `403` | `not_profile_owner` |

### `POST /users/me/photo`

`multipart/form-data`, field name `file`.

| Aspect | Rule |
|---|---|
| Max size | **2 MB** → over is `413 file_too_large` |
| Types | `image/jpeg`, `image/png`, `image/webp` → else `415 unsupported_media_type` |
| Detection | **Sniff the actual bytes**, do not trust `content_type` or the extension |
| Replacing | New upload deletes the old row. One photo per user |
| Empty file | `422` |
| Stored | Raw `bytea` in `photos.data` |

**Verify the bytes, not the header.** A client can send
`Content-Type: image/png` with a shell script inside. Check the magic number —
JPEG `FF D8 FF`, PNG `89 50 4E 47`, WebP `RIFF....WEBP`. This is a trust
boundary (`AGENTS.md` §5 rule 5).

**Never base64 in a JSON response.** Base64 inflates by 33% and `bytea` already
serves as `image/jpeg` with `Content-Disposition: inline`. A photo URL is the
shape; not a data URI.

Set `Cache-Control: private, max-age=86400` and **ETag**. Uploaded photos do
not change; re-downloading on every render is pointless.

### Serving photos

`GET /users/{id}/photo` requires a session. Photos are not public URLs — a
signed-out stranger with the id should not get the cohort's pictures. Do not
serve the `uploads/` directory statically.

Return `404` when there is no photo, and the frontend renders initials on a
coloured circle. Every user without a photo must still look deliberate.

## 5. `profile_complete`

**`true` when `role IS NOT NULL` AND the profile has ≥1 skill. Nothing else.**

```
profile_complete = role IS NOT NULL AND (SELECT COUNT(*) FROM profile_skills
                                           WHERE profile_id = p.id) >= 1
```

Computed and stored, recomputed on every profile update, so it can be indexed
and filtered. A stored boolean is a cache; recompute it in the service and
never trust a value sent by the client.

**Interests, course, photo and bio are not required.** Keep the bar minimal —
the goal is enough signal to rank people, and role + one skill is enough. Do
not add requirements to "improve" it. Every extra required field is another
reason a user never reaches the demo.

Course is deliberately **not** required. Matching filters by it but does not
require it: a user who has not filled it in should still be able to see people.

This flag gates matching ([04](04_matching_and_search.md) §4) and matching is
the first thing a new user wants. Keep the gate easy to pass.

## 6. What other users may see

| Field | Own profile | Someone else's |
|---|---|---|
| `display_name`, `first_name` | ✅ | ✅ |
| `bio`, `role`, `course`, `looking_for` | ✅ | ✅ |
| `skills`, `interests` | ✅ | ✅ |
| `has_photo`, `photo_url` | ✅ | ✅ |
| `profile_complete` | ✅ | ❌ |
| **`email`** | ✅ | ❌ |
| `is_active` | ✅ | ❌ |
| `is_admin` | ✅ | ❌ |

Two schemas, two Pydantic models: `UserPrivate` and `UserPublic`. Do not build
one model and strip fields in the router — routers are thin
([`00_conventions.md`](00_conventions.md) §8) and stripping in a router is where
a leak happens. Two schemas make the leak structurally impossible.

**There is an integration test that asserts another user's email never appears
in any response body.** Not a spot check — a scan of every endpoint that
returns user data.

## 7. Endpoints that must not exist

| Rejected | Why |
|---|---|
| `PATCH /users/{id}` | Only `/users/me`. The path id would be the client telling the server who to edit — [`00_conventions.md`](00_conventions.md) §3 |
| `PUT /users/{id}` | Same |
| `DELETE /users/{id}` | Account deletion is [`deferred_privacy_settings.md`](deferred_privacy_settings.md) |
| `POST /users/{id}/skills` | Covered by `PATCH /users/me` |

Admin reading another user's profile works by **admin using `/users/me`**, not
by editing them. Admin *deactivation* and *role changes* are their own endpoints
in [09](09_admin.md), each audited.

## 8. Validation

| Field | Rule | Cap |
|---|---|---|
| `bio` | Trimmed, plain text | 500 chars |
| `looking_for` | Trimmed | 300 chars |
| `role` | Must be a valid enum value | — |
| `course_id`, `skill_ids`, `interest_ids` | Must exist | ≤ 20 skills, ≤ 20 interests |
| `display_name` | Trimmed, non-empty | 80 chars |
| Photo | Sniffed type, 2 MB | 2 MB |

20 skills is a ceiling to stop a client posting a 10,000-element array. Not a
judgment about how capable anyone is.

### Bio is stored and rendered as plain text

React escapes by default, so there is no XSS hole. **Do not add
`dangerouslySetInnerHTML` for "rich bios"** — newlines and paragraphs are
sufficient and there is no sanitiser dependency.

## 9. Frontend

| Route | Renders |
|---|---|
| `/profile` | Own profile, read view |
| `/profile/edit` | Edit form |
| `/users/:userId` | Someone else's profile |

### The edit form

Sections, in the order that gets a new user to `profile_complete` fastest —
identity and role first, because those plus skills are the gate:

1. **Photo** — drag-and-drop or click, with a live preview and a remove
   button. Show the 2 MB limit and accepted types *before* upload fails.
2. **Role** — two big cards, `software_developer` / `business_developer`. Not
   a dropdown; this is a defining choice and should feel like one.
3. **Skills** — multi-select with type-ahead over `/skills`. Showing selected
   chips. At least one is required for matching, so say so on the field.
4. **Course** — dropdown from `/courses`. Optional, labelled as such.
5. **Interests** — multi-select over `/interests`. Optional.
6. **Bio** — textarea with a live `n/500` counter.
7. **Looking for** — textarea, optional.

**Show `profile_complete` state live.** "Add a role and one skill to unlock
matching" with the state updating as they type, so the gate is never a
surprise. A progress hint beats a `403` after the fact.

`/profile/edit?focus=skills` scrolls to and highlights that section — the
incomplete-profile prompt deep-links here
([01](01_landing_page.md) §4).

### Public profile view

Photo, name, role, course, bio, looking for, skills, interests. **Then a
contextual action: "Connect" if no request exists, or the current connection
state** — pending, connected, or "Start conversation". See
[05](05_connection_requests.md).

Render the real state from `GET /connections?user_id=`, never from local
optimistic state.

## 10. Tests

### Unit — `services/profiles.py`

| Test | Asserts |
|---|---|
| `test_profile_complete_requires_role_and_skill` | Both → `true` |
| `test_profile_complete_false_without_skill` | Role only → `false` |
| `test_profile_complete_false_without_role` | Skill only → `false` |
| `test_profile_complete_ignores_interests` | Interests alone → `false` |
| `test_profile_complete_true_with_one_skill` | Exactly one is enough |
| `test_bio_strips_html` | `<script>` retained as text, not markup |
| `test_public_schema_excludes_email` | **The leak guard** |
| `test_photo_type_sniffing` | Every accepted and rejected byte signature |
| `test_photo_size_cap` | 2 MB ok, 2 MB + 1 → `413` |
| `test_photo_rejects_fake_content_type` | Shell script claiming `image/png` → `415` |

### Integration

| Test | Asserts |
|---|---|
| `test_update_own_profile` | `200`, persisted |
| `test_update_another_users_profile` | **Rule 4.** No such route → `405`/`404` |
| `test_other_user_profile_omits_email` | **Rule 4.** No `email` key anywhere in the body |
| `test_no_endpoint_returns_another_users_email` | **Scans every user-returning endpoint.** §6 |
| `test_unauthenticated_profile_access` | **Rule 1.** `401` on all of `/users/*` |
| `test_photo_upload_and_serve` | Round-trip bytes match |
| `test_photo_oversize_rejected` | `413` |
| `test_photo_wrong_type_rejected` | `415` |
| `test_photo_replacement_deletes_old` | One `photos` row per user |
| `test_photo_not_publicly_served` | No session → `401` |
| `test_deactivated_user_profile_404s` | `404`, not `200` |
| `test_invalid_role_rejected` | `422` |
| `test_duplicate_skill_rejected` | DB composite PK |

### E2E

1. Register → home feed → "complete your profile" → `/profile/edit`.
2. Upload a photo → preview → save → appears on `/profile`.
3. Pick role + one skill → `profile_complete` flips → suggestions unlock.
4. Sign up as a second user, browse matches, open the first user's profile →
   bio, skills and photo visible; **no email address anywhere on the page.**
5. Over-2 MB photo → inline error, upload blocked before the request.

## 11. Out of scope

Multiple photos, cropping and rotation, skill proficiency levels, profile
editing history, profile visibility settings
([`deferred_privacy_settings.md`](deferred_privacy_settings.md)), profile
completeness percentages, avatar uploads separate from the profile photo,
markdown bios.

## 12. Definition of done

- [x] `UserPrivate` and `UserPublic` are separate schemas (§6)
- [x] Photo upload stores a sniffed-type blob, 2 MB cap, served from Postgres
- [x] `profile_complete` = role + ≥1 skill, recomputed on every update
- [x] No route lets a user write another user's profile
- [x] No response body anywhere contains another user's email
- [x] Live `profile_complete` hint on the edit form
- [x] Every §10 test passes

## 13. Agent notes

- **Use a Postgres `ENUM` for `role`.** It stops invalid values at the database
  even if a route has a bug.
- **Sniff photo bytes.** Checking the extension or the client's `content-type`
  is not validation.
- **Two schemas, not field-stripping in a router.** The email leak is the one
  thing here that is a genuine security bug.
- **`profile_complete` is cached state.** Recompute it in the service; never
  trust a client-supplied value.
- **Do not add a second photo or an upload library.** One photo, one endpoint.
---

## 14. As built — 2 October 2026

**One deviation, and it simplifies this spec.**

### 14.1 `ProfilePrivate` is gone; `UserPrivate` carries the difference

§6 named three schemas (`ProfilePublic`, `ProfilePrivate`, `UserPublic`). The
split that actually matters is **own account vs someone else's**, so that is
where the boundary sits:

| Schema | Contains | Used by |
|---|---|---|
| `UserPublic` | profile fields only, **never `email`** | `/users/{id}`, matches, connections, threads, notifications, ideas |
| `UserPrivate` | `UserPublic` + `email`, `is_admin`, `is_active`, `last_login_at` | `/users/me`, auth responses |

`ProfilePrivate` existed only to add `user_id`, which no endpoint returned.
Removing it deleted a schema rather than adding one, and the leak guard in §6 is
now carried by `UserPublic` having no `email` field to leak.

§6's table is otherwise implemented as written: `profile_complete`, `is_active`
and `is_admin` are absent from the public view.

### 14.2 Other notes

`GET /users/me` is registered **before** `GET /users/{user_id}`. FastAPI matches
in declaration order, so the reverse order makes `/users/me` unreachable. Any
future literal path segment must be declared ahead of its parameterised sibling.

`profile_complete` is recomputed in `update_profile` and in `seed.py`, and was
**written by SQL into the live database once** during development because
`seed.py` originally refreshed the profile after setting the flag, which
discarded the change. Both fixed.

**Test coverage:** unit tests for `sniff_image_type` covering PNG, JPEG, WebP
and the rejection of a shell script claiming to be a PNG; integration tests for
upload, the 2 MB cap, type rejection, round-trip bytes, the 413/415 codes, and
a **scan across eight user-returning endpoints** asserting no response contains
another user's email.

**Known gaps:** no component tests for the edit form; the photo-downscaling
mentioned in ADR 0006 is not implemented — the original is served.
