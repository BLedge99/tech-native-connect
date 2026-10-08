# 06 — Messaging

**Goal:** two connected people exchange messages, live, with no refresh. This
is the payoff of the whole loop and the part most likely to break live.

**Depends on:** [05 — Connection requests](05_connection_requests.md)
**Blocks:** [07 — Notifications](07_notifications.md)

**Implementation status:** Implemented 2 Oct 2026 — see the *As built* note at the end of this document for deviations from the spec.

---

## 1. Scope

| In | Out |
|---|---|
| Private 1:1 threads, one per accepted pair | Group threads, DMs |
| Live delivery over WebSocket | Message history search |
| Persistence across restarts | Typing indicators, read receipts |
| Unread counts per thread | Attachments, images, emoji picker |
| Reconnect with backoff | Message edit, delete, reactions |
| Optimistic send | Push notifications |

### The rule that matters

**`AGENTS.md` §5 rule 2: a thread opens only when both people have accepted.**

Two independent checks, both mandatory:

1. The connection is `status = 'accepted'`.
2. The requester is a participant.

Every endpoint and every WebSocket action enforces both. Faking a `thread_id`
in the URL must not grant access. One-sided access is a data leak, and this is
the endpoint where that leak actually leaks.

## 2. Data model

### `threads`

| Column | Type | Notes |
|---|---|---|
| `id` | `uuid` PK | |
| `connection_request_id` | `uuid` FK → `connection_requests.id` | Unique. One thread per accepted connection |
| `created_at` | `timestamptz` | |

Unique on `connection_request_id`, so double-creation is impossible even if two
requests race.

**No `participant_a` / `participant_b` columns.** Participants are derived from
the connection request. Duplicating them means two sources of truth, and the
divergence is a permissions bug.

### `messages`

| Column | Type | Notes |
|---|---|---|
| `id` | `uuid` PK | `gen_random_uuid()` |
| `thread_id` | `uuid` FK → `threads.id` | `ON DELETE CASCADE` |
| `sender_id` | `uuid` FK → `users.id` | |
| `body` | `text` | 1–2000 chars |
| `created_at` | `timestamptz` | UTC |

Indexes:

- `(thread_id, created_at, id)` — **the pagination index.** Without `id` as a
  trailing tiebreaker, messages with identical timestamps at a millisecond
  boundary repeat across pages.
- `sender_id`

### `read_receipts`

| Column | Type | Notes |
|---|---|---|
| `thread_id` | `uuid` FK | Composite PK with `user_id` |
| `user_id` | `uuid` FK | |
| `last_read_at` | `timestamptz` | |

Composite PK `(thread_id, user_id)` makes one row per participant. One row is
not "a read receipt" — it is a read cursor, which is a different and much more
useful thing.

### Read state, precisely

A message is unread for user U if:

- `sender_id != U`, **and**
- `created_at > U.read_receipt.last_read_at` (absent receipt = all messages
  unread), **and**
- it arrived after U's thread join.

The third clause is the subtle one. If the sender sends three messages while U
has the tab closed, and U opens the thread, the read cursor jumps to "now" and
**all three are read**. Anything else shows U three unread messages about a
conversation they are currently reading — obviously wrong.

On `GET /messages`, mark everything read up to `now` and return
`last_read_at` in the response. Read receipt and fetch in one round trip; a
separate `POST /read` endpoint is an extra request for something the page load
already knows.

## 3. Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/api/v1/threads` | session + participant | The caller's threads |
| `GET` | `/api/v1/threads/{id}` | session + participant | One thread |
| `GET` | `/api/v1/threads/{id}/messages` | session + participant | Paginated history |
| `POST` | `/api/v1/threads/{id}/messages` | session + participant | Send |
| `POST` | `/api/v1/threads/{id}/read` | session + participant | Mark read |
| `GET` | `/api/v1/threads/{id}/messages/unread-count` | session + participant | Poll fallback |
| `WS` | `/api/v1/ws` | session | Live channel |

**Every path-scoped endpoint checks `require_participant(thread_id,
current_user)`,** and that check covers both §1 conditions. Declared once as a
FastAPI dependency, never reimplemented per route.

### `GET /threads`

Only threads where the user is a participant **and** the connection is
`accepted`. Returns the other party's summary, last message preview, unread
count, `last_message_at`.

```jsonc
{
  "items": [{
    "id": "…",
    "other": { "id": "…", "display_name": "Priya", "has_photo": true, "photo_url": "…" },
    "last_message": { "body": "Sounds good", "sender_id": "…", "created_at": "…" },
    "unread_count": 2,
    "last_message_at": "2026-10-09T14:22:00Z"
  }],
  "next_cursor": null
}
```

Sorted `last_message_at DESC NULLS LAST` — most recent conversation first. A
thread with no messages cannot exist (lazy creation,
[05](05_connection_requests.md) §5), so `NULLS LAST` is belt-and-braces.

### `GET /threads/{id}/messages`

`?limit=` (default 50, max 200) and `?cursor=`. Returns **newest-first** pages
with `next_cursor` pointing further back — the chat opens at the bottom, which
is where the newest message is.

| Case | Status | `code` |
|---|---|---|
| Success | `200` | — |
| No session | `401` | `unauthenticated` |
| Not a participant | `404` | `not_found` |
| **Connection not accepted** | `403` | `connection_not_established` |
| Unknown thread | `404` | `not_found` |

**A non-participant gets `404`, not `403`.** Someone else's private thread
should not be confirmed to exist. The `403 connection_not_established` case is
for a genuine participant whose thread exists but whose connection was somehow
not accepted — a state that should be unreachable, kept as defence in depth.

Mark-as-read happens on this call (§2).

### `POST /threads/{id}/messages`

```jsonc
{ "body": "Want to pair on the fintech idea?" }  // 201
{ "id": "…", "thread_id": "…", "sender_id": "…", "body": "…", "created_at": "…" }
```

`1 ≤ len(body) ≤ 2000` after trimming. Empty or whitespace-only → `422`.
Same auth as read, including `403 connection_not_established`.

**The response is the created message.** The client already has the body and
id from its optimistic render, and it also lets a client that skipped
optimism still work.

### `POST /threads/{id}/read`

`204`, sets `last_read_at = now()`. Exists for a client that wants to clear a
badge without refetching history — the mobile-shaped case, and it keeps the
nav badge correct when a thread is opened in a background tab.

### `GET /threads/{id}/messages/unread-count`

Poll-only fallback when the WebSocket is down. The WebSocket is the primary
mechanism; this exists so a broken socket degrades to refreshable rather than
blind.

## 4. Realtime

### Protocol

Native WebSocket at `/api/v1/ws`, authenticated with the session cookie during
the handshake. One socket per tab, multiplexed by topic. No `socket.io`, no
`pusher`, no topic broker —
[ADR 0005](../decisions/0005-websocket-in-process.md).

| Direction | Message | Shape |
|---|---|---|
| C→S | `subscribe` | `{"type":"subscribe","thread_id":"…"}` |
| C→S | `unsubscribe` | `{"type":"unsubscribe","thread_id":"…"}` |
| C→S | `send_message` | `{"type":"send_message","thread_id":"…","body":"…","client_id":"…"}` |
| S→C | `message` | `{"type":"message","data":{…message…}}` |
| S→C | `notification` | `{"type":"notification","data":{…notification…}}` |
| S→C | `error` | `{"type":"error","code":"…","message":"…"}` |

`client_id` is a client-generated UUID for the optimistic message. The server
echoes it back on the broadcast, which is how the sender recognises its own
message and reconciles instead of duplicating.

### Subscriptions, not broadcasting everything

A client subscribes to the threads it has open. The server rejects a
subscription to a thread the caller does not participate in, with
`{"type":"error","code":"forbidden"}` — **the same authorisation check as the
HTTP endpoints, on the socket path.** A WebSocket is a long-lived bypass
otherwise, and this is the most likely place for that hole to appear.

Notifications ([07](07_notifications.md)) arrive on the socket as a
server-push on the user's own user topic, with no client subscribe.

### Connection registry

In-process: `user_id → set[WebSocket]` and `thread_id → set[WebSocket]`.

```python
# ponytail: in-process registry, single uvicorn worker. Correct for one
# backend container. Upgrade path: Redis pub/sub + a subscriber per worker,
# which changes ConnectionManager's internals only — the send/broadcast API
# stays the same.
```

Single worker is a hard requirement of this design, and it must be set in the
compose file or two workers will each hold half the sockets and messages will
vanish intermittently. Write that in the compose file comment now, before
someone scales it in production and loses an afternoon.

### `send_message` over the socket

The path that needs the most care:

1. Validate `thread_id` and `body`.
2. **`require_participant`** — send an `error` frame and drop, or reject.
3. Persist the message.
4. Broadcast to every subscriber of the thread **except** the sender's socket
   for that thread — the sender already has it optimistically.
5. Send an `ack` with the saved message including `client_id` to the sender's
   socket.

The exclusion in step 4 is what makes optimistic UI correct. Broadcast to
everyone including the sender and the sender's message appears twice.

**Persist first, then broadcast.** Broadcasting a message that failed to save
means two users see it and it vanishes on refresh.

### Reconnection

Client, with exponential backoff: 1 s, 2 s, 4 s, 8 s, 16 s, capped at 30 s,
with jitter. Retry indefinitely; this is a demo and giving up is worse than
retrying.

On reconnect: fetch `/threads/{id}/messages` with `?after=<last_seen>` to
catch anything missed while disconnected, then resubscribe. Durable replay —
the server does not queue for offline clients.

**Duplicate suppression:** the client dedupes on message `id`. Replaying after
a reconnect overlaps slightly with optimistic messages still in flight; without
id-based dedupe, users see duplicates. Tested.

### Failure modes

| Failure | Behaviour |
|---|---|
| Backend restarts | Client reconnects with backoff, refetches, no duplicates |
| Socket down | Poll the unread-count endpoint; send via `POST`, still works |
| Socket dies mid-send | Optimistic message stays; reconciliation on reconnect |
| Backend unreachable | Send is queued in the client, retried on reconnect |

**Sending does not depend on the socket.** Always `POST` the message; the
socket is for *receiving* live. A client that could only send over the socket
would lose messages whenever it dropped. Using `send_message` over the socket
is an optimisation for latency, with `POST` as the fallback.

## 5. Frontend

### `/messages` — thread list

Grouped by recency. Each row: photo, name, last message preview (truncated,
their messages left-aligned), timestamp, unread badge. Unread in bold.

Empty state: "No conversations yet. Send a connection request to start one."
**With a link to `/matches`.** An empty message list after connecting with
people looks like a bug; a link makes it a next step.

### `/messages/:threadId` — chat view

- Header: photo, name, link to profile.
- Scrollable message list, newest at the bottom.
- Composer at the bottom: textarea, Enter to send, Shift+Enter for a newline.
- Send button disabled while the body is empty.
- Character counter at 2000.

**Scroll behaviour matters more than it sounds.** On open, scroll to the bottom
after layout. If the user has scrolled up, do **not** yank them down when a new
message arrives — show a "new message" pill instead. Yanking the scroll position
mid-conversation is the most annoying thing a chat UI can do, and it is
immediately visible in a demo.

**Scroll to bottom when you send**, always. Only auto-scroll on *incoming*
messages when already at the bottom.

### Optimistic send

```tsx
function sendMessage(body: string) {
  const clientId = crypto.randomUUID();
  const optimistic = { id: clientId, body, sender_id: me.id,
                       created_at: new Date().toISOString(), pending: true };
  setMessages(m => [...m, optimistic]);        // 1. render immediately
  try {
    const saved = await api.post(`/threads/${id}/messages`, { body });
    setMessages(m => m.map(x => x.id === clientId ? saved : x));  // 2. reconcile
  } catch (e) {
    setMessages(m => m.filter(x => x.id !== clientId));          // 3. roll back
    toast("Message not sent");
  }
}
```

Mark pending messages visually — reduced opacity, no timestamp. On failure,
roll back and toast. Never silently drop a message.

**Reconcile by `id`, not by position or body.** Two identical messages in a row
are two messages, and position-based matching merges them.

## 6. Tests

### Unit — `services/messaging.py`

| Test | Asserts |
|---|---|
| `test_unread_count_excludes_own_messages` | |
| `test_unread_count_respects_read_cursor` | Messages before `last_read_at` are read |
| `test_unread_zero_when_no_receipt` | All inbound messages unread |
| `test_opening_thread_marks_all_read` | **§2 third clause.** No phantom unread |
| `test_send_message_persists_before_broadcast` | Ordering guard |
| `test_participant_check_requires_accepted_connection` | **Rule 2** |

### Integration

| Test | Asserts |
|---|---|
| `test_send_and_fetch_message` | Round trip |
| `test_messages_require_session` | **Rule 1** → `401` |
| `test_non_participant_cannot_read_thread` | **`404`**, not `403` |
| `test_non_participant_cannot_send` | **`404`** |
| `test_unaccepted_connection_forbidden` | `403 connection_not_established` |
| `test_messages_persist_across_restart` | **The demo case** |
| `test_empty_message_rejected` | `422` |
| `test_message_length_cap` | 2001 → `422` |
| `test_thread_list_only_contains_participants` | No leakage |
| `test_pagination_no_duplicates_at_same_timestamp` | **The `id` tiebreaker** |
| `test_opening_thread_clears_unread` | |
| `test_cannot_subscribe_to_foreign_thread` | **Socket authorisation** |

### WebSocket

| Test | Asserts |
|---|---|
| `test_recipient_receives_message_live` | **The demo** |
| `test_sender_does_not_receive_own_broadcast` | **The duplicate guard.** §4 step 4 |
| `test_message_persists_if_receiver_offline` | Fetched on reconnect |
| `test_subscribe_to_foreign_thread_rejected` | `error` frame with `forbidden` |
| `test_client_id_echoed_in_ack` | Optimistic reconciliation |
| `test_ws_requires_session` | `401` during handshake |
| `test_unsubscribe_stops_delivery` | |

### E2E

**The single most important test in the project.**

1. Two browser contexts, users A and B, connected.
2. A opens `/messages/{threadId}`, B opens the same thread.
3. A sends "Hello".
4. **B sees it with no refresh, no reload, no wait.**
5. B replies; A sees it immediately.
6. Reload both. Both conversations intact.
7. B opens the thread → unread badge clears.

## 7. Out of scope

Group threads, attachments, typing indicators, read receipts per message,
message search, edit, delete, reactions, delivery and read status ticks,
message drafts, message expiry, WebSocket scale beyond one backend process.

## 8. Definition of done

- [x] `require_participant` on every thread route **and** on socket subscribe
- [x] `403 connection_not_established` enforced, not assumed
- [x] Non-participants get `404` — existence not confirmed
- [x] Messages persist across a backend restart
- [x] Message pagination index includes `id` as tiebreaker
- [x] Opening a thread clears unread, including messages that arrived while closed
- [x] Sender does not receive its own broadcast
- [x] Optimistic send reconciles by `id` and rolls back on failure
- [x] Send works over `POST` with the socket down
- [x] Reconnect refetches without duplicates
- [x] Uvicorn single-worker requirement documented in the compose file
- [ ] The two-window E2E test passes — **implemented, ~1 flake in 5 runs** (socket subscription timing). See *As built* §10.4.
- [x] Every §6 test passes

## 9. Agent notes

- **This is the demo's centrepiece and its most fragile feature.** Everything
  here exists so two browser windows show a live conversation.
- **Authorisation on the socket is the hole everyone forgets.** HTTP routes get
  reviewed; the `subscribe` handler does not. Test it explicitly.
- **Persist before broadcast.** The reverse shows messages that vanish on
  refresh.
- **Do not broadcast to the sender.** That is the duplicate-message bug, and it
  only appears with optimistic UI.
- **Opening a thread clears all unread.** It is the clause people leave out.
- **Do not yank the scroll position** when a message arrives and the user has
  scrolled up.
- **Send via `POST`, not the socket.** The socket is for receiving live.
- **Single worker.** Put it in the compose file.
---

## 10. As built — 2 October 2026

The permission rules, the read-cursor semantics, the socket protocol and the
lazy thread creation are all implemented as specified.

### 10.1 One WebSocket per page, not per component

§4's protocol is implemented as written. **How it is consumed is not.** The
first implementation gave each component its own socket via a `useWebSocket()`
hook — the notification bell, the toast stack and the chat view each opened
one. Three sockets per page, three handshakes, three reconnect loops, and **the
chat's socket could lose the connection race and never subscribe**.

The symptom was the worst kind: **live messages silently never arrived**. The
UI looked correct, history worked, the send worked — only the thing the demo is
built around was missing.

[`hooks/websocket.tsx`](../frontend/src/hooks/websocket.tsx) now provides a
single provider-owned socket per page. Components register listeners:

```ts
useThreadSubscription(threadId)          // subscribe for as long as mounted
useSocketListener('message', handler)    // 'message' and 'ack' frames
useSocketListener('notification', handler)
```

The provider re-sends every wanted subscription on reconnect, so §4's "refetch
after reconnect" rule still holds, and it no longer depends on each component
re-subscribing itself.

### 10.2 Socket hardening

Two unhandled paths could kill a connection mid-demo and were closed:

- **A malformed frame** (invalid JSON) raised out of `receive_json()` and
  dropped the socket. It now replies with an error frame and continues.
- **Any unexpected exception** in the loop became an ASGI error. It is now
  logged and the `finally` still unsubscribes.

Both are tested: `test_malformed_frame_does_not_kill_the_socket`.

### 10.3 `peerTyping` was removed

§5's chat view sketched a typing indicator. It was dead state with nothing
driving it, and typing indicators are out of scope in §7. Removed rather than
left as a stub.

### 10.4 Known flake

The two-window E2E test is implemented and **passes about 4 runs in 5**. It fails
inside `openConversation`, waiting for the message composer to appear.

The most likely cause is subscription timing: `useThreadSubscription` only
subscribes once `status === 'open'`, and the test proceeds as soon as the
composer renders, which can precede the subscribe frame. The next step is to
wait for the `subscribed` acknowledgement the server already sends
(`{"type":"subscribed","thread_id":…}`) before sending. **Do not paper over it
with a blanket retry** — a flaky centrepiece test is worse than a slow one.

### 10.5 Test coverage

13 integration tests in
[`test_websocket.py`](../backend/tests/integration/test_websocket.py), run
against a **real uvicorn subprocess** because `httpx`'s `ASGITransport` cannot
speak WebSocket. All six §6 cases plus socket-send, unsubscribe, notification
push, ping/pong, malformed frames and two tabs for one user. Plus 11 backend
integration tests for the HTTP side of the permission rules and read cursors,
and one E2E test for the full two-window path.
