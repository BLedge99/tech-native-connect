# Bootcamp Connect

> Connect the software developers with the business developers sitting three
> rows away from them.

A bootcamp puts software developers and business developers in the same
building, on the same schedule, for the same course. They never actually meet.
The developers want a business partner who can sell what they build. The
business developers want someone who can build the thing they keep describing.
This app lists the people on your course, ranks the ones you overlap with, and
tells you why.

**Status:** all nine features implemented. 240 backend tests, 26 component tests,
11 E2E tests, 10 evidence recordings. Demo target 15 October 2026.

---

## Quick start

Requires Docker Desktop (WSL2 backend supported).

```powershell
.\run.bat              # build + start everything
.\run.bat panel        # open the dev panel at http://localhost:5173/dev
```

That's it. First build takes a few minutes (Python wheels, npm install). After
that, `run.bat` is enough.

| Command | What it does |
|---|---|
| `run.bat` / `run.bat dev` | Build and start all services |
| `run.bat build` | Build images only |
| `run.bat down` | Stop services (keeps data) |
| `run.bat clean` | Stop and delete all data |
| `run.bat logs` | Follow logs |
| `run.bat panel` | Open the dev panel in your browser |

### Services

| Service | URL |
|---|---|
| Frontend | http://localhost:5173 |
| Backend API | http://localhost:8000 |
| API docs (Swagger) | http://localhost:8000/docs |
| Mailpit inbox | http://localhost:8025 |
| Adminer (DB GUI) | http://localhost:8080 |
| Dev panel | http://localhost:5173/dev |

### Demo logins

| Email | Password | Role |
|---|---|---|
| `priya@example.com` | `demo-password-123` | Business developer |
| `ben@bootcamp.example.com` | `bootcamp-dev-admin` | Admin |

---

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

---

## Admin panel

The admin panel at `/admin` has four tabs:

| Tab | What it does |
|---|---|
| **Overview** | Five counts: total users, active, new this week, connections made, project ideas |
| **Users** | Search by email or name. Activate/deactivate, grant/revoke admin, view profile. Paginated with "Load more" |
| **Reference** | Manage courses, skills, and interests. Add, rename (skills), delete (skills). Paginated |
| **Audit** | Read-only log of admin actions with timestamp, action, target, and metadata. Paginated |

Admin access is granted by an existing admin via the Users tab. Non-admins who
try to reach `/admin` get a 403 page.

---

## Dev panel

The dev panel at `/dev` is a development tool — not part of the product. It has
two tabs:

| Tab | What it does |
|---|---|
| **Services** | Cards linking to every service (main site, API docs, Mailpit, Adminer, backend). Shows Adminer login credentials |
| **Videos** | Grid of evidence recordings with `<video>` players, served from the backend |

No authentication required. Only active when `APP_ENV=development`.

---

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

---

## Tests

```powershell
docker compose exec -T backend pytest tests                      # 240 passed
docker compose exec -T frontend npx vitest run                   # 26 passed
docker compose exec -T frontend npx tsc --noEmit                 # clean
docker compose exec -T frontend npx playwright test              # 11 passed
```

The E2E suite resets the demo data before each run. **Restart the frontend
container after editing frontend source** — Vite's hot reload does not reliably
pick up changes on this setup.

---

## Evidence videos

Ten recorded videos in [`videos/`](videos/), viewable in the dev panel. Two of
them put two browsers side by side in a single file, so live messaging is
visible without cutting.

```powershell
docker compose exec -T frontend npx playwright test -c playwright.videos.config.ts
./scripts/build-videos.sh
```

---

## Documentation

| Start here | What it gives you |
|---|---|
| **[`AGENTS.md`](AGENTS.md)** | **Read this first.** Tech stack, conventions, the six non-negotiable product rules, how to work. |
| **[`handoff.md`](handoff.md)** | Live build state, known bugs, and the gotchas that will cost you an hour. |
| [`PRD.md`](PRD.md) | Who the app serves, what it does, what is in and out of scope, success criteria. |
| [`roadmap.md`](roadmap.md) | The nine features in dependency order, each with a finish line, plus the cut line. |
| [`specs/`](specs/) | One document per feature, each ending with an *As built* section. |
| [`decisions/`](decisions/) | Twelve architecture decision records. Start at [0001](decisions/0001-fastapi-and-react.md). |

---

## Repository layout

```
.
├── AGENTS.md            entry point for humans and AI agents
├── handoff.md           live build state, known bugs, gotchas
├── PRD.md               what the product is
├── roadmap.md           what to build, in what order, and what is built
├── specs/               one doc per feature, plus deferred_*.md
├── decisions/           numbered ADRs
├── run.bat              Windows wrapper for docker compose
├── backend/             FastAPI + SQLAlchemy + Alembic + pytest
│   ├── app/             config, models, routers, services, realtime, dev
│   ├── alembic/         migrations
│   └── tests/           unit/ and integration/
├── frontend/            Vite + React + TypeScript + Tailwind
│   ├── src/             api/, hooks/, components/, pages/, routes/
│   └── tests/           Playwright E2E and its global setup
└── docker-compose.yml   db, mailpit, backend, frontend, adminer
```

---

## Team

Ben · Joey · James · Alys · Mick

Bootcamp Connect — TechNative Digital
