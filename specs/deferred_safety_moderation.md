# DEFERRED — Safety tools: block, report, moderation queue

> **STATUS: NOT FOR THE DEMO. DO NOT BUILD.**
>
> A complete spec so it can be added later **without touching required code**.
> Not a roadmap task. See [`roadmap.md`](../roadmap.md) §Cut line.
>
> Source: the brief's suggested "Safety tools: block and report users, plus an
> admin moderation queue."

---

## Why it is deferred

It is the most security-sensitive feature in the brief and it depends on three
features that must exist first: connections, messages, and admins.

Worse, it is easy to get *plausibly* wrong. A block that only hides the UI, or a
report queue that never surfaces anything, is worse than no feature at all — it
signals a safety capability the app does not have.

It is also the most likely to be probed as a stretch item. If asked, the honest
answer is: specced, deliberately not built in fourteen days, here is the design.

## Dependency

Requires, and reuses unchanged:

- `connection_requests` ([05](05_connection_requests.md)) — a block must close
  an accepted connection
- `messages` ([06](06_messaging.md)) — a block must stop delivery
- `notifications` ([07](07_notifications.md)) — the blocker must not be notified
- `get_current_admin` and `admin_audit_log` ([09](09_admin.md)) — the queue

## Part 1 — Blocking

### `blocks`

| Column | Type | Notes |
|---|---|---|
| `id` | `uuid` PK | |
| `blocker_id` | `uuid` FK → `users.id` | Who blocked |
| `blocked_id` | `uuid` FK → `users.id` | Who was blocked |
| `reason` | `varchar(300)` nullable | Never shown to the blocked user |
| `created_at` | `timestamptz` | |

Constraints:

```sql
CHECK (blocker_id <> blocked_id)
CREATE UNIQUE INDEX one_block_per_pair ON blocks (
  LEAST(blocker_id, blocked_id), GREATEST(blocker_id, blocked_id)
);
```

**The same pattern as connections** ([05](05_connection_requests.md) §1), and the
same reason: a `SELECT`-before-`INSERT` race is not a constraint.

**Blocking is one-directional.** The blocked user is not told, and their match
list is unchanged. Symmetric blocking would require every read to check both
directions — and it leaks information, because the blocked user could infer
something from the asymmetry. One row, one direction, checked on every read
path that could surface the blocker.

### What a block does, everywhere

This is the whole feature. Miss one of these and a block is decorative.

| Surface | Behaviour |
|---|---|
| `/matches` | Blocker is not excluded; **blocked user's** results exclude the blocker |
| `/users/{id}` | `404`, not `403`. A blocker must not know they are blocked |
| `POST /connections` | `403 blocked_by_user` |
| Accepted connection | **Closed.** Status → `declined`, reason recorded as blocked |
| `/threads/{id}` | `403` both directions. The blocker cannot see their own history either |
| `POST .../messages` | `403` |
| Existing messages | **Retained**, not deleted. Deleting them deletes the blocker's copy too |
| Notifications | Blocked user's events no longer reach the blocker |
| `/ideas` | Blocked user's ideas hidden from the blocker only |
| Search / filters | Blocked user never appears |

### The two mistakes, named

1. **Hiding in the UI only.** A block that greys out a card but leaves the API
   open is not a block. Every check goes in the **service layer**, or in a
   shared `apply_block_filters(query, user_id)` helper used by every read path.
2. **Telling the blocked user.** "You have been blocked by Priya" confirms the
   block exists and gives a harassment target a reason to try again.
   `404` on the profile. Silence everywhere else.

### Blocking closes the connection

Blocking an accepted connection sets it to `declined` with an internal reason of
`blocked`, and deletes the `threads` row? **No** — keep the messages. Delete the
thread row and `messages` cascades, destroying the blocker's own history
because of the other person's action. That is a real bug people ship.

Correct: set the connection to `declined` with `reason = 'blocked'`, close the
thread to access, **retain the message rows**.

The blocker loses access. The data stays until the blocker deletes their own
account ([`deferred_privacy_settings.md`](deferred_privacy_settings.md)).

## Part 2 — Reporting

### `reports`

Defined in [`deferred_privacy_settings.md`](deferred_privacy_settings.md) §3,
repeated here for standalone use.

| Column | Type | Notes |
|---|---|---|
| `id` | `uuid` PK | |
| `reporter_id` | `uuid` FK → `users.id` | Who reported |
| `reported_user_id` | `uuid` FK → `users.id` | Who was reported |
| `reason` | enum | `harassment`, `spam`, `inappropriate`, `impersonation`, `other` |
| `details` | `varchar(500)` nullable | |
| `status` | enum | `open`, `actioned`, `dismissed` |
| `resolved_by` | `uuid` nullable | Admin |
| `resolved_at` | `timestamptz` nullable | |
| `resolution` | `varchar(200)` nullable | What was done |
| `created_at` | `timestamptz` | |

Indexes: `(status, created_at DESC)` for the queue, `(reported_user_id)` for
"has this person been reported before".

### Rules

| Rule | Enforcement |
|---|---|
| Cannot report yourself | `422` |
| Cannot report someone you blocked | `422`. Block is the stronger action |
| Duplicate open report by the same reporter | `409 already_reported` |
| **Reported user is never told** | No notification, ever |
| `details` never shown to the reported user | Admin-only |
| Reports are never deleted | Resolution is a status, not a deletion |

**Reporters are anonymous to the reported user, always.** There is no "you were
reported" notification and no count on their profile. Reporting someone because
they are active on the platform should not expose the reporter.

A reporter must be able to see their own report's status — otherwise "report"
is a black hole and people report less. `GET /reports/mine`, their reports only.

### Block *or* report, not both required

Offer both from the same menu. Reporting without blocking lets a user flag a
pattern without cutting contact; blocking without reporting lets someone just
cut a person off. Forcing both would be paternalistic and would suppress
reporting.

## Part 3 — Admin moderation queue

### Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/api/v1/admin/reports` | admin | Open reports, newest first |
| `GET` | `/api/v1/admin/reports?status=` | admin | Filter |
| `GET` | `/api/v1/admin/reports/{id}` | admin | Full detail, reporter identity |
| `PATCH` | `/api/v1/admin/reports/{id}` | admin | `actioned` / `dismissed` + resolution |
| `GET` | `/api/v1/reports/mine` | session | The caller's own reports |

`PATCH` body:

```jsonc
{ "status": "actioned", "resolution": "Deactivated account pending review" }
```

**Resolution text is required when actioning, optional when dismissing.** A
report closed with no explanation teaches admins nothing and leaves the reporter
with no idea what happened.

### Available actions

**Deactivation only** ([09](09_admin.md) §3). Do not add per-report suspension,
warnings, or a strike system. Deactivation is reversible; a warning system built
on top of it is not, and a botched warning is unrecoverable.

### Queue ordering

Open reports, newest first. Show the reported user's **total report count** —
three reports on one account is a pattern, and it is the reason to look. Group
by reported user if volume ever warrants it. Do not build it now.

### The reporter sees a resolution, or nothing

When a report is actioned, the reporter gets one notification: "Your report was
reviewed." **Never what action was taken, and never the outcome for the other
user.** Disclosing the resolution exposes the moderation process and invites
appeals against a process they cannot see.

## Endpoints — user-facing

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `POST` | `/api/v1/users/{id}/block` | session | Block |
| `DELETE` | `/api/v1/users/{id}/block` | session | Unblock |
| `GET` | `/api/v1/users/{id}/block` | session | Did **I** block them |
| `GET` | `/api/v1/blocks` | session | Users I blocked |
| `POST` | `/api/v1/users/{id}/report` | session | Report |

`GET /users/{id}/block` returns whether the *caller* blocked them. It must not
reveal whether they blocked the caller.

## Tests

This feature has the highest ratio of security tests to code in the project.
Every row matters.

### Unit

| Test | Asserts |
|---|---|
| `test_cannot_block_self` | `422` |
| `test_duplicate_block_rejected` | `409` |
| `test_cannot_report_self` | `422` |
| `test_cannot_report_blocked_user` | `422` |
| `test_duplicate_open_report_rejected` | `409` |
| `test_block_closes_accepted_connection` | Status → `declined` |
| `test_block_retains_message_rows` | **The cascade bug.** Messages survive |
| `test_unblock_does_not_restore_connection` | Deliberate. One-way |
| `test_blocked_user_not_notified` | **The disclosure rule** |
| `test_blocked_user_sees_404_not_403` | **Existence not confirmed** |

### Integration

| Test | Asserts |
|---|---|
| `test_blocked_user_absent_from_all_match_endpoints` | `/matches`, `/matches/{id}`, `/ideas` |
| `test_blocked_user_absent_from_search` | |
| `test_blocked_user_profile_404s_for_blocker` | Not `403` |
| `test_blocked_user_does_not_appear_in_connections` | |
| `test_blocked_pair_cannot_read_thread` | Both directions |
| `test_blocked_pair_cannot_send_messages` | `403` |
| `test_block_prevents_new_connection_requests` | `403 blocked_by_user` |
| `test_block_status_endpoint_is_caller_scoped` | No reverse disclosure |
| `test_reports_require_session` | `401` |
| `test_reports_list_is_admin_only` | `403` |
| `test_reported_user_receives_no_notification` | |
| `test_reporter_sees_status_but_not_resolution` | |
| `test_reporter_notified_only_on_action` | Not on dismissal |
| `test_audit_log_records_admin_resolution` | |
| `test_report_never_deleted_on_resolution` | Status only |
| `test_action_requires_resolution_text` | `422` |

### E2E

A blocks B → B's profile 404s for A → B absent from A's matches → A's existing
thread with B is closed → **B has no idea** (no notification, B's own list is
unchanged) → A unblocks → A's match list is unchanged, the connection stays
closed. Report C → appears in the admin queue → admin deactivates C → A is told
"reviewed" and nothing more.

## Implementation notes

- **One-directional block.** Never symmetric.
- **Block filters go in the service layer, or in a shared helper every read path
  calls.** The single most likely bug in this feature is a new endpoint that
  forgets the filter.
- **`404` on the profile, silence everywhere else.** Never tell the blocked user.
- **Never cascade-delete messages.** The blocker's copy is destroyed too.
- **Deactivation is the only enforcement action.** Do not build warnings.
- **Reporters see status, never outcome.**
- **Reports are resolved, never deleted.**

## If asked about it in the demo

Honest answer: "Blocking and reporting are specced and deliberately not built —
we had two weeks and it depends on connections, messaging and admin all being
solid. The design is in `specs/deferred_safety_moderation.md`, and the key rule
is that a block is enforced in the service layer, not just hidden in the UI."

That is a better answer than a half-built report button.