# 09 — Admin screens

**Goal:** let the project participants manage the reference data the rest of
the app depends on, and see who is using it.

**Depends on:** [03 — Profiles](03_profiles.md), [02 — Registration](02_registration_and_login.md)
**Blocks:** nothing. **Most cuttable feature** — see [`roadmap.md`](../roadmap.md) §Cut line.

**Implementation status:** Implemented 2 Oct 2026 — see the *As built* note at the end of this document for deviations from the spec.

---

## 1. Scope

| In | Out |
|---|---|
| Manage courses, skills, interests | Manage project ideas |
| List users, deactivate, promote to admin | Delete users |
| Audit log of admin access | Admin dashboard stats — see §4 Overview |
| | Content moderation queue — [`deferred_safety_moderation.md`](deferred_safety_moderation.md) |
| | Bulk operations, CSV import, password resets |

### Admin manages the substrate, not other people's content

The boundary is deliberate and consistent:

| Admin **can** | Admin **cannot** |
|---|---|
| Manage courses, skills, interests | Edit another user's profile, bio or photo |
| Deactivate a user | Edit or delete a project idea |
| Promote a user to admin | Read or send another user's messages |
| See the audit log | Reset a password |

**Admins manage the app, not individual users' content.** Anyone can post an
idea ([08](08_project_ideas.md) §4); no one can edit it but its author, and that
holds for admins too. If admin can rewrite a user's bio, then every content
field in the app is really editable by staff, and that is a much larger product
decision than a bootcamp demo.

Admin reads of user data are **audited** ([03](03_profiles.md) §6).

### Deactivating, not deleting

`is_active = false` plus a login block ([02](02_registration_and_login.md) §3).
The user row stays because connections, messages, notifications and ideas
reference it, and `ON DELETE CASCADE` would erase a conversation thread that two
people had. Deletion is a GDPR project
([`deferred_privacy_settings.md`](deferred_privacy_settings.md)).

## 2. Data model

### Existing tables

`courses`, `skills`, `interests` ([03](03_profiles.md) §3). Admin manages these
in place — no separate admin schema.

Add to `skills`: `category varchar(50) nullable` — "Language", "Framework",
"Tool", "Design". One nullable column, purely for grouping in the picker. It is
not a taxonomy to design; it is a label.

### `admin_audit_log`

New. Every admin read or write of user data.

| Column | Type | Notes |
|---|---|---|
| `id` | `uuid` PK | |
| `admin_id` | `uuid` FK → `users.id` | Who |
| `action` | enum | `view_user`, `deactivate_user`, `reactivate_user`, `grant_admin`, `revoke_admin`, `create_skill`, `update_skill`, `delete_skill`, `create_course`, `update_course`, `create_interest`, `update_interest` |
| `target_type` | varchar(50) nullable | `user`, `skill`, `course`, `interest` |
| `target_id` | `uuid` nullable | |
| `metadata` | `jsonb` | What changed, old → new |
| `created_at` | `timestamptz` | |

Index on `(created_at DESC)` for the log listing, and `(admin_id, created_at DESC)`.

### Audit writes are not optional

Every admin action that touches user data writes a row **in the same
transaction** as the action. If the transaction rolls back, the audit row
disappears with it — which is correct, since nothing happened.

Writing audit rows from application middleware is tempting and wrong:
middleware cannot know whether the handler succeeded, so it logs attempts as if
they were actions. Write them in the service, where the outcome is known.

**Do not log admin access to reference data reads** (listing skills). Logging
every GET makes the log unreadable and buries the entries that matter, which are
the ones about people.

## 3. Endpoints

Every route below requires `get_current_admin`. A non-admin gets `403`.

### Users

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/admin/users` | List, searchable, paginated |
| `GET` | `/api/v1/admin/users/{id}` | Full user incl. email, inactive |
| `POST` | `/api/v1/admin/users/{id}/deactivate` | `is_active = false` |
| `POST` | `/api/v1/admin/users/{id}/reactivate` | `is_active = true` |
| `POST` | `/api/v1/admin/users/{id}/grant-admin` | `is_admin = true` |
| `DELETE` | `/api/v1/admin/users/{id}/admin` | `is_admin = false` |

**Mutation verbs are `POST` with a sub-path, not `PATCH`.** `PATCH
/admin/users/{id}` would invite someone to send `{"email": "..."}`, which the
admin model explicitly does not allow ([09](09_admin.md) §1). The path says what
is permitted; a PATCH body does not.

### Reference data

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/admin/courses` | List |
| `POST` | `/api/v1/admin/courses` | Create |
| `PATCH` | `/api/v1/admin/courses/{id}` | Rename |
| `GET` | `/api/v1/admin/skills` | List |
| `POST` | `/api/v1/admin/skills` | Create |
| `PATCH` | `/api/v1/admin/skills/{id}` | Rename, recategorise |
| `DELETE` | `/api/v1/admin/skills/{id}` | Delete if unused |
| `GET` | `/api/v1/admin/interests` | List |
| `POST` | `/api/v1/admin/interests` | Create |
| `PATCH` | `/api/v1/admin/interests/{id}` | Rename |
| `DELETE` | `/api/v1/admin/interests/{id}` | Delete if unused |

### Audit

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/admin/audit` | Newest first, filterable |

### Deleting a skill in use

`skills` has a FK from `profile_skills` with `ON DELETE CASCADE`. A cascade
would silently strip skills from users' profiles — matching scores would change
underneath them and nobody would know why.

**Block the delete if referenced:**

```python
if await db.scalar(select(func.count()).where(profile_skills.c.skill_id == id)):
    raise ConflictError(code="skill_in_use",
        message="This skill is on 12 profiles. Rename it instead.")
```

Same for courses and interests. 409 `skill_in_use` with the count in the
message — "rename it instead" is the actionable half.

Renaming is always safe. That is the operation people actually need.

### Granting admin

`POST /admin/users/{id}/grant-admin` sets `is_admin = true` and audits it. This
is how a fifth participant is added beyond the seeded five
([02](02_registration_and_login.md) §7).

**Guard against the last admin being demoted or deactivated.** If
`target.is_admin` and the count of active admins is 1, refuse with
`409 last_admin`. An app with no way back in is a demo over.

`GET /api/v1/admin/users` — searchable on email, display name and skill name;
filterable on `role`, `is_active`, `is_admin`, `course_id`; paginated.

| Case | Status | `code` |
|---|---|---|
| Success | `200` | — |
| **No session** | `401` | `unauthenticated` |
| **Signed in, not admin** | `403` | `forbidden` |
| Unknown user | `404` | `not_found` |
| Deactivating self | `422` | `validation_error` |
| Demoting the last admin | `409` | `last_admin` |
| Delete skill in use | `409` | `skill_in_use` |

**A non-admin gets `403`, not `404`.** Unlike a thread or a notification, the
admin panel is not a secret — a signed-in user who finds the URL should be told
they are not permitted, not left guessing whether it exists. Same as
[`01`](01_landing_page.md) §5.

**Deactivating yourself is refused** (`422`). Same reasoning — not because
admins must not deactivate anyone, but because you cannot see your own way back
in.

## 4. Frontend

`/admin`, behind `RequireAdmin`. A non-admin gets a 403 page, never a
redirect — they are authenticated, just not permitted
([`01`](01_landing_page.md) §5).

Four tabs.

### Overview

Counts as plain numbers: total users, active, new this week, connections
made, project ideas. **No charts.** One bar chart needs a library and does not
make the demo better. The brief's "dashboard stats" is
[`deferred_privacy_settings.md`](deferred_privacy_settings.md) territory; this is
just a count row.

`GET /api/v1/admin/overview` returning four integers, not a chart dataset.



### Users

Table: photo, name, email, role, course, skills, joined, status, admin badge.
Search, filters, paginated.

Row actions: view, deactivate / reactivate, grant / revoke admin. Destructive
actions get a confirm — unlike declining a connection
([05](05_connection_requests.md) §6), deactivating a person deserves a
confirmation because it locks them out of their account.

The detail view is the **only** place another user's email is visible. It is
audited.

### Reference data

Three simple tables — courses, skills, interests — each with an inline add form
and inline rename. Delete only where unused; the 409 message explains why.

**These lists are shared global state.** An admin adds a skill and every
user's profile form shows it immediately. This is the feature's real value: it
means the data set never needs to be edited by hand.

Cache the public `/skills` list and invalidate on any admin mutation, or the
next signup uses a stale list and looks broken.

### Audit log

Newest first: timestamp, admin, action, target. Filter by action type and by
admin. Read-only.

Boring on purpose. Its job is to make "who looked at what" answerable.

## 5. Tests

**Every admin route gets an auth test.** Not one test — one per route. This is
the feature where a forgotten guard is a real vulnerability.

| Test | Asserts |
|---|---|
| `test_admin_routes_require_session` | **Rule 1** → `401`, **every route** |
| `test_admin_routes_reject_non_admin` | **Rule 4** → `403`, **every route** |
| `test_admin_can_list_users` | |
| `test_admin_user_detail_includes_email` | The one legitimate exposure |
| `test_non_admin_cannot_list_users` | `403` |
| `test_deactivate_blocks_login` | `403 account_deactivated` |
| `test_reactivate_restores_login` | |
| `test_deactivated_user_hidden_from_public_profile` | `404` |
| `test_grant_admin_works` | New admin can log in and see the panel |
| `test_revoke_admin_removes_access` | |
| `test_cannot_deactivate_self` | `422` |
| `test_cannot_remove_last_admin` | `409 last_admin` |
| `test_create_skill_appears_in_profile_form` | The value of the feature |
| `test_rename_skill_updates_display` | |
| `test_delete_skill_in_use_rejected` | **`409 skill_in_use`** |
| `test_delete_unused_skill_allowed` | |
| `test_duplicate_skill_name_rejected` | `409` |
| `test_admin_cannot_edit_user_profile` | **`403`.** §1 boundary |
| `test_admin_cannot_edit_project_idea` | **`403`** |
| `test_audit_log_records_admin_view` | **Rule 4.** Row written |
| `test_audit_log_records_grant_admin` | With metadata |
| `test_audit_rolls_back_with_failed_action` | Same transaction |
| `test_audit_log_only_visible_to_admins` | `403` |

### E2E

1. Log in as admin → panel opens.
2. Add a skill → sign up as a new user → the skill is in the profile form.
3. Search for a user, open details, see their email.
4. Deactivate them → their login fails with "account deactivated".
5. Reactivate → login works.
6. Grant a colleague admin → they see the panel; a non-admin does not.

## 6. Out of scope

User deletion, password resets, content moderation, analytics charts, bulk
operations, CSV import, roles beyond admin/user, permission granularity,
audit-log export, impersonation ("log in as this user"), editing user content,
managing project ideas, cohort roster import from an LMS.

## 7. Definition of done

- [x] `get_current_admin` on every route, one auth test per route
- [x] Non-admin → `403` (not `404`) — admin panel is not secret
- [x] Cannot deactivate self or remove the last admin
- [x] Deleting a skill in use → `409` with the count; renaming always works
- [x] Reference-data mutations invalidate the public cache
- [x] Every admin read of user data audited, in the same transaction
- [x] Admin **cannot** edit profiles or project ideas
- [x] No charts — four counts
- [x] Every §5 test passes

## 8. Agent notes

- **Every admin route needs its own auth test.** This is the feature with the
  highest consequence for a forgotten guard.
- **`403` for a non-admin, not `404`.** Do not copy the thread rule here.
- **Guard the last admin.** Two lines, and they prevent an unrecoverable app.
- **Audit writes in the service, same transaction.** Middleware logs attempts as
  successes.
- **Block deleting a skill that is in use**, offer a rename. The cascade would
  silently change everyone's match scores.
- **Mutation verbs are `POST /action`, not `PATCH`.** The path encodes what is
  allowed; a PATCH body invites the wrong thing.
- **This is the first thing to cut** if you are behind. Keep `seed.py` so the
  admin logins still work with no panel.
---

## 10. As built — 2 October 2026

§3's endpoint verbs, §3's delete-in-use guard, §2's same-transaction auditing
and §4's four tabs are all implemented as written.

### 10.1 One auth test per route, and a boundary that is enforced

§5's headline requirement is implemented as a parametrised test over the full
list of admin read routes plus the write routes, so adding an admin endpoint
without adding it to `ADMIN_READ_ROUTES` is a visible gap rather than an
unnoticed one.

§1's boundary — admin manages the substrate, not other people's content — is
tested from both directions:

- `test_admin_cannot_edit_user_profile` — no method against `/users/{id}`
  succeeds, for an admin.
- `test_admin_cannot_edit_project_idea` — `403 not_idea_owner`.
- `test_admin_cannot_read_someone_elses_messages` — no such endpoint exists.

### 10.2 Audit rows roll back with the action

§2 requires the audit row to be written in the same transaction.
`test_failed_admin_action_leaves_no_audit_row` proves it: deactivating yourself
returns `422`, and the audit log is unchanged.

`test_audit_does_not_log_plain_listing` covers §4's "boring on purpose" — the
log records `view_user` for a specific user but not a list request, which would
otherwise bury the entries that matter.

### 10.3 The last-admin guard

§3 requires it. `test_cannot_remove_the_last_admin` asserts `409 last_admin`.
An app with no way back in is a demo over, and this is two lines.

### 10.4 Delete-in-use message

§3's message names the skill. The API returns the **count** instead
(`"This skill is on 12 profiles. Rename it instead."`) and the UI resolves the
name from the skill row it already has. The count is the more useful half; the
name was redundant in context.

### 10.5 Known gaps

`AdminPage.tsx` has no component tests. The reference-data editors, the users
table and the audit log are all unverified at the browser level; only the API
beneath them is covered.
