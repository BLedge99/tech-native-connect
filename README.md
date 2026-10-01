# Bootcamp Connect

> Connect the software developers with the business developers sitting three
> rows away from them.

A bootcamp puts software developers and business developers in the same
building, on the same schedule, for the same course. They never actually meet.
The developers want a business partner who can sell what they build. The
business developers want someone who can build the thing they keep describing.
This app lists the people on your course, ranks the ones you overlap with, and
tells you why.

**Status:** specification complete, implementation not started. Demo target
15 October 2026.

---

## Documentation first

This repository is currently **documentation only**. No application code has
been written yet. The spec set is the deliverable for week one, and it is
designed to be handed to a human developer or an AI agent with no further
context.

| Start here | What it gives you |
|---|---|
| **[`AGENTS.md`](AGENTS.md)** | **Read this first.** Tech stack, conventions, the six non-negotiable product rules, how to pick up a feature. |
| [`PRD.md`](PRD.md) | Who the app serves, what it does, what is in and out of scope, success criteria. |
| [`roadmap.md`](roadmap.md) | The nine features in dependency order, each with a finish line, plus the cut line. |
| [`specs/`](specs/) | One document per feature. Everything an implementer needs, including the tests to write. |
| [`decisions/`](decisions/) | Twelve architecture decision records. Start at [0001](decisions/0001-fastapi-and-react.md). |

### The demo path

> sign up → complete profile → browse matches → send request → accept → message → see notification

Live updates are the centrepiece. Open two browser windows and a message sent on
one appears on the other with no refresh. A chat thread only opens when both
people have accepted — expressing interest is not permission to message.

## Features

**Required for the demo**

| # | Feature | Spec |
|---|---|---|
| 1 | Registration, login, magic link, admin seed | [02](specs/02_registration_and_login.md) |
| 2 | Profiles: photo, bio, skills, interests, course, role | [03](specs/03_profiles.md) |
| 3 | Landing page and home feed | [01](specs/01_landing_page.md) |
| 4 | Matching and search | [04](specs/04_matching_and_search.md) |
| 5 | Connection requests, mutual opt-in | [05](specs/05_connection_requests.md) |
| 6 | Private messaging, live over WebSocket | [06](specs/06_messaging.md) |
| 7 | In-app notifications | [07](specs/07_notifications.md) |
| 8 | Project ideas board | [08](specs/08_project_ideas.md) |
| 9 | Admin screens | [09](specs/09_admin.md) |

**Specced, deliberately not built** — complete designs so they can be added
later without touching required code. Do not build these during the sprint.

- [Events and meetups](specs/deferred_events.md)
- [Privacy settings, deletion and export](specs/deferred_privacy_settings.md)
- [Block, report, moderation queue](specs/deferred_safety_moderation.md)
- [AI icebreaker suggestions](specs/deferred_ai_icebreakers.md)

## Tech stack

Fixed, and not to be substituted. Each choice has an ADR explaining what was
rejected.

| Layer | Choice |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.0 (async), Alembic, Pydantic v2 |
| Frontend | Vite, React 18, TypeScript, React Router, Tailwind CSS |
| Database | PostgreSQL 16 |
| Realtime | Native WebSocket, in-process connection registry |
| Auth | httpOnly cookie sessions + magic link, no third-party vendor |
| Email (dev) | Mailpit — fake SMTP with a web inbox on `:8025` |
| Storage | Profile photos as `bytea` blobs in Postgres |
| Infra | Docker Compose, full stack, local only |
| Tests | pytest, Vitest + React Testing Library, Playwright |

No production deploy and no third-party services. No budget, and a demo that
breaks on hotel wifi is not worth having.

### The six rules

Every spec assumes these. They are the rules a marker is most likely to probe,
so break them deliberately or not at all.

1. **No authentication means no data.** Every user-scoped endpoint returns
   `401` without a valid session. Never trust a client-supplied user id.
2. **A chat thread opens only when both people have accepted.** Expressing
   interest is not permission to message.
3. **Matching is inaccessible until the profile is complete** — role chosen and
   at least one skill added. Return `403 profile_incomplete`, never partial
   results.
4. **Users can only read and write their own profile.** Admins are the sole
   exception, and their access is audited.
5. **Every input is validated at the HTTP boundary.** Length caps, enum checks,
   email format, file type and file size.
6. **The app degrades, it does not break.** If a non-essential feature fails,
   the page still renders.

## Running it

Not yet — implementation has not started. This is the interface once the
foundations feature lands.

```bash
docker compose up --build          # full stack
docker compose up -d db mailpit    # just infra; run apps on host for hot reload
docker compose exec db psql -U bootcamp -d bootcamp_connect
docker compose down -v             # reset, destroys data
```

| Service | URL |
|---|---|
| Frontend | http://localhost:5173 |
| Backend API | http://localhost:8000 |
| Swagger | http://localhost:8000/docs |
| Mailpit inbox | http://localhost:8025 |
| Postgres | localhost:5432 |

Mailpit is a local fake mail server — no real email is ever sent. Magic links
land in the web inbox.

## Working on it

1. Read [`specs/00_conventions.md`](specs/00_conventions.md). It holds the error
   shape, auth guards, pagination and naming that every spec assumes.
2. Read your feature's spec. Features are numbered in **dependency** order — do
   not start one whose prerequisite is unfinished.
3. Branch `feat/<spec-number>-<slug>`, e.g. `feat/03-profiles`.
4. Backend → frontend → tests. **Tests are part of done.**
5. Open a PR referencing the spec number.

Work is not pre-assigned. Take the feature nobody has started.

```bash
feat/02-registration
feat/03-profiles
feat/04-matching
```

## Repository layout

```
.
├── AGENTS.md            entry point for humans and AI agents
├── PRD.md               what the product is
├── roadmap.md           what to build, in what order
├── specs/               one doc per feature, plus deferred_*.md
├── decisions/           numbered ADRs
├── backend/             FastAPI + SQLAlchemy + Alembic   (not yet created)
├── frontend/            Vite + React + TypeScript        (not yet created)
├── e2e/                 Playwright                        (not yet created)
└── docker-compose.yml                                   (not yet created)
```

## Decisions worth knowing about

Full reasoning in [`decisions/`](decisions/), but these three are the ones
people are most likely to question:

- **[0002 — PostgreSQL from day one](decisions/0002-postgres-not-sqlite.md).**
  We considered SQLite now and Postgres later. The switch is not one line: it
  breaks case-insensitive email, `bytea` photos, UUID generation, partial
  indexes, timestamp handling, and concurrent writes. Six real differences, all
  discovered on day thirteen.
- **[0005 — Native WebSocket, in-process registry](decisions/0005-websocket-in-process.md).**
  No Socket.IO, no Redis, no hosted realtime. The cost is a hard single-worker
  requirement on uvicorn — it is written into the compose file on purpose.
- **[0009 — Deterministic matching first](decisions/0009-deterministic-matching-first.md).**
  Matching is weighted overlap over four signals, not an LLM. It is testable,
  explainable, free, and cannot fail during a demo. AI icebreakers are fully
  specced and deferred.

## Team

Ben · Joey · James · Alys · Mick

Bootcamp Connect — TechNative Digital