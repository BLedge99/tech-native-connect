# DEFERRED — Privacy settings, account deletion and data export

> **STATUS: NOT FOR THE DEMO. DO NOT BUILD.**
>
> A complete spec so it can be added later **without touching required code**.
> Not a roadmap task. See [`roadmap.md`](../roadmap.md) §Cut line.
>
> Source: the brief's suggested "Privacy settings: control who can see your
> profile or contact you", and the stretch goal "Account deletion and data
> export: a nod to GDPR".

---

## Why it is deferred

Two reasons, and the second matters more than the first.

**Product risk.** Every privacy setting multiplies the states of every screen.
Three visibility levels means profile pages, match lists, message headers and
notification lists all need a "you can see this but not that" rendering. That is
a combinatorial mess, and it is the kind of bug that only shows up in a live
demo.

**Product consequence.** A visibility setting with no enforcement anywhere else
is worse than no setting — it promises something the app does not deliver.

Both required surfaces (profile, messages) already enforce a single coherent
policy: *any signed-in cohort member can see your profile; only your connections
can message you.* Adding per-user overrides on top is easy. Removing them later
is not.

**This is the least reversible feature in the brief.** That is why it goes last.

## Dependency

Consumes, changes nothing:

- `profiles` ([03](03_profiles.md)) — three new boolean columns
- `users` ([02](02_registration_and_login.md)) — cascading delete target
- `get_current_admin` ([09](09_admin.md)) — for the moderation queue it enables

### The required-code constraint

Everything here is **additive**: new columns, new tables, new endpoints, one new
branch in the profile view. No required endpoint changes shape.

That constraint is the whole point of writing this spec now. When it is built,
if anyone has to edit `specs/04` or `specs/06` to make it work, this design was
wrong.

## Part 1 — Visibility settings

### New columns on `profiles`

| Column | Type | Default | Meaning |
|---|---|---|---|
| `discoverable` | `boolean` | `true` | Appear in `/matches` and search |
| `show_contact` | `boolean` | `true` | Show email to connections |
| `allow_messages` | `boolean` | `true` | Accept new connection requests |

Three booleans, not a three-valued enum. "Hidden" and "private" are different
questions, and an enum invites a fourth state nobody designed.

### Enforcement

| Setting | Where it is enforced |
|---|---|
| `discoverable = false` | Excluded from `GET /matches` ([04](04_matching_and_search.md) §5) and `/ideas` author lookup |
| `show_contact = false` | Omit `email` from the connection's user detail |
| `allow_messages = false` | `POST /connections` → `403 requests_disabled` |

**All three are enforced in the matching service, not in the router.** The
matching query already has a `NOT EXISTS` exclusion block
([04](04_matching_and_search.md) §5); `discoverable` joins it.

### The enforcement gap to watch

**A user who is already connected, then sets `discoverable = false`, still sees
existing connections.** Hiding is not disconnecting. Existing messages stay
readable.

This is the correct behaviour and it is the one people get wrong when
implementing. Write it in a comment.

### UI

`/settings/privacy` — three toggles with a one-line explanation each:

| Toggle | Help text |
|---|---|
| Discoverable | "Appear in suggestions and search." |
| Show contact | "Let people you've connected with see your email." |
| Allow messages | "Let other people send you connection requests." |

Each explains its effect plainly. **No privacy settings that need a lawyer to
read.** The GDPR-ish framing here is an acknowledgement, not compliance — do
not imply this app is GDPR compliant, because with SQLite-free local storage,
no consent records and no data-processing agreement, it is not.

## Part 2 — Account deletion and data export

The stretch goal. A nod at GDPR, not an implementation of it. Be honest about
that in any write-up.

### `POST /api/v1/users/me/export`

Returns a **JSON download** of everything tied to the user.

| Table | Included |
|---|---|
| `users` | Everything except the password hash |
| `profiles` | All fields |
| `photos` | Metadata, plus base64 `data` |
| `profile_skills`, `profile_interests` | Resolved to names, not ids |
| `connection_requests` | With the other party's name |
| `messages` | **Only messages the user sent.** Receiving party gets nothing |
| `project_ideas` | If the user authored any |
| `idea_interests` | Resolved |
| `notifications` | Received only |

**Sending another person's messages to a user is a data leak.** The export
covers rows where `sender_id = me`. It is not a full backup and does not claim
to be.

Build it as a `StreamingResponse` of incrementally serialised JSON rather than
building a giant dict in memory. Data export is exactly when a user might have
thousands of rows.

### `POST /api/v1/users/me/delete`

Requires password confirmation. Body: `{"password": "..."}` → `403` if wrong.

Deletion order, and the reason for it:

1. Verify password. **No password, no deletion.** This is the guard against
   someone who walks up to an unlocked laptop deleting an account.
2. Delete photos, interests, skills, connections, threads, messages, ideas,
   interests-in-ideas, notifications.
3. Delete `session` rows — the user is logged out.
4. Soft-delete the user row: `email` → `<deleted-id>@deleted.invalid`,
   `display_name` → "Deleted user", `password_hash` → random, `photo_id` → null,
   `is_active` → `false`.

**Step 4 is the decision worth arguing about.** Two options:

| Option | Pros | Cons |
|---|---|---|
| **A. Soft delete** | Other people's threads and ideas stay coherent; no broken references | Retains some data, so this is not "erasure" |
| **B. Hard delete** | Actually erases; GDPR-defensible | Cascades destroy other users' conversation history and their ideas |

**Recommendation: A, with B available on request via an admin.** Soft delete
keeps everyone else's content intact — Priya did not consent to Sam's deletion
erasing her messages. That argument is what makes A defensible, and it is worth
stating in the write-up.

If B is chosen, then other participants' messages must be replaced with
"[message deleted]" rather than cascaded away. Same principle.

### Self-service deletion is irreversible

No undo, no grace period, no soft-restore UI. Confirm twice (password plus an
explicit typed confirmation) and say so plainly. There is no support team.

## Part 3 — Enables a moderation queue

Blocking is specified separately in
[`deferred_safety_moderation.md`](deferred_safety_moderation.md). This file adds
the admin view that depends on it.

```sql
CREATE TABLE reports (
  id uuid PK, reporter_id uuid FK, reported_user_id uuid FK,
  reason report_reason, details varchar(500), status report_status,
  resolved_by uuid NULL, resolved_at timestamptz NULL,
  resolution varchar(200) NULL, created_at timestamptz
);
-- report_reason:  harassment | spam | inappropriate | impersonation | other
-- report_status:  open | actioned | dismissed
```

`GET /api/v1/admin/reports` lists open reports. `PATCH /api/v1/admin/reports/{id}`
records `actioned` or `dismissed` with `resolution`. **Never delete a report** —
an unresolved queue item and a dismissed report are different facts.

Deactivate the reported user as the resolution action; do not add a
suspend-until-date column unless asked.

## Endpoints summary

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/api/v1/users/me/export` | session + password confirm | JSON download |
| `POST` | `/api/v1/users/me/export` | session + password confirm | Same, `POST` for symmetry with delete |
| `POST` | `/api/v1/users/me/delete` | session + password | Delete account |
| `GET` | `/api/v1/users/me/privacy` | session | Read settings |
| `PATCH` | `/api/v1/users/me/privacy` | session | Update settings |
| `GET` | `/api/v1/admin/reports` | admin | Moderation queue |

Offer **both** `GET` and `POST` on export. A browser link prefetch would consume
a `GET`, and password confirmation is a `POST` body regardless.

## Tests

### Unit

| Test | Asserts |
|---|---|
| `test_discoverable_false_excluded_from_matches` | **The main integration** |
| `test_discoverable_false_still_shows_to_existing_connections` | **The gap people get wrong** |
| `test_show_contact_false_omits_email_from_connections` | |
| `test_allow_messages_false_blocks_requests` | `403 requests_disabled` |
| `test_visibility_settings_have_no_effect_on_your_own_profile` | |
| `test_export_excludes_password_hash` | **Never export it** |
| `test_export_includes_only_own_messages` | **The leak** |
| `test_export_resolves_ids_to_names` | Readable, not ids |
| `test_delete_requires_correct_password` | `403` |
| `test_delete_scrubs_personal_fields` | Email and display name |

### Integration

| Test | Asserts |
|---|---|
| `test_discoverable_false_hides_from_all_match_endpoints` | Including `/matches/{id}` |
| `test_hidden_user_still_reachable_by_direct_link` | **Or `404`. Pick one, test it** |
| `test_export_requires_session` | `401` |
| `test_delete_revokes_all_sessions` | Every session, not just the current |
| `test_deleted_user_cannot_login` | |
| `test_delete_preserves_other_users_messages` | **The soft-delete argument** |
| `test_privacy_settings_require_session` | `401` |
| `test_no_required_endpoint_changes_shape` | Regression guard for this file |

### E2E

Set `discoverable = false` → another user's match list no longer contains you →
you still see your existing conversation → restore. Export → download opens and
contains your data and not another's. Delete → logged out, cannot log back in,
the other user still sees their messages.

## Implementation notes

- **Three booleans, not an enum.** Four states nobody designed is worse than
  three states that are obvious.
- **Hidden ≠ disconnected.** Existing connections survive. Comment it.
- **Export sends messages only, never receives them.** This is the leak in this
  feature.
- **Never export the password hash.** Not hashed, not truncated — absent.
- **Deletion is irreversible.** Two confirmations, stated plainly.
- **Soft delete by default**, hard delete on admin request, with the reasoning in
  §2 above.
- **Build this last of anything.** It touches every screen and it is the only
  feature here that is genuinely hard to take back.

---

## As built — 2 October 2026

**Not built. Nothing in this file exists.** One finding worth recording, because
it changes what this feature would have to touch:

**The claim in §"The enforcement gap to watch" is real and was independently
rediscovered during implementation.** The profile page derived connection state
from `GET /matches`, which excludes anyone with a pending request — so a user
who had just sent one was shown as having no connection. That bug exists in the
current code and was fixed by reading state from `GET /connections` instead
(see [`04_matching_and_search.md`](04_matching_and_search.md) §13.2).

`discoverable = false` would have to be enforced in the **same place** — the
matching service's candidate query — for the same reason. There is now a
written precedent for where that goes.

No other part of this spec was built. The `reports` table in §Part 3 does not
exist.
