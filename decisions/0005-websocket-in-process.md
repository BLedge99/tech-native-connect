# 0005 — Native WebSocket with an in-process registry

**Status:** Accepted
**Date:** 2026-10-01
**Affects:** [06](../specs/06_messaging.md), [07](../specs/07_notifications.md)

## Context

Live updates are the demo's centrepiece. Two browser windows, one sends a
message, the other shows it with no refresh. That is the moment the app stops
looking like a prototype.

The brief lists real-time chat as a *suggested* feature and the weekly goals
include real-time chat, so it is in. The question was how to build it in two
weeks without a piece of infrastructure that nobody on the team can debug under
pressure.

## Decision

**A native WebSocket endpoint on the existing FastAPI process, with an in-process
connection registry. FastAPI's native WebSocket support, no external library, no
dedicated service, and a hard single-worker requirement on uvicorn.**

The registry is `user_id → set[WebSocket]` and `thread_id → set[WebSocket]`, in
[`realtime.py`](../backend/app/realtime.py).

## Rejected

| Option | Why it lost |
|---|---|
| **Socket.IO** | The most featureful option and the most common. Rejected because most of that feature set — rooms with automatic joins, reconnection with buffering, acknowledgements, binary attachments — is unused here, and it adds a client library, a different protocol on the server, and a second thing to learn when debugging. It also brings its own handshake semantics, which interacts badly with a cookie-based session ([0004](0004-cookie-sessions-not-jwt.md)). Our protocol is six message types ([06](../specs/06_messaging.md) §4). |
| **Server-Sent Events + POST** | Half the code and one-directional, which is arguably all we need. Rejected because SSE is HTTP, so it fights the session-cookie story differently and does not solve the harder part: notifications must be pushed to a specific user, and message delivery needs bidirectional confirmation (`client_id` echo) for optimistic UI. The bidirectional case is real, so we pay for bidirectional. |
| **Long polling** | Works everywhere, needs no new protocol, and is trivial. Rejected on demo risk: 2-second polling delays make live updates look sluggish, and a poll per thread does not scale to a demo where someone has five threads open. |
| **Polling on an interval** | The fallback we kept, not the mechanism ([06](../specs/06_messaging.md) §4). Refresh-to-see reads as an unfinished app. |
| **Redis pub/sub + a dedicated realtime service** | The correct answer at any real scale, and the one this would grow into. Rejected because it is a fifth container, it needs configuration before a single message flows, and it adds a failure mode that cannot be debugged from inside one terminal during a live demo. **It is the upgrade path, not the starting point.** |
| **A hosted realtime vendor (Pusher, Ably)** | Excellent reliability and a beautiful client API. Rejected because it needs an account and a key, works only when someone has network access, and costs money — all three violate the "no third-party services" constraint. |

## Consequences

**Cost, and it is the important one: this does not scale past one process.** An
in-process registry is per-worker. If FastAPI runs two workers, each holds half
the sockets and a message to a user connected to the other worker is simply lost
— silently, intermittently, and only under concurrency.

Therefore:

- **`uvicorn` must run with exactly one worker.** Not a preference; a
  correctness requirement of this design.
- **This belongs in the compose file as a comment**, written now, before someone
  scales it and loses an afternoon to messages that vanish with no error.
- The `# ponytail:` marker in [06](../specs/06_messaging.md) §4 names the ceiling
  and the upgrade path.

**Second cost:** a process restart drops every socket. Clients reconnect with
exponential backoff and refetch
([06](../specs/06_messaging.md) §4), which is fine for a demo but is a visible
delay.

**Second cost:** delivery is best-effort. There is no durable queue. If the
receiver is offline, the message is not buffered — the client fetches on
reconnect. Acceptable, and it is why
[06](../specs/06_messaging.md) §4 requires refetching with `?after=` rather than
replaying from the server.

**Gained:** no new infrastructure, no new dependency, no network hop, and no
third-party failure. Debugging is `print` statements in one process. For a
feature whose entire job is to work reliably on one laptop in front of a
marker, that is exactly the right trade.

**Upgrade path.** Replace the internals of `ConnectionManager` with Redis
pub/sub and run as many workers as we like. **The `send`, `broadcast_to_thread`
and `broadcast_to_user` API does not change**, so no spec changes and no route
changes. That is the property worth protecting: keep the registry behind a small
interface so the swap is internal.

**Risk to watch:** the socket handshake is a long-lived route that HTTP
middleware and dependency injection can mishandle. Authorisation on
`subscribe` must go through the same `require_participant` check as the HTTP
endpoints — a WebSocket is otherwise a long-lived bypass of every guard, and it
is the single most likely place for a permissions hole
([06](../specs/06_messaging.md) §9).

## Related

- [0001](0001-fastapi-and-react.md) — why FastAPI specifically helps here
- [0004](0004-cookie-sessions-not-jwt.md) — how the socket authenticates
- [0010](0010-test-strategy.md) — the two-window E2E test this decision exists for