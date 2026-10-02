# 00 — Conventions

**This document is the contract.** Every spec from 01 to 09 assumes it. Read it
before reading anything else. If a feature spec and this document disagree,
this document wins — and the feature spec is wrong and should be fixed.

**Status:** Implemented. Every rule below is enforced in code and covered by a
test. See *As built* §13 for the five rules that needed sharpening and the two
traps that cost real debugging time.
**Applies to:** every feature.

---

## 1. Base URLs

| Path | Owner | Notes |
|---|---|---|
| `/api/v1/*` | Backend | All HTTP endpoints. Version prefix is mandatory. |
| `/api/v1/ws` | Backend | WebSocket upgrade. Same origin through Vite. |
| `/api/v1/docs` | Backend | Swagger UI. Never block on building this. |

The frontend calls **same-origin relative paths only**. Vite proxies `/api` to
the backend. Hardcoding `localhost:8000` anywhere in frontend code is a bug —
it breaks the moment someone runs on a different host.

## 2. Error shape

Every non-2xx response uses one shape. No exceptions. Frontend error handling
depends on it.

```json
{
  "error": {
    "code": "profile_incomplete",
    "message": "Choose a role and add at least one skill before browsing matches.",
    "fields": { "role": "Required to complete your profile." }
  }
}
```

| Field | Type | Required | Meaning |
|---|---|---|---|
| `code` | string | yes | Stable, machine-readable, `snake_case`. Switch on this, never on `message`. |
| `message` | string | yes | Human-readable, presentable to a user as-is. No stack traces, no jargon. |
| `fields` | object | no | Per-field validation detail. Only on `422`. |

### Status codes

| Code | When | `code` examples |
|---|---|---|
| `400` | Malformed request, unparseable body | `bad_request` |
| `401` | No session, or session expired | `unauthenticated`, `session_expired` |
| `403` | Authenticated but not permitted | `forbidden`, `not_profile_owner`, `profile_incomplete`, `connection_not_established` |
| `404` | Does not exist, **or exists but you may not know it exists** | `not_found` |
| `409` | Conflicts with current state | `already_exists`, `invalid_transition` |
| `413` | Payload too large (photo over cap) | `file_too_large` |
| `415` | Wrong media type | `unsupported_media_type` |
| `422` | Validation failed | `validation_error` |
| `429` | Rate limited | `rate_limited` |
| `500` | Unhandled server fault | `internal_error` |

Two rules that get probed:

- **`403` and `404` are not interchangeable.** Use `403` when the resource
  exists and you are not allowed to touch it. Use `404` when existence itself
  is private. Never leak the existence of another user's private resource.
- **`500` never leaks internals.** Log the traceback server-side, return
  `internal_error` with a generic message.

### Validation errors

`422` bodies always carry `fields`, keyed by the request field name:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Some fields need attention.",
    "fields": {
      "email": "Enter a valid email address.",
      "password": "Must be at least 8 characters."
    }
  }
}
```

## 3. Authentication

**httpOnly cookie sessions. Not JWT in localStorage.**
Rationale: [`decisions/0004-cookie-sessions-not-jwt.md`](../decisions/0004-cookie-sessions-not-jwt.md).

- Cookie name: `session`. `httpOnly`, `SameSite=Lax`, `Secure` in production,
  `Path=/`.
- Opaque random token stored server-side. **Not** a signed payload — there is
  nothing in the session the client needs to read, so there is no reason for it
  to be decodable.
- Default lifetime 7 days. Sliding: refreshed on activity.
- Logout deletes the server-side row. The cookie alone is never enough to
  revoke anything.

### CSRF

Because cookies are sent automatically, mutating requests need CSRF protection.

- Mutating methods: `POST`, `PUT`, `PATCH`, `DELETE`.
- Require header `X-CSRF-Token`, matching a token issued alongside the session.
- Missing or wrong → `403 csrf_failed`.
- `GET` and the WebSocket handshake are exempt.

### Guards

Depend on FastAPI dependencies, declared per router — never checked by hand
inside a handler.

| Dependency | Behaviour |
|---|---|
| `get_current_user` | Valid session required, else `401`. Every user-scoped endpoint uses this. |
| `get_current_admin` | `get_current_user` plus `is_admin`, else `403`. |

**Never trust a client-supplied user id.** The current user always comes from
the session. A `user_id` in a path or body is only ever the *other* party.

## 4. Resources and naming

Plural nouns for collections, singular for one. No verbs in paths — the verb is
the method.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/users/{id}` | One user |
| `PATCH` | `/api/v1/users/me` | Update own profile |
| `GET` | `/api/v1/matches` | Collection |
| `POST` | `/api/v1/connections` | Create |
| `PATCH` | `/api/v1/connections/{id}` | Transition |

### Names

| Thing | Convention | Example |
|---|---|---|
| Database table | `snake_case` plural | `connection_requests` |
| ORM model | `Singular` PascalCase | `ConnectionRequest` |
| Pydantic schema | `PascalCase` + suffix | `UserPublic`, `CreateSkillRequest` |
| API field | `snake_case` | `first_name` |
| Python var/function | `snake_case` | `def score_match(...)` |
| React component | `PascalCase` | `ProfileCard.tsx` |
| Hook | `useX` | `useMatches()` |
| Env var | `UPPER_SNAKE` | `SESSION_SECRET` |
| Migration | Alembic-generated, never hand-named | — |

### Endpoints reserved for each feature

Each spec lists its own endpoints. Adding one is a spec change first.

```
GET    /api/v1/health
POST   /api/v1/auth/register            POST   /api/v1/auth/login
POST   /api/v1/auth/logout              POST   /api/v1/auth/magic-link
GET    /api/v1/auth/magic-link/verify   GET    /api/v1/users/me
PATCH  /api/v1/users/me                 POST   /api/v1/users/me/photo
GET    /api/v1/users/{id}               GET    /api/v1/matches
GET    /api/v1/matches/{id}             GET    /api/v1/connections
POST   /api/v1/connections              GET    /api/v1/connections/{id}
PATCH  /api/v1/connections/{id}         DELETE /api/v1/connections/{id}
GET    /api/v1/threads                  GET    /api/v1/threads/{id}/messages
POST   /api/v1/threads/{id}/messages    WS     /api/v1/ws
GET    /api/v1/notifications            GET    /api/v1/notifications/{id}
PATCH  /api/v1/notifications/{id}       POST   /api/v1/notifications/read-all
GET    /api/v1/ideas                    POST   /api/v1/ideas
GET    /api/v1/ideas/{id}               PATCH  /api/v1/ideas/{id}
DELETE /api/v1/ideas/{id}               POST   /api/v1/ideas/{id}/interest
DELETE /api/v1/ideas/{id}/interest
GET    /api/v1/admin/users              GET    /api/v1/admin/skills
GET    /api/v1/admin/audit              ...    full list in specs/09_admin.md
```

## 5. Pagination

Every list endpoint is paginated. No exceptions — an unpaginated list will
eventually be the thing that falls over during the demo.

| Aspect | Rule |
|---|---|
| Params | `?limit=` (default 20, max 100) and `?cursor=` (opaque, optional) |
| Envelope | `{"items": [...], "next_cursor": "..." \| null}` |
| Ordering | Stable. Always include a tiebreaker column, or page 2 duplicates page 1. |
| Filtering | Query params, AND-combined. Defined per endpoint in its spec. |

**Cursor, not offset.** Offsets skip or duplicate rows when data changes
between requests — exactly what happens when someone sends a message during
the demo.

## 6. Timestamps and IDs

- **IDs:** UUID v4, generated by the database (`uuid` type, `gen_random_uuid()`
  via `pgcrypto`). Never sequential integers — they leak volume and let people
  enumerate.
- **Timestamps:** `timestamptz`, always UTC. Never store naive local time.
- **Serialise as** ISO 8601 with `Z`: `2026-10-14T09:30:00Z`.
- Never hand-assign an ID. Never trust one from a client.

## 7. The frontend

### Structure

```
frontend/src/
  api/        one typed function per endpoint; the ONLY place fetch is called
  components/ presentational, no data fetching
  pages/      one per route, composes components and hooks
  hooks/      data fetching and websocket lifecycle
  routes/     route table and guards
```

### Rules

1. **`api/` is the only place `fetch` appears.** Components use `api/` functions.
   This is what makes the error shape enforceable and the components testable.
2. **`credentials: 'include'` on every request.** The session cookie must
   travel. Easy to forget; fails as a confusing 401.
3. **`X-CSRF-Token` on every mutating request.** Handled inside the `api/`
   client so callers cannot forget.
4. **Route guards in `routes/`,** not scattered through components.
5. **Optimistic where safe.** Sending a message renders immediately and
   reconciles on the socket event. Accepting a connection does *not* go
   optimistic — the request must succeed before a thread appears.
6. **Every list has a loading, empty and error state.** A spinner is not an
   empty state. See `AGENTS.md` §5 rule 6.
7. **No new component library.** Tailwind only. See
   [`decisions/0003-vite-not-nextjs.md`](../decisions/0003-vite-not-nextjs.md).

## 8. The backend

### Layout

```
backend/app/
  main.py        app factory, CORS, router mounting, exception handlers
  config.py      pydantic-settings, all env access in one place
  db.py          async engine + session dependency
  models/        SQLAlchemy models, one module per domain
  schemas/       Pydantic request/response models
  routers/       HTTP layer: parse, call service, serialise. No business logic.
  services/      ALL business logic lives here
  realtime.py    WebSocket connection registry + broadcast helpers
  seed.py        dev seed data, including admin accounts
```

### Rules

1. **Routers are thin.** Parse input, call a service, serialise output. Any
   `if` that encodes a business rule belongs in `services/`.
2. **Services own the rules**, including the ones in `AGENTS.md` §5. Unit tests
   target `services/` directly — no HTTP needed, no fixtures, fast.
3. **One global exception handler** turns internal errors into the §2 shape.
   Handlers do not return ad-hoc error bodies.
4. **Migrations, never `create_all`.** Schema changes go through Alembic. Anyone
   can run `alembic upgrade head` on an empty database.
5. **No business logic in the frontend.** If a rule matters, it is enforced in a
   service. The frontend may mirror it for a better error message; it is never
   the enforcement point.
6. **Async throughout.** `asyncpg` driver, `AsyncSession`, `await` every query.
   Never a blocking call in an async handler — it stalls the event loop and
   takes down the WebSocket with it.

## 9. Permissions

Every user-scoped endpoint answers three questions before returning data:
whose data is this, may this user see it, may this user change it.

| Rule | Enforced by |
|---|---|
| Own profile only, admins excepted and audited | `get_current_user` + service check |
| Matching needs `profile_complete` | service check → `403 profile_incomplete` |
| Messaging needs an accepted connection, both ways | service check → `403 connection_not_established` |
| Idea mutation needs ownership | service check → `403 not_idea_owner` |
| Admin routes need `is_admin` | `get_current_admin` |

`AGENTS.md` §5 is the short version. Those rules are not suggestions.

## 10. Tests

Bar and rationale: [`decisions/0010-test-strategy.md`](../decisions/0010-test-strategy.md).

| Suite | Tool | Runs against | Covers |
|---|---|---|---|
| Backend unit | pytest | no I/O, `services/` called directly | scoring, permission checks, state machines, validation |
| Backend integration | pytest + httpx | real Postgres, test client | every endpoint, every `AGENTS.md` §5 rule |
| Frontend component | Vitest + RTL | jsdom | rendering, loading/empty/error states |
| E2E | Playwright | full stack in Docker | each feature's demo path |

**Every `AGENTS.md` §5 rule has at least one integration test.** These are the
rules a marker is most likely to probe. Auth guard, mutual opt-in, profile
completeness, profile ownership, input validation, graceful degradation.

Conventions: test files mirror source (`tests/unit/test_matching.py`), name
behaviour not implementation (`test_accept_own_request_rejected`), one arrange
/ act / assert block with a comment naming the rule under test.

## 11. Naming for things we chose deliberately

Use these names. Consistency across five people and several AI agents is worth
more than personal preference.

| Concept | Name | Not |
|---|---|---|
| Accepted connection | `connection` | `match`, `friendship` |
| Pending request | `connection_request` | `invite`, `connect_request` |
| Automatic suggestion | `match` | `recommendation`, `suggestion` |
| Why a match was suggested | `reason` | `explanation`, `justification` |
| Private conversation | `thread` | `chat`, `conversation` |
| Single message | `message` | — |
| Someone who posted an idea | `author` | `owner`, `poster` |
| Interest in an idea | `interest` | `vote`, `like` |
| Admin user | `admin`, `is_admin` | `moderator`, `superuser` |

"Match" and "connection" are different things and must never be used
interchangeably: a **match** is a suggestion, a **connection** is a mutual
agreement. `AGENTS.md` §5 rule 2 depends on the distinction.

## 12. Adding to this document

If two feature specs need a convention that is not here, it belongs here. Add
it to this file in the same PR as the feature that needed it, and reference it
from the spec.

If you change the stack, write an ADR in `decisions/` first. Mark the old ADR
superseded and link both. Never change the stack in code without the ADR —
[`decisions/` README](../decisions/README.md) has the format.
---

## 13. As built — 2 October 2026

Every rule in this document is implemented and enforced. Where the
implementation sharpened a rule, it is recorded below; nothing here was dropped.

### 13.1 §2 error shape

Enforced by one global exception handler plus `AppError` subclasses. Two rules
from this document that were not obvious until code existed:

- **A message string after an assignment is not a docstring.** `class Foo: code
  = "x"` followed by `"""Message"""` produces an empty message, because
  `self.__doc__` is `None`. Every named error now puts its message first.
- **`422` is not always `validation_error`.** `ReceiverProfileIncomplete` is a
  `422` with its own code, because specs 05 §4 requires it.

### 13.2 §3 authentication

Implemented exactly as written: opaque tokens hashed at rest, `X-CSRF-Token` on
mutating requests, and `get_current_user` / `get_current_admin` as the only
ways to reach a user.

**One trap worth writing down:** `require_session` returns a **tuple**
`(Session, User)`. Three call sites initially assumed a bare `Session` and
produced a `500` at runtime rather than a type error. Always destructure.

### 13.3 §5 pagination

Implemented for every list endpoint. Offsets were rejected for the reason §5
gives — they duplicate rows when data changes mid-scroll, which is precisely
what happens when someone sends a message during a demo.

The shared helper is
[`services/pagination.py`](../backend/app/services/pagination.py). Two key
shapes:

- **Time-ordered lists** (ideas, notifications, messages) key on
  `(created_at, id)`.
- **Matches** key on `(score, user_id)`, as specs 04 §7 specifies, because
  sorting is done in Python.

Each service fetches `limit + 1` rows so "is there another page" needs no
`COUNT`.

### 13.4 §8 no lazy loading

`User.profile` is `lazy="joined"` and `Profile.skills`, `Profile.interests` and
`Profile.course` are `lazy="selectin"`.

This is not a style preference. Touching a lazy relationship in async context
raises `MissingGreenlet` **at runtime, not at import time**, and it happened in
three separate places during implementation. The rule for new code: load the
other party with `db.get(...)`, never by attribute access on a relationship.

### 13.5 §10 tests

230 backend tests, 26 frontend component tests, 11 E2E tests. Every `AGENTS.md`
§5 rule has at least one integration test, which is what §10 asks for.

The E2E suite has a **global setup** that deletes non-seed users before each
run. Without it, accumulated test users make `.first()` selectors ambiguous and
the suite goes flaky in a way that reads as an application bug.
