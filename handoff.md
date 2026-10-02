# Handoff

**Date:** 2 October 2026
**Deadline:** demo 15 October
**Written for:** whoever picks this up next — human or AI agent

Read [`AGENTS.md`](AGENTS.md) first. This file covers only **what state the
code is actually in**, which is not derivable from the specs.

---

## 1. Test status

| Suite | Command | Result |
|---|---|---|
| Backend unit + integration | `docker compose exec -T backend pytest tests` | **230 passed** (~6 min) |
| Frontend components | `docker compose exec -T frontend npx vitest run` | **26 passed** |
| Frontend typecheck | `docker compose exec -T frontend npx tsc --noEmit` | clean |
| E2E (Playwright) | `docker compose exec -T frontend npx playwright test` | **11 passed**, ~1 flake in 5 runs (§5.1) |

---

## 2. What exists

### Documentation — committed as `6eeb4dd`

`AGENTS.md`, `PRD.md`, `roadmap.md`, `README.md`, `specs/00`–`09`,
`specs/deferred_*.md` (4), `decisions/0001`–`0012` + README, `.gitignore`,
`.env.example`, `handoff.md`.

### Code — uncommitted

```
docker-compose.yml     db, mailpit, backend, frontend. Single-worker warning in
                       comments. TEST_DATABASE_URL set on the backend service.
.env                   gitignored

backend/app/
  config.py db.py errors.py dependencies.py realtime.py main.py seed.py
  schemas.py serializers.py
  models/    enums, user, profile, connection, thread, notification, idea
  services/  auth, profiles, matching, match_service, connections, messaging,
             notifications, ideas, mailer, pagination
  routers/   auth, users, matches, connections, messaging (+ws), notifications,
             ideas, admin
  alembic/versions/0001_initial.py
  tests/unit/          test_matching, test_connections, test_auth, test_notifications
  tests/integration/   test_permissions, test_rules, test_websocket, test_admin,
                       test_ideas

frontend/src/
  api/      types.ts, client.ts
  hooks/    session.tsx, useQuery.ts, websocket.tsx
  components/ ui.tsx, MatchCard.tsx, Notifications.tsx, MatchCard.test.tsx
  pages/    LandingPage, AuthPages, HomeFeed, ProfilePages, MatchesPage,
            ConnectionsPage, MessagingPage, NotificationsPage, IdeasPage, AdminPage
  routes/   App.tsx, App.test.tsx
frontend/tests/  helpers.ts, global-setup.ts, demo.spec.ts
frontend/        playwright.config.ts, vitest.config.ts, vite.config.ts
```

---

## 3. Bugs found and fixed in this session

Ten real bugs, all found by tests rather than by reading. The first two would
have broken the demo.

| Bug | Symptom | Fix |
|---|---|---|
| **CSRF blocked registration entirely** | Register threw "Not signed in yet." — nobody could sign up | `client.ts` no longer throws when there is no token; register/login *create* the session |
| **Three WebSockets per page** | Bell, toast stack and chat each opened their own socket. The chat's socket lost the race and never subscribed, so **live messages silently never arrived** | New `hooks/websocket.tsx`: one provider-owned socket per page with `useSocketListener` / `useThreadSubscription`. `hooks/useWebSocket.ts` deleted |
| **Login/register responses had no `csrf_token`** | Only `/users/me` returned it, so the token was null for up to a second after signup. Every mutation 403'd — including logout | Backend `_session_body()` adds `csrf_token` (from `session.csrf_token`, not the session token) to both auth responses |
| **`/users/me` race logged users out** | The initial 401 session check resolved *after* registration and clobbered the new session | `sessionGeneration` ref; `adopt()` on register/login cancels the in-flight check |
| **Profile page offered Connect twice** | After sending a request the person vanishes from `/matches` (matching excludes pending), so state fell back to `none`. Backend 409'd but the UI lied | `PublicProfilePage` reads state from `/connections`, not from the match list |
| **"Message" was a dead link** | Linked to `/messages` (the list) when no thread exists. Threads are created lazily, so a fresh connection had no thread | `ConnectionAction` takes `threadId`/`onOpenThread`; renders a button that creates the thread, or a link once one exists. Fixed on both profile and connections pages |
| **`alert()` blocked the page** | `PublicProfilePage` used `alert()` on error, freezing the page | Replaced with inline `role="alert"` |
| **Malformed WS frame killed the socket** | One bad frame dropped the connection | Catches non-JSON, replies with an error, keeps the loop alive |
| **Unhandled WS error dropped every connection** | Exception in one frame became an ASGI error | Broad `except Exception` that logs and falls through |
| **`receiver_profile_incomplete` returned `validation_error`** | Spec 05 §4 requires its own code | No longer subclasses `ValidationFailed` |
| **Sending a request skipped the sender's completeness check** | Incomplete users could send | `send_request` raises `profile_incomplete` |
| **`next_cursor` always `None`** | Specs require cursor pagination everywhere | Implemented on ideas, notifications, messages, matches via `services/pagination.py` |
| **Two multi-selects shared a placeholder** | Ambiguous selectors; worse, a screen-reader user could not tell skills from interests | Distinct placeholders **and** `aria-label`s |
| **Search input had no accessible name** | | `aria-label` added |
| **`peerTyping` was dead state** | Typing indicators are out of scope | Removed |

Also: `require_session` returns a tuple (three call sites had got this wrong),
error messages were empty because the message string sat *after* an assignment
so was not a docstring, and `/users/{id}` shadowed `/users/me`.

---

## 4. What changed in the code's shape

- **`frontend/src/hooks/websocket.tsx` is new** and replaces the per-component
  hook. One socket per page. Read it before touching anything realtime.
- **`frontend/tests/global-setup.ts` is new.** It deletes non-seed users before
  an E2E run. Without it the suite goes flaky after a few runs — accumulated
  test users make `.first()` selectors ambiguous, which looks like an app bug
  and is not one.
- **`services/pagination.py` is new.**
- `ConnectionAction` gained `threadId` and `onOpenThread`.

---

## 5. Known issues

### 5.1 One E2E test flakes ~1 run in 5

`the demo path › request → accept → message, live in two windows`

Fails inside `openConversation` at
`await expect(page.getByLabel('Message')).toBeVisible()` — the composer never
appears. It passes about 80% of runs.

**Likely cause:** socket subscription timing. `useThreadSubscription` only
subscribes once `status === 'open'`. If the page renders, the composer shows,
the test proceeds — but the subscription may not have been sent yet, so the
*live delivery* assertion later can lose a race. The fix is almost certainly in
the test, not the app: wait for the socket to be subscribed before sending, e.g.

```ts
// In openConversation, after the composer appears:
await page.waitForFunction(() => performance.now() > 0) // no-op placeholder
```

Better: have `openConversation` wait for the `subscribed` acknowledgement. The
server sends `{"type":"subscribed","thread_id":…}`; the client ignores it. The
laziest correct fix is for `useThreadSubscription` to resolve a promise on
`subscribed` and have the test await it, or simply add a short
`await page.waitForTimeout(500)` after opening the conversation and accept that
as a documented tradeoff. **Do not add a blanket retry to hide it** — a flaky
centrepiece test is worse than a slow one.

### 5.2 Everything else

- **`window.location.href` remains in `IdeaFormPage`** after posting/editing an
  idea. Works, loses SPA navigation. `ConnectionsPage` and `MatchesPage` were
  converted to `useNavigate`.
- **`ProfilePages` uses `<a href>`** for internal links via `Linkish`. Full page
  reloads. Cosmetic.
- **`useQuery` spreads `deps` into a dependency array.** Works, cannot be
  statically verified, ESLint will flag it.
- **Magic link flow has no E2E test.** Mailpit's REST API
  (`GET /api/v1/messages`) makes this easy. It is the one auth path with no
  browser-level coverage.
- **`AdminPage` and `IdeaFormPage`/`IdeaDetailPage` have no component tests.**
- **Spec "Implementation status" lines all still say Not started.** All nine
  features are implemented and tested — the docs now contradict the code.

---

## 6. Deliberate deviations from the specs

Five, all additive. None is a bug.

| Deviation | Why |
|---|---|
| Admin emails are `@bootcamp.example.com` | `EmailStr` rejects `.local`, so the spec's address returns `422` on login. `seed.py` updated; live DB migrated by SQL |
| `POST /api/v1/connections/{id}/thread` | Not in spec 05. Threads are created lazily on first message, so a client had no way to get a thread id before its first message |
| `csrf_token` in `/users/me`, `/auth/register` and `/auth/login` | Not in specs 02. The cookie is httpOnly, so the token must come from somewhere |
| `named volumes` for `pgdata` and `venv` | Needed for `--reload` to survive a container restart without a rebuild |
| One WebSocket per page | Spec 06 §4 implies one registry, not one socket per component |

**Reconcile these in the specs** if you want the documents to match reality:
`specs/02` §3 and §7, `specs/05` §4, `specs/06` §4.

---

## 7. Not done

| Missing | Where | Priority |
|---|---|---|
| Fix the live-chat flake | §5.1 | **High** — it is the demo's centrepiece test |
| Update spec Implementation status + roadmap checkboxes | §5.2 | **High** — docs contradict code |
| Magic-link E2E test | §5.2 | Medium |
| `IdeaFormPage` → `useNavigate`, `Linkish` → `<Link>` | §5.2 | Low |
| Admin / ideas component tests | §5.2 | Low |
| Single `docker compose` command that runs all four suites | — | Low |

---

## 8. First 30 minutes for whoever is next

```bash
docker compose up -d --build
curl localhost:8000/api/v1/health          # {"status":"ok","database":"ok"}

docker compose exec -T backend pytest tests               # 230 passed, ~6 min
docker compose exec -T frontend npx vitest run            # 26 passed
docker compose exec -T frontend npx tsc --noEmit           # clean
docker compose exec -T frontend npx playwright test       # 11 passed
```

If a Playwright failure is mysterious, read
`frontend/test-results/*/error-context.md` — each contains the full
accessibility tree at the moment of failure, which usually shows the problem
without re-running anything.

Demo logins:

- `priya@example.com` / `demo-password-123` — business developer, has a pending
  request out and an accepted connection
- `ben@bootcamp.example.com` / `bootcamp-dev-admin` — admin
  (`SEED_ADMIN_PASSWORD` in `.env`)

All demo users are in `backend/app/seed.py`.

---

## 9. Things that will bite you

- **Restart the frontend container after editing frontend source.** The bind
  mount is live but Vite's HMR does not reliably pick up changes on this
  WSL/Windows setup — twice a test failed against a stale module and cost real
  time. `docker compose restart frontend`, then wait ~15 s.
- **One uvicorn worker. Non-negotiable.** The WebSocket registry is per-process;
  two workers silently lose messages. Commented in `docker-compose.yml`.
- **`require_session` returns a tuple.** `pair = Depends(require_session)` then
  `session, user = pair`.
- **No lazy SQLAlchemy relationships.** `User.profile` is `lazy="joined"`, the
  rest `selectin`. Touching one lazily raises `MissingGreenlet` at runtime. Load
  the other party with `db.get`, never `request.sender`.
- **Integration tests recreate the schema per test.** Do not make the engine
  session-scoped — asyncpg connections cannot cross event loops.
- **The `auth` test fixture returns its own `client` per call.** A cookie jar
  holds one session, so two `await auth()` calls are two browsers.
- **Never `select(Photo)`.** `photos.data` is a `bytea`.
- **Frontend `fetch` must go through `src/api/client.ts`.** It adds
  `credentials: 'include'` and the CSRF header.
- **`register()` in `frontend/tests/helpers.ts` must wait for the URL to leave
  `/register`.** Waiting on the h1 is not enough — it is already there.
- **Playwright `getByRole(name: 'Message')` also matches the nav link
  "Messages".** Use `exact: true`. This cost an hour.
- **`backend/tests/conftest.py` sets `DATABASE_URL` before importing app
  config.** The engine is built at import time; redirecting afterwards points
  tests at the dev database.