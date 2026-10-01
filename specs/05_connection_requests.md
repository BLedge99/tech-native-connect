# 05 — Connection requests

**Goal:** express interest, get an answer, and open a thread only when both
sides have agreed. This feature **is** the consent mechanism for messaging
([06](06_messaging.md)) — getting the state machine wrong here is a data leak,
not a UI annoyance.

**Depends on:** [04 — Matching](04_matching_and_search.md)
**Blocks:** [06 — Messaging](06_messaging.md),
[07 — Notifications](07_notifications.md)

**Implementation status:** Not started.

---

## 1. Scope

| In | Out |
|---|---|
| Send, withdraw, accept, decline | Blocking, reporting — [`deferred_safety_moderation.md`](deferred_safety_moderation.md) |
| Received / sent / connected lists | Per-connection privacy settings |
| State machine enforced server-side | Message requests before acceptance — deliberately absent |
| Connection state on cards | Group chats |
| | Editing a request message after sending |

### One request per pair, ever

A pair of users has **one** `connection_requests` row, not one per attempt.
Its state moves forward only: `pending → accepted` or `pending → declined`.
A declined pair cannot re-request.

This is a table constraint, not a service check, so it cannot be bypassed:

```sql
CREATE UNIQUE INDEX one_request_per_pair ON connection_requests (
  LEAST(sender_id, receiver_id), GREATEST(sender_id, receiver_id)
);
```

`LEAST`/`GREATEST` normalise direction, so the index catches both orderings
with one definition. Without a database-level guarantee, five people writing
this feature will each handle the duplicate differently, and the first race
condition during the demo wins.

## 2. Data model

### `connection_requests`

| Column | Type | Notes |
|---|---|---|
| `id` | `uuid` PK | |
| `sender_id` | `uuid` FK → `users.id` | Who asked |
| `receiver_id` | `uuid` FK → `users.id` | Who was asked |
| `status` | enum | `pending` \| `accepted` \| `declined` |
| `message` | `varchar(300)` nullable | One line with the request |
| `created_at` | `timestamptz` | |
| `responded_at` | `timestamptz` nullable | |
| `responded_by` | `uuid` nullable | Audit trail |

```sql
CREATE TYPE connection_status AS ENUM ('pending', 'accepted', 'declined');
```

**`responded_by` is not obvious and it is worth keeping.** It lets the audit
screen answer "who accepted this?" without inferring it from `sender_id` /
`receiver_id`. The alternative is a coin flip every time someone asks.

### Constraints

- `CHECK (sender_id <> receiver_id)` — no self-requests, at the database.
- Unique index from §1.
- Index on `(receiver_id, status)` for the received list.
- Index on `(sender_id, status)` for the sent list.

The **accepted** connection and the request are the same row at `status =
'accepted'`. Do not create a separate `connections` table. Two tables holding
the same fact is two sources of truth, and they will disagree.

`threads` ([06](06_messaging.md)) references `connection_requests.id`.

### `decline_reason`

Not a column. The brief does not ask for it, and decline is terminal — nothing
acts on a reason. Skip it.

## 3. The state machine

Terminal states. No transitions back to `pending`, ever.

```
                    ┌──────────────┐
     send ─────────▶│   pending    │
                    └──┬────────┬──┘
              accept   │        │   decline
          ┌────────────┘        └──────────┐
          ▼                                 ▼
    ┌───────────┐                     ┌───────────┐
    │ accepted  │  (terminal)         │ declined  │  (terminal)
    └───────────┘                     └───────────┘
          │
          │  grants
          ▼
    ┌───────────┐
    │  thread   │  created lazily on first message
    └───────────┘
```

### Transition table

The authority for the service and for the unit tests. Implement it as data,
not as scattered `if` statements.

| From | Action | To | Actor | Result |
|---|---|---|---|---|
| — | `send` | `pending` | Either party | `201` |
| `pending` | `accept` | `accepted` | **Receiver only** | `200` |
| `pending` | `decline` | `declined` | **Receiver only** | `200` |
| `pending` | `withdraw` | *(deleted)* | **Sender only** | `204` |
| `pending` | `send` again | — | — | `409 already_exists` |
| `pending` | `accept` | — | **Sender** | `403 not_receiver` |
| `pending` | `accept` again | — | Receiver | `409 already_responded` |
| `pending` | `decline` after accept | — | Receiver | `409 already_responded` |
| `accepted` | any | — | — | `409 already_connected` |
| `declined` | `send` | — | — | `409 request_declined` |
| `declined` | any | — | — | `409` |
| any | self-action | — | Self | `403` |

### Every invalid transition is a case in the tests

Unit-test the whole table, not just the happy path. Six rows that "obviously
can't happen" and five do. Row-by-row table-driven tests:

```python
@pytest.mark.parametrize("current,action,actor,expected_status,expected_code", [
    ("pending",  "accept",  "sender",   403, "not_receiver"),
    ("pending",  "accept",  "receiver", 200, None),          # happy path
    ("accepted", "accept",  "receiver", 409, "already_responded"),
    ("declined", "send",    "sender",   409, "request_declined"),
    ("accepted", "decline", "receiver", 409, "already_responded"),
    # ... every row
])
def test_transition(current, action, actor, expected_status, expected_code): ...
```

One test function, the table as data. Adding a state means adding a row.

### Only the receiver can accept or decline

**The sender accepting their own request would open a thread without the other
person's consent** — a direct violation of `AGENTS.md` §5 rule 2. This is the
single most important authorisation check in the feature.

## 4. Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `POST` | `/api/v1/connections` | session | Send a request |
| `GET` | `/api/v1/connections` | session | All connections, filterable |
| `GET` | `/api/v1/connections?filter=received\|sent\|connected` | session | Filtered |
| `GET` | `/api/v1/connections/{id}` | session | One request; participants only |
| `PATCH` | `/api/v1/connections/{id}` | session | `accept` or `decline` |
| `DELETE` | `/api/v1/connections/{id}` | session | Withdraw, sender only |
| `GET` | `/api/v1/connections/summary` | session | Counts for the nav badge |

### `POST /connections`

```jsonc
// request
{ "receiver_id": "…uuid…", "message": "Saw your fintech idea — let's talk" }

// 201
{
  "id": "…", "status": "pending",
  "sender":    { "id": "…", "display_name": "Sam", "has_photo": true, "photo_url": "…" },
  "receiver":  { "id": "…", "display_name": "Priya", "has_photo": true, "photo_url": "…" },
  "message": "Saw your fintech idea — let's talk",
  "created_at": "2026-10-08T09:00:00Z", "responded_at": null
}
```

The response embeds **both** parties' summaries. The sender's UI needs to render
the card immediately without a second request, and both parties are participants,
so both are visible under [`03](03_profiles.md) §6.

| Case | Status | `code` |
|---|---|---|
| Success | `201` | — |
| Request to yourself | `422` | `validation_error` |
| Unknown receiver | `404` | `not_found` |
| Deactivated receiver | `404` | `not_found` |
| Already pending | `409` | `already_exists` |
| Already connected | `409` | `already_connected` |
| Previously declined | `409` | `request_declined` |
| Receiver profile incomplete | `422` | `receiver_profile_incomplete` |

**`receiver_profile_incomplete` is the one that gets missed.** Sending a
request to someone with no skills means matching cannot explain why, and they
will not see the request in a useful context. Rejecting it at send time with a
clear message beats a stranger's blank profile.

| Case | Status | `code` |
|---|---|---|
| Receiver profile incomplete | `422` | `receiver_profile_incomplete` |
| Sender profile incomplete | `403` | `profile_incomplete` |

Sender incompleteness is `403`, matching [04](04_matching_and_search.md) §4 —
you cannot meaningfully ask to connect before you can receive a match.
Receiver incompleteness is `422`, because the receiver is not the one making
the invalid request.

### `GET /connections`

One endpoint with a filter, not three endpoints. It is the same query with a
different `WHERE`, and three endpoints means three routes to keep in step.

| `filter` | Returns |
|---|---|
| `received` | Pending requests **to me**, newest first |
| `sent` | Pending requests **from me**, newest first |
| `connected` | Accepted, for either party, with the other party's summary |

Omit `filter` for everything involving me, accepted and pending both ways. The
`/connections` screen renders three tabs from one call.

```jsonc
{ "items": [ /* connections, each with `other` = the other party */ ],
  "next_cursor": null }
```

Each item carries `other`, `status`, and `unread_count` (0 unless accepted).
For the frontend, a request card wants the *other* person and its own status —
two shapes, not one, and the tabs differ.

### `GET /connections/summary`

```jsonc
{ "received_pending": 3, "sent_pending": 1, "connected": 5, "unread_messages": 2 }
```

One call for nav badges, so the badges cannot disagree with the list they link
to. `/connections` does not include `summary`.

### `PATCH /connections/{id}`

```jsonc
{ "action": "accept" }   // or "decline"
```

`200` with the updated connection.

| Case | Status | `code` |
|---|---|---|
| Success | `200` | — |
| Not a participant | `404` | `not_found` |
| **Sender trying to accept** | `403` | `not_receiver` |
| Already accepted | `409` | `already_responded` |
| Already declined | `409` | `already_responded` |
| Unknown id | `404` | `not_found` |

A non-participant gets `404`, not `403` — the existence of other people's
connections is not the caller's business
([`00_conventions.md`](00_conventions.md) §2).

### `DELETE /connections/{id}`

`204`, sender only, `pending` only. `403 not_sender` if you are the receiver.
`409` if already accepted — withdrawing an accepted connection is disconnecting,
which is [`deferred_safety_moderation.md`](deferred_safety_moderation.md) territory.

## 5. Side effects

### On accept

1. Set `status = 'accepted'`, `responded_at = now()`, `responded_by = receiver_id`.
2. Create a notification for the **sender**: "Priya accepted your request."
   ([07](07_notifications.md)).
3. Do **not** create a `threads` row. It is created lazily on first message.

Creating the thread on accept makes `/messages` show an empty conversation
before either person has spoken. Lazy creation means the thread list is exactly
the list of conversations that have messages — no empty rows to explain.

### On decline

One notification to the sender: "Priya declined your request." A quiet, honest
sentence. **No reason field** — we do not collect one (§2).

Never auto-delete the request. `declined` is a recorded answer and §1 depends on
it.

### On withdraw

No notification. The receiver never saw it as pending, so telling them about a
withdrawal is noise.

### Idempotency

Every notification trigger checks `responded_at IS NULL` before firing, so a
retry cannot double-notify. Test it by calling `accept` twice — expect `409`
and exactly one notification.

## 6. Frontend

### `/connections`

Three tabs — **Received**, **Sent**, **Connected** — from
`GET /connections?filter=…`.

Received cards show the sender's photo and name, their request message, and
**Accept** / **Decline** buttons.

**Decline is one click, no confirmation modal.** It is terminal but cheap to
recover from in the user's mental model, and a modal is the kind of friction
that gets clicked through without reading. Accept gets a confirming state
because it is consequential — it opens a chat.

Sent cards show "Request sent" with a **Withdraw** link, muted not primary.
Connected cards show the last message preview, unread count, and **Message**.

**Pending count badge in the nav** from `/connections/summary`, polled on
route change and invalidated on any mutation. Not a WebSocket push — simpler,
and notifications are already on the socket ([07](07_notifications.md)).

### `ConnectButton`

One component, three states, driven entirely by `connection_state` from
[04](04_matching_and_search.md) §6. Reused on match cards, profiles, and the
home feed.

```tsx
function ConnectButton({ userId, state, onSent }) {
  switch (state) {
    case "none":           return <PrimaryButton onClick={onSent}>Connect</PrimaryButton>;
    case "pending_outgoing": return <MutedButton>Request sent</MutedButton>;
    case "pending_incoming": return <SecondaryButton href={`/connections`}>Wants to connect</SecondaryButton>;
    case "connected":        return <SecondaryButton href={`/messages/${threadId}`}>Message</SecondaryButton>;
  }
}
```

Rendered from **server state**, never local optimism. Send → refetch →
`pending_outgoing`. The state machine is the source of truth.

### Optimistic UI boundary

**Accept is not optimistic.** The thread must not exist unless the server said
so. Send *can* be optimistic — flip the button, roll back on error — because a
failed request leaves nothing behind.

This asymmetry is deliberate and is the most likely thing to get wrong.

## 7. Tests

### Unit — `services/connections.py`

The whole state machine, table-driven (§3). Plus:

| Test | Asserts |
|---|---|
| `test_only_receiver_can_accept` | Sender → `403 not_receiver` |
| `test_only_receiver_can_decline` | Sender → `403` |
| `test_only_sender_can_withdraw` | Receiver → `403 not_sender` |
| `test_cannot_withdraw_accepted` | `409` |
| `test_cannot_request_self` | `422` |
| `test_decline_is_terminal` | Re-request → `409 request_declined` |
| `test_accept_creates_exactly_one_notification` | **Side effect once** |
| `test_double_accept_creates_no_second_notification` | The idempotency guard |
| `test_decline_creates_notification` | |
| `test_withdraw_creates_no_notification` | |
| `test_accept_does_not_create_thread` | **Lazy thread creation** |

### Integration

| Test | Asserts |
|---|---|
| `test_send_request` | `201` |
| `test_duplicate_request` | `409 already_exists` |
| `test_request_to_self_rejected` | `422` |
| `test_request_unknown_user` | `404` |
| `test_request_deactivated_user` | `404` |
| `test_request_to_incomplete_profile` | `422 receiver_profile_incomplete` |
| `test_send_from_incomplete_profile` | `403 profile_incomplete` |
| `test_accept_happy_path` | `200`, status `accepted` |
| `test_sender_cannot_accept` | **`AGENTS.md` §5 rule 2** → `403` |
| `test_non_participant_gets_404_not_403` | |
| `test_accept_twice` | `409` |
| `test_decline_then_accept` | `409` |
| `test_withdraw_by_receiver` | `403` |
| `test_connections_require_session` | **Rule 1** → `401` |
| `test_connection_list_never_leaks_other_people` | Only requests involving me |
| `test_summary_counts_match_list` | Badge arithmetic |
| `test_accepted_pair_can_see_the_thread_id` | Feeds [06](06_messaging.md) |

### E2E

1. Two users. A sends B a request.
2. B sees it under Received, A sees "Request sent" under Sent.
3. B accepts.
4. **Both** see a connected state, in two windows, without refreshing.
5. A gets a notification.
6. B declines on a second pair; A sees declined and cannot re-request.
7. Third party cannot see or alter either request.

## 8. Out of scope

Blocking, reporting, disconnecting after acceptance, bulk accept/decline,
message previews before acceptance, request expiry, a "connections" graph
visualisation, contacts import, connection recommendations, per-connection
notification settings.

## 9. Definition of done

- [ ] One row per pair, enforced by a unique index on `(LEAST, GREATEST)`
- [ ] Full transition table implemented as data and unit-tested row by row
- [ ] Only the receiver can accept or decline — tested
- [ ] Sender cannot accept their own request — `403 not_receiver`
- [ ] Accepted connection is the request row, not a second table
- [ ] Thread created lazily on first message, not on accept
- [ ] Notifications fire exactly once per transition
- [ ] Non-participants get `404`
- [ ] Every §7 test passes

## 10. Agent notes

- **This feature is a security boundary, not a UI feature.** A bug here leaks
  messages. Read `AGENTS.md` §5 rule 2 before changing anything.
- **Only the receiver accepts.** The single most important check.
- **The unique index on `(LEAST, GREATEST)` catches duplicate requests in both
  directions.** Do not rely on a `SELECT` before `INSERT` — that races.
- **Do not create a thread on accept.** Lazy, on first message. Creating it
  eagerly means empty conversations in the message list.
- **Accept is not optimistic.** Send may be. The difference matters.
- **`receiver_profile_incomplete` is `422`, sender incompleteness is `403`.**
  Different actors, different codes.