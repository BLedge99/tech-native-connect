# AGENTS.md

**Read this file first.** It is the entry point for both human and AI contributors.

Bootcamp Connect — a platform that connects software developers with business
developers who are studying alongside them on the same bootcamp.

---

## 1. Project state

- **Repo:** https://github.com/BLedge99/tech-native-connect
- **Demo deadline:** 15 October 2026
- **Team:** Ben, Joey, James, Alys, Mick
- **Current phase:** all nine required features implemented, 2 October 2026

**State.** 233 backend tests, 26 frontend component tests, 11 E2E tests pass.
`tsc --noEmit` is clean. Every feature spec carries an *As built* section
documenting its deviations; `roadmap.md` §Status summary has the totals and the
two known gaps.

- **The code in this repo is newer than the specs in one direction only.** The
  specs remain the source of truth for *what* the product is. Where the build
  had to differ, the difference is written into the spec rather than left in the
  code — if you find a sixth deviation, fix it the same way.
- **Do not build anything in `deferred_*.md`.** Still out of scope.
- **[`handoff.md`](handoff.md)** records the live state of the build, known bugs
  and gotchas. Read it before touching anything.

---

## 2. Tech stack — do not substitute

| Layer | Choice |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.0 (async), Alembic, Pydantic v2 |
| Frontend | Vite + React 18 + TypeScript, React Router, Tailwind CSS |
| Database | PostgreSQL 16 |
| Realtime | Native WebSocket via FastAPI, in-process connection registry |
| Auth | httpOnly cookie sessions + magic link, no third-party auth vendor |
| Email (dev) | Mailpit — fake SMTP, web inbox on :8025 |
| Storage | Profile photos as `bytea` blobs in Postgres |
| Infra | Docker Compose, full stack |
| Tests | pytest (unit + integration), Vitest + React Testing Library, Playwright (E2E) |

Rationale for each choice is in [`decisions/`](decisions/). If you believe a
choice is wrong, write a new ADR that supersedes the old one. Do not silently
change the stack.

---

## 3. Repository layout

```
.
├── AGENTS.md              ← you are here
├── handoff.md             ← live build state, known bugs, gotchas
├── PRD.md                 ← what the product is, who it serves, scope
├── roadmap.md             ← numbered features in build order, with finish lines
├── README.md              ← human quickstart
├── specs/
│   ├── 00_conventions.md  ← READ BEFORE ANY FEATURE. Shared contract.
│   ├── 01_landing_page.md
│   ├── 02_registration_and_login.md
│   ├── 03_profiles.md
│   ├── 04_matching_and_search.md
│   ├── 05_connection_requests.md
│   ├── 06_messaging.md
│   ├── 07_notifications.md
│   ├── 08_project_ideas.md
│   ├── 09_admin.md
│   └── deferred_*.md      ← real specs, NOT for the demo
└── decisions/
    ├── 0001-*.md ... 0012-*.md
```

### Code layout

```
backend/
  alembic/            migrations
  app/
    main.py           FastAPI app factory
    config.py         env settings
    db.py             engine + session
    models/           SQLAlchemy models
    schemas/          Pydantic request/response
    routers/          one module per spec area
    services/         business logic (matching, auth, notifications)
    realtime.py       websocket connection registry
    seed.py           dev seed data incl. admins
  tests/
    unit/          pure logic, no I/O
    integration/   real Postgres, including a live-server WebSocket suite
frontend/
  src/
    api/              typed fetch client
    components/
    pages/
    routes/
    hooks/            session, useQuery, websocket (one socket per page)
  tests/              Playwright E2E + global setup (resets demo data first)
docker-compose.yml
```

---

## 4. How to work on a feature

1. Read `specs/00_conventions.md`. It defines the error shape, auth guards,
   pagination, and naming that every spec assumes.
2. Read your feature's spec in `specs/`. Specs are numbered in build order —
   a higher number may depend on a lower one. Check the "Depends on" line.
3. Implement **backend → frontend → tests**, all on one branch.
4. Branch name: `feat/<spec-number>-<short-slug>` e.g. `feat/03-profiles`.
5. Open a PR referencing the spec number: `Closes spec 03`.
6. Update the spec's "Implementation status" line and its Definition-of-done
   checkboxes when the finish line is met. Add an *As built* section if the
   implementation had to differ from the spec — do not leave that only in code.

### Do not

- Do not implement a feature whose prerequisites are unfinished. Matching
  cannot be built before profiles; there is nothing to match against.
- Do not build anything in a `deferred_*.md` file. They are written so they can
  be added later without touching required code — not so they get built now.
- Do not invent new endpoints, fields or tables that the specs do not describe.
  If the spec is wrong or incomplete, say so and fix the spec first.
- Do not add dependencies not listed in §2 without an ADR.

---

## 5. Non-negotiable product rules

These hold across every feature. They are the rules a marker is most likely to
probe, so break them deliberately or not at all.

1. **No authentication means no data.** Every user-scoped endpoint returns
   `401` without a valid session. Never trust a client-supplied user id.
2. **A chat thread opens only when both people have accepted.** Expressing
   interest is not permission to message. One-sided access is a data leak.
3. **Matching is inaccessible until the profile is complete** — role chosen and
   at least one skill added. Return `403 profile_incomplete`, do not return
   partial results.
4. **Users can only read and write their own profile.** Admins are the sole
   exception, and their access is audited in the admin screens.
5. **Every input is validated at the HTTP boundary.** Length caps, enum checks,
   email format, file type and file size.
6. **The app degrades, it does not break.** If a non-essential feature fails,
   the page still renders. This matters live in a demo.

---

## 6. Running the stack

```bash
docker compose up --build     # full stack
docker compose up -d db mailpit   # just infra, run apps on host for fast reload
docker compose exec db psql -U bootcamp -d bootcamp_connect
docker compose down -v        # reset, destroys data
```

| Service | URL |
|---|---|
| Frontend (Vite) | http://localhost:5173 |
| Backend API | http://localhost:8000 |
| API docs (Swagger) | http://localhost:8000/docs |
| Mailpit inbox | http://localhost:8025 |
| Postgres | localhost:5432 |

Vite proxies `/api` and `/ws` to the backend, so the frontend only ever calls
same-origin paths. Do not hardcode `localhost:8000` in frontend code.

---

## 7. Test requirements

Every required feature ships with:

- **Unit tests** for all business logic in `services/` — matching scoring,
  permission checks, connection state transitions, notification triggers.
- **Integration tests** against a real test Postgres, covering the happy path
  and every rule in §5.
- **E2E tests** (Playwright) for the demo path of every feature:
  sign up → complete profile → browse matches → send request → accept →
  message → see notification.

Test bar rationale: [`decisions/0010-test-strategy.md`](decisions/0010-test-strategy.md).

---

## 8. Environment variables

Never commit real secrets. `.env.example` is committed; `.env` is not.

```
POSTGRES_USER=bootcamp
POSTGRES_PASSWORD=bootcamp
POSTGRES_DB=bootcamp_connect
DATABASE_URL=postgresql+asyncpg://bootcamp:bootcamp@db:5432/bootcamp_connect
SESSION_SECRET=change-me
MAILPIT_SMTP_HOST=mailpit
MAILPIT_SMTP_PORT=1025
MAILPIT_WEB_URL=http://localhost:8025
APP_ENV=development
CORS_ORIGINS=http://localhost:5173
```

---

## 9. Where to look next

| You want to know | Read |
|---|---|
| What the product is | [`PRD.md`](PRD.md) |
| What to build, in what order | [`roadmap.md`](roadmap.md) |
| The contract every spec shares | [`specs/00_conventions.md`](specs/00_conventions.md) |
| Why the stack is what it is | [`decisions/`](decisions/) |
| How to run it | [`README.md`](README.md) |