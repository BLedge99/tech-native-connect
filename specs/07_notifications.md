# 07 — Notifications

**Goal:** tell someone something happened, in the app, once, and let them know
how many unread things they have.

**Depends on:** [05 — Connection requests](05_connection_requests.md),
[06 — Messaging](06_messaging.md)
**Blocks:** nothing. This is triggered by 05 and 06.

**Implementation status:** Not started.

---

## 1. Scope

| In | Out |
|---|---|
| In-app bell with unread badge | Email notifications |
| List, mark read, mark all read | Push notifications |
| Live toasts over the existing WebSocket | SMS |
| Four trigger events | Notification preferences per user |
| | Notification grouping or digests |

### In-app only — and this is the whole ADR

The brief lists "notifications: alerts for new matches, messages and
requests". It does not say email. In-app is the demo-friendly reading: no
queue, no templates, no delivery failure mode, and it shows up live over a
socket we already have.

Email would need a background job (an HTTP request must not wait on SMTP), a
template per notification type, bounce handling, and a Mailpit-delivered test
for each. All of that for something nobody sees in the demo.

**"New matches" does not get a notification.** Read that requirement again:
we do not run a matching job that produces matches on a schedule, so there is
no event to notify on. When a user finishes their profile they get matches on
the next page load — which the app can show directly. Notifying them about
something they are about to see is noise. There is a mock matcher in
[04](04_matching_and_search.md) territory but no cron, no queue, and no
notification. If someone wants daily match emails, that is the deferred AI
feature's job, not this one's.

## 2. Data model

### `notifications`

| Column | Type | Notes |
|---|---|---|
| `id` | `uuid` PK | |
| `user_id` | `uuid` FK → `users.id` | **Recipient.** `ON DELETE CASCADE` |
| `type` | enum | Four values, §3 |
| `actor_id` | `uuid` FK → `users.id` nullable | Who caused it. **Not** the recipient |
| `connection_request_id` | `uuid` FK nullable | For connection types |
| `thread_id` | `uuid` FK nullable | For message type |
| `project_idea_id` | `uuid` FK nullable | For idea types |
| `data` | `jsonb` | Snapshot of display strings, §5 |
| `read_at` | `timestamptz` nullable | `NULL` = unread |
| `created_at` | `timestamptz` | |

```sql
CREATE TYPE notification_type AS ENUM (
  'connection_requested', 'connection_accepted', 'connection_declined',
  'new_message', 'idea_interest'
);
```

Indexes:

- `(user_id, read_at, created_at DESC)` — **covers the unread count and the
  list.** The partial index below makes the count cheap.

```sql
CREATE INDEX idx_notifications_unread ON notifications (user_id, created_at DESC)
  WHERE read_at IS NULL;   -- ponytail: partial index; unread is a small slice
```

A partial index on `read_at IS NULL` is the right call because unread is a tiny
fraction of a user's notifications and the count query runs on every page load
via the bell. Deeper in the stack it is just an index on `user_id` with a
`WHERE`.

### Notification rows are immutable

No updates, no deletes except a cascade when the user is deleted. Only
`read_at` changes, and only from `NULL` to a timestamp.

There is no edit endpoint for a notification and there should never be one. A
notification is a record that something happened; if the thing it describes is
deleted, the notification stays and its link 404s. That is honest.

### Store display strings, not just ids

`data` holds `"actor_name": "Priya"`, `"actor_photo_url": "/api/v1/users/…/photo"`.

Without this, every notification render joins four tables and the list endpoint
becomes an N+1. With it, the list is one query. **The cost is a stale name** if
someone renames themselves, which is acceptable for a notification that is
usually seconds old.

## 3. The five events

Every event names its recipient. Getting that backwards means users get
notified about their own actions.

| Event | Fires when | Recipient | Actor | Also |
|---|---|---|---|---|
| `connection_requested` | Request created | **Receiver** | Sender | |
| `connection_accepted` | Request accepted | **Sender** | Acceptor | |
| `connection_declined` | Request declined | **Sender** | Acceptor | |
| `new_message` | Message persisted | **The other participant** | Sender | Socket broadcast |
| `idea_interest` | Interest expressed | **Idea author** | Interester | |

### Create notifications in the service that caused the event

Not in a background job, not in a signal handler. `[05](05_connection_requests.md)`
§5 already specifies this for connection transitions; same for messages and
ideas.

A background job would need a queue — Redis, Celery, or an in-process `asyncio`
queue — for a table insert and a socket broadcast. That is a whole new failure
surface for no benefit, and it would make the demo's live notification
eventually consistent, which means the notification arrives after the UI has
already updated. **Synchronous insert, then push.** The request is already
authenticated and the insert is sub-millisecond.

### Never notify about your own action

Every trigger has `actor_id != user_id` as a precondition. Enforce it in the
service helper so it is true by construction:

```python
def notify(user_id: UUID, type: NotificationType, *, actor_id: UUID | None, **data):
    if actor_id == user_id:
        return   # you do not notify yourself about your own action
```

One guard covers all five events. Without it, sending a message notifies you
that you sent a message, which is how a bell badge ends up permanently
non-zero.

### Fire exactly once

Guard on state, not on a "have we notified?" flag:

| Event | Guard |
|---|---|
| `connection_requested` | Row just inserted |
| `connection_accepted` / `declined` | `responded_at IS NULL` before the update |
| `new_message` | Row just inserted, recipient ≠ sender |
| `idea_interest` | `ideas_interests` has no row for this pair (enforced by unique index) |

Idempotency by precondition, not by a `notified` boolean. A flag is a second
source of truth that can desynchronise from the state it mirrors.

### `new_message` and the WebSocket

A message notification exists for the **badge and history**. The live delivery
is the message broadcast itself ([06](06_messaging.md) §4) — the client
receives the message, knows the thread is unread, and can toast "New message
from Priya" without a second socket frame carrying the same message.

**Do not send both a `message` frame and a `notification` frame for the same
event.** The recipient's client would toast twice. One path: the `message`
frame, from which the client derives the toast and bumps the badge locally.

### `new_message` volume

A fast typist sends 20 messages and the receiver gets 20 rows and 20 toasts.
Debounce toasts on the client: collapse toasts with the same `actor_id` within
5 seconds into one, "Priya sent 3 messages".

**Do not skip persisting messages.** A row per message is what makes the unread
count honest and the history correct. Debouncing is a client rendering concern,
not a storage one.

## 4. Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/api/v1/notifications` | session | List, newest first |
| `GET` | `/api/v1/notifications/unread-count` | session | Badge number |
| `GET` | `/api/v1/notifications/{id}` | session | One |
| `PATCH` | `/api/v1/notifications/{id}` | session | Mark read |
| `PATCH` | `/api/v1/notifications/read-all` | session | Mark all read |
| `DELETE` | `/api/v1/notifications/{id}` | session | Delete one |
| `DELETE` | `/api/v1/notifications` | session | Clear all |

### `GET /notifications`

`?limit=` (default 20, max 100), `?cursor=`, `?unread_only=` (bool).

```jsonc
{
  "items": [{
    "id": "…", "type": "connection_requested",
    "read_at": null,
    "created_at": "2026-10-09T09:00:00Z",
    "data": {
      "actor_name": "Priya", "actor_photo_url": "/api/v1/users/…/photo",
      "connection_request_id": "…", "thread_id": null, "project_idea_id": null
    },
    "url": "/connections"       // where clicking goes
  }],
  "next_cursor": "…",
  "unread_count": 3
}
```

**`unread_count` in the list response.** The bell renders from the same call as
the list, so they cannot disagree — the bug where the badge says 3 and the list
shows 1 unread disappears structurally.

### `GET /notifications/unread-count`

```jsonc
{ "unread_count": 3 }
```

For a fast badge poll. Separate from the list deliberately: the header renders
before the route's data has loaded, and one integer is a much cheaper poll than
a page of JSON.

### `PATCH /notifications/{id}`

`{ "read": true }` → `200`. Idempotent — marking an already-read notification
returns `200`, not `409`.

Marking an already-read notification read is not a conflict. The user pressed
the button twice because the button was slow; `409` for that is hostile.

`PATCH /notifications/read-all` → `204`. Only `read_at IS NULL` rows, so
already-read notifications keep their original timestamp. That timestamp is the
order of the list.

### Authorisation

Every notification is scoped to its `user_id`:

| Case | Status | `code` |
|---|---|---|
| Success | `200` / `204` | — |
| No session | `401` | `unauthenticated` |
| **Someone else's notification** | `404` | `not_found` |

**`404`, not `403`.** Confirming that notification #123 exists and belongs to
someone else leaks the user's activity. Every notification query is filtered by
`user_id` in the `WHERE`, not checked after fetching — the check-after-fetch
pattern is how one row leaks into a response.

## 5. Render strings

The `data` snapshot carries display strings; **the client renders them.** No
server-side templates per type, no nested switch in the frontend that can
disagree with the backend.

`url` is computed server-side and is a **relative path only** — never a full
URL, and never derived from user input. A notification whose `url` is
user-controllable would be an open-redirect vector on a page a user trusts.
Validate that it starts with `/` and is not `//` before storing.

```jsonc
"connection_requested": "Priya wants to connect",
"connection_accepted":  "Priya accepted your request",
"connection_declined":  "Priya declined your request",
"new_message":          "Priya sent you a message",
"idea_interest":        "Sam is interested in your idea \"Carbon-aware logistics\""
```

The last one embeds a user-supplied title, so the frontend renders it as text
inside a string template. React escapes by default, which is sufficient. Do not
build it as HTML.

## 6. Frontend

### The bell

Header component, visible only when logged in. Red badge with the unread count,
capped display at `99+`. Dropdown panel showing the latest 10, "Mark all read",
and a "See all" link to `/notifications`.

**Poll `/unread-count` on route change** and invalidate on any mutation. Do not
poll on a timer — a fixed interval keeps firing on the notification page itself
for no reason.

### Live toasts

Arriving over the existing socket ([06](06_messaging.md) §4), bottom-right,
auto-dismiss after 5 s, click to navigate.

Debounce by `actor_id` within 5 s (§3). Suppress toasts for the tab that is
currently focused on the target route — a toast for the conversation you are
already reading is pure noise.

**Toasts must never fire for your own actions** (§3). The client checks
`actor_id !== me.id` as well, because belt-and-braces on the client is one
line and the failure is embarrassing in a live demo.

### `/notifications` — the list

Grouped by day: **Today**, **Yesterday**, **Earlier**. Unread rows have a dot
and bold text; clicking marks read and navigates. Read rows are muted.

Clicking behaviour, in order: mark read → navigate to `url` → invalidate the
list and the count. Sequential, and each step must complete — navigating first
means the bell is briefly wrong on the destination page.

Empty state: "You're all caught up." Not an error, and it should look like one.

## 7. Tests

### Unit — `services/notifications.py`

| Test | Asserts |
|---|---|
| `test_notify_ignores_self_actions` | **`actor_id == user_id` → no row** |
| `test_unread_count_excludes_read` | |
| `test_unread_count_zero_when_none` | |
| `test_mark_read_sets_read_at` | |
| `test_mark_read_twice_does_not_overwrite` | **Idempotent** |
| `test_mark_read_all_skips_already_read` | Original timestamps kept |
| `test_connection_accepted_fires_once` | **The double-fire guard** |
| `test_url_must_be_relative` | `//evil.com` rejected |
| `test_message_notification_targets_recipient_not_sender` | |

### Integration

| Test | Asserts |
|---|---|
| `test_list_requires_session` | **Rule 1** → `401` |
| `test_cannot_read_another_users_notification` | **`404`** |
| `test_cannot_mark_another_users_notification_read` | **`404`** |
| `test_cannot_delete_another_users_notification` | **`404`** |
| `test_list_only_returns_own_notifications` | No leakage |
| `test_unread_count_matches_list` | **Badge arithmetic** |
| `test_request_creates_notification_for_receiver` | Not the sender |
| `test_accept_creates_notification_for_sender` | Exactly one |
| `test_double_accept_creates_no_second_notification` | |
| `test_message_creates_notification_for_recipient` | Not the sender |
| `test_idea_interest_creates_notification_for_author` | |
| `test_url_is_relative_in_every_notification` | **Open-redirect guard** |

### E2E

1. Two users. A sends B a request → **B's badge shows 1 live, no refresh.**
2. B opens notifications → navigates → badge clears.
3. B accepts → **A's badge shows 1.**
4. A and B exchange a message → a toast appears on the other side.
5. Mark all read → badge empties, reload stays empty.

## 8. Out of scope

Email, push, SMS, per-type preferences, notification grouping beyond the day
headers, notification search, archiving, read receipts beyond a read cursor,
notifications for new matches (see §1), notification for follows.

## 9. Definition of done

- [ ] Five enum values, all five events firing for the correct recipient
- [ ] `actor_id == user_id` short-circuits — tested
- [ ] Every trigger fires exactly once, guarded on state not a flag
- [ ] Another user's notification → `404`, not `403`
- [ ] `unread_count` returned with the list — badge cannot disagree
- [ ] No duplicate message broadcast + notification toast
- [ ] Toast debouncing by `actor_id`
- [ ] `url` validated as relative
- [ ] Every §7 test passes

## 10. Agent notes

- **"New match" notifications are deliberately absent.** Read §1 before
  "implementing" that requirement.
- **Insert the row synchronously.** No queue, no job. The demo needs it
  immediately and consistency is easier to reason about.
- **Get the recipient backwards at your peril.** Sender-vs-receiver is wrong in
  a way tests catch but a demo does not, until a user's own action notifies
  them.
- **Filter by `user_id` in the `WHERE`.** Fetch-then-check leaks.
- **`unread_count` in the list response** removes a whole class of badge bugs.
- **Debounce toasts on the client only.** Never skip storing messages.