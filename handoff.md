# Handoff

**Date:** 2 October 2026
**Deadline:** demo 15 October
**Written for:** whoever picks this up next — human or AI agent
**Docs status:** specs reconciled with code 2 Oct. `c4c7a00`.

Read [`AGENTS.md`](AGENTS.md) first. This file covers only **what state the
code is actually in**, which is not derivable from the specs.

---

## 1. Test status

| Suite | Command | Result |
|---|---|---|
| Backend unit + integration | `docker compose exec -T backend pytest tests` | **240 passed** (389s) |
| Frontend components | `docker compose exec -T frontend npx vitest run` | **26 passed** |
| Frontend typecheck | `docker compose exec -T frontend npx tsc --noEmit` | clean |
| E2E (Playwright) | `docker compose exec -T frontend npx playwright test` | **11 passed** (1.4 min) |
| Evidence recordings (separate) | `docker compose exec -T frontend npx playwright test -c playwright.videos.config.ts` | **10 passed** (5.5 min) — see §6 |

**Final verification, 2 Oct 2026, after the cursor pagination and input
validation fixes:** all five commands above passed in WSL Docker. The backend
suite first exposed three stale admin test expectations after reference lists
changed to page envelopes; those tests were updated to read `items` and expect
the endpoint's HTTP 200 response, then the full backend suite passed. The
frontend component run emits React Router future-flag and React `act(...)`
warnings; these are non-failing cleanup opportunities.

---

## 2. What exists

### Documentation — committed as `6eeb4dd`, reconciled in `c4c7a00`

`AGENTS.md`, `PRD.md`, `roadmap.md`, `README.md`, `specs/00`–`09`,
`specs/deferred_*.md` (4), `decisions/0001`–`0012` + README, `.gitignore`,
`.env.example`, `handoff.md`.

All of the above are committed as `c4c7a00`. As part of that commit the
spec-status lines were corrected, Definition-of-done boxes ticked, and dated
*As built* sections appended to `specs/00`–`09` and all four `deferred_*.md`
files. `roadmap.md` gained a §Deviations table and a §Status summary;
`AGENTS.md` §1, `PRD.md` and `README.md` were brought in line. **The documents
now describe the code rather than contradicting it.**

### Code — committed as `c4c7a00`

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

Found 2 Oct, after the suite had gone green, by reading
`docker compose logs backend` rather than by reading code — the tests were all
passing while the server was throwing:

| Bug | Symptom | Fix |
|---|---|---|
| **Logout sent a body with its 204** | `JSONResponse(None, 204)` serialises a literal `null`, and starlette omits `content-length` on a 204 — so `BaseHTTPMiddleware` raised `RuntimeError: Response content longer than Content-Length` *after* the status was already on the wire. Every logout logged a 500 nobody received | `logout` returns a bare `Response(status_code=204)` and takes the already-resolved session from `get_current_session` instead of re-loading it |
| **`last_used_at` written on every request** | `load_session` assigned the attribute, leaving the ORM row dirty; SQLAlchemy autoflushes on the next query, so a session revoked by a concurrent logout turned that flush into `StaleDataError: UPDATE statement on table 'sessions' expected to update 1 row(s); 0 were matched` — a **500 on `/notifications` and `/notifications/unread-count`**, endpoints that have nothing to do with sessions | Throttled to a Core `UPDATE` at most once every 5 minutes. The ORM row stays clean, so a vanished session is a no-op instead of an exception |
| **`ConnectionsPage` swallowed failures in `alert()`** | A failed "Message" click showed a dialog and navigated nowhere. Playwright auto-dismisses dialogs, so in a test it presented as *"the composer never appears"* — indistinguishable from the flake in §5.1 | Inline `role="alert"`, same as `PublicProfilePage` |

Three regression tests in `tests/integration/test_rules.py` under a new
*Sessions* section: 204 carries no body, logout really revokes, and a session
revoked mid-request does not 500.

**Lesson worth keeping:** a green suite is not a quiet server. `docker compose
logs backend | grep -i unhandled` found three real bugs that 263 passing tests
had missed, because every one of them happened *after* a successful response or
on a race the tests never provoke.

### 3b. Five more bugs, found while building the video suite

Same method — drive the app for real and read what the server says. Every one
of these was live in the demo and invisible to the existing tests. **None of
them is a cosmetic issue: three were features that did not work at all.**

| Bug | Symptom | Fix |
|---|---|---|
| **Magic link 500'd for every real user** | `send_magic_link` is sync but the route awaited it. Python evaluated the call — **sending the mail** — then raised `TypeError: object bool can't be used in 'await' expression`. So the link arrived and the user got a 500 and no confirmation. Spec 02, on the one auth path that had no test | `send_magic_link` is `async` and hands the blocking smtplib call to `anyio.to_thread.run_sync` |
| **"Mark all read" never worked** | `PATCH /notifications/read-all` returned `422`. `@router.patch("/{notification_id}")` was declared *first*, so FastAPI matched it and tried to parse `read-all` as a UUID. The button did nothing, silently | Literal `/read-all` moved above the parameterised route |
| **Bell badge ignored "Mark all read"** | The page refetched, the bell did not — so the badge still said "3 unread" after everything was read. The bell's own comment promises the badge "cannot disagree with the page it links to" (specs/07 §6). It could | Page dispatches a `notifications:changed` window event; the bell listens and re-counts |
| **A message could vanish from your own screen** | `loadHistory` overwrote the message list wholesale. Send while the "socket opened → refetch history" effect is still in flight and your own message disappears: the POST returned 201, the composer cleared, no bubble. Nothing puts it back, because the sender never gets a socket frame for its own message | `loadHistory` merges by id instead of replacing. Messages are never deleted, so a union cannot go stale |
| **The centrepiece E2E test was over budget** | `timeout: 30_000`, actual ~33s. It failed roughly 1 run in 5 while every assertion had passed — this *was* the flake in §5.1 | Timeout raised to 90s, with a comment saying why |

Two more regression tests in `tests/integration/test_rules.py`: the magic link
returns 202 for a real account, and `read-all` actually clears the badge while
leaving the list intact.

**The route-ordering trap is worth checking any time a router gains a literal
path.** It was audited across all nine routers afterwards and
`/notifications/read-all` was the only instance.

**Also caught: a regression I introduced.** The `last_used_at` throttle in §3
was written as a Core `UPDATE` and never committed. Nothing else commits on a
read-only request, so `last_used_at` never advanced — every later request
rewrote it and held a row lock on the session for the life of the request. It
locked the E2E suite hard enough to hang a run for 180s. The fix is one line
(`await db.commit()`), with a comment explaining why committing that early is
safe. **Worth remembering that "uncommitted" and "harmless" are not the same
thing.**

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
- **`ThreadPage.loadHistory` merges instead of replacing** (§3b). If you touch
  message rendering, keep that.
- **`NOTIFICATIONS_CHANGED`** is exported from `components/Notifications.tsx`
  and dispatched by `NotificationsPage` on both read paths. Anything else that
  marks notifications read must dispatch it too, or the badge drifts again.
- **`/api/v1/threads` is an envelope, not an array** (§11). It returned
  `Thread[]` until the pagination review. Same for `/connections`, and
  `/admin/users` + `/admin/audit` now take a `cursor` and cap `limit` at 100.
  If you add a list endpoint, copy the shape from `services/pagination.py`
  rather than inventing one.

---

## 5. Known issues

### 5.1 The live-chat flake — root cause found 2 Oct

`the demo path › request → accept → message, live in two windows`

**It was never a socket race. It was the test timeout.** The config had
`timeout: 30_000`; the test measures ~33s on this machine. It failed with
`Test timeout of 30000ms exceeded` while every single assertion had already
passed — the failure point moved around from run to run (once on the profile
form, once on the connections page, once on the thread), which is the signature
of a budget problem rather than a logic problem. Confirmed by running it with
`--timeout=45000`: **passed in 32.9s**. Fixed by raising the budget to 90s,
which still fails a genuine hang, because a hang runs past 180s.

The earlier guess recorded here — socket subscription timing — was wrong, and
the reasoning against it is worth keeping:

- The failure was at composer *visibility*, not at the later live-delivery
  assertion. A subscription race cannot stop the composer rendering; the
  composer is not gated on socket state.
- `useThreadSubscription` cannot lose a subscription: `subscribe()` records the
  thread in `wanted` whether or not the socket is open yet, and `onopen`
  re-sends every entry in `wanted` after a reconnect.

Two real defects *did* present exactly like this flake and are now fixed — the
`ConnectionsPage` `alert()` in §3, and the message-vanishing bug in §3b.

**Do not add a blanket retry or a `waitForTimeout` to hide anything here.** If a
timeout comes back, `frontend/test-results/*/error-context.md` holds the
accessibility tree at the moment of failure, and it will usually name the step.
The test is the demo's centrepiece; a slow centrepiece beats a flaky one.

### 5.2 Everything else

- **`window.location.href` remains in `IdeaFormPage`** after posting/editing an
  idea. Works, loses SPA navigation. `ConnectionsPage` and `MatchesPage` were
  converted to `useNavigate`.
- **`ProfilePages` uses `<a href>`** for internal links via `Linkish`. Full page
  reloads. Cosmetic.
- **`useQuery` spreads `deps` into a dependency array.** Works, cannot be
  statically verified, ESLint will flag it.
- **Magic link has no E2E test in `tests/`.** It now has an integration test
  (§3b) and is driven end-to-end by recording 02, so it is no longer untested —
  but there is still nothing in the normal suite that would catch a regression
  in the browser flow. Mailpit's REST API (`GET /api/v1/messages`) makes this
  easy; see `fetchMagicLink()` in `tests-videos/helpers.ts` for the extraction.
- **`AdminPage` and `IdeaFormPage`/`IdeaDetailPage` have no component tests.**
- **`AdminPage` and `IdeasPage` still call native `alert()` on failure.** The
  app degrades fine, but a dialog blocks the page, and Playwright
  auto-dismisses dialogs — so a failure there is invisible to a test. This is
  the same class of bug as the `ConnectionsPage` one in §3. `ConnectionsPage` is
  fixed; these two are not.
- **✅ Spec status lines updated.** All nine say *Implemented*, all nine have
  ticked Definition-of-done boxes, and every spec — plus `00_conventions.md` and
  all four `deferred_*.md` — now ends with a dated *As built* section. The
  `roadmap.md` deviations table, `AGENTS.md` §1, `PRD.md` and `README.md` were
  updated in the same pass. Docs now match the code.

---

## 6. Evidence videos

Nine recorded videos, one per feature, in `videos/`. Two of them put **two
browsers side by side in one file** so live messaging is visible without
cutting.

```bash
# 1. record (~5.5 min, writes frontend/videos-raw/*.webm)
docker compose exec -T frontend npx playwright test -c playwright.videos.config.ts

# 2. composite + convert to mp4 (~1 min, writes videos/*.mp4)
./scripts/build-videos.sh
```

| File | Feature | What it shows |
|---|---|---|
| `01-landing-page-the-pitch-logged-out.mp4` | spec 01 | The pitch, the three steps, the CTA |
| `02-registration-login-and-magic-link.mp4` | spec 02 | Sign up, sign in, sign out, and a real magic link pulled out of Mailpit and followed |
| `03-profile-building-one-from-nothing.mp4` | spec 03 | The locked gate, role/skills/interests/course/bio, a real PNG upload, the finished profile |
| `04-matching-and-search.mp4` | spec 04 | Ranked matches with reasons, role filter, skill and interest search, a full public profile, sending a request |
| `05-connection-requests-two-windows-side-by-side.mp4` | spec 05 | **Two browsers.** A signs up, finds B, requests; B sees it and accepts. Includes rule 2 — A cannot message until B accepts |
| `07-live-messaging-two-windows-side-by-side.mp4` | spec 06 | **Two browsers, the centrepiece.** Same thread in both, live delivery each way, both windows reload, still live |
| `08-notifications.mp4` | spec 07 | The badge, the dropdown, the grouped page, mark all read clearing the badge |
| `09-project-ideas-board.mp4` | spec 08 | Browsing, filtering, a business developer posting, then a developer finding it and expressing interest |
| `10-admin-screens.mp4` | spec 09 | 403 for a non-admin, then overview, user search, audit log, reference data |

There is no `06` file: spec 06 is covered by `07`, which is the two-window
messaging recording.

### How it works

- **Captions are a DOM overlay**, not an ffmpeg `drawtext` filter — `say()` in
  `tests-videos/captions.ts` injects a bar at the bottom of the page and lifts
  the app clear of it with `body { padding-bottom }`. An overlay across the top
  hid the app's own nav on every page, and the nav is part of the evidence.
- **Two windows are two browser contexts** with separate cookie jars.
  `twoWindows()` gives each one `recordVideo`, labels it with a page global, and
  navigates it immediately so no panel is ever a blank white rectangle.
- **ffmpeg runs in a container** (`jrottenberg/ffmpeg:7-ubuntu`). The host has
  none, and the copy bundled with Playwright is stripped to `scale` and VP8 — no
  `hstack`, no `libx264`. `build-videos.sh` pads both panes with `tpad` before
  stacking, because the two recordings do not stop at the same millisecond.

### Gotchas that cost real time here

- **`page.video().saveAs()` deadlocks** if the page is still open — it waits for
  the video to be finalised, and fixtures tear down in reverse order, so the page
  is still alive. `tests-videos/record.ts` closes the context first.
- **The recordings must be repeatable.** They assert exact message counts, so
  `resetThread()` and `deleteIdeasTitled()` in `tests-videos/helpers.ts` wipe
  prior runs' leftovers first. Every helper there that mutates demo data is
  scoped to exact values; there is no API for it and there should not be one.
- **A receiver only gets live delivery while it is sitting on the thread page.**
  Navigating the second window to `/messages` (the list) unsubscribes it, and a
  message sent after that will not appear. This looks exactly like a broken
  socket and is not — it cost a full debugging cycle.
- **Fresh test users accumulate.** `"Tomas Nowak T82"` from an earlier run made
  a `getByRole('heading', {name: /Tomas/})` ambiguous. The video config reuses
  `tests/global-setup.ts`, and seeded names are matched with `exact: true`.
- **`videos/` and `frontend/videos-raw/` are untracked and not gitignored.**
  Roughly 4.7 MB of mp4. Decide whether to commit them before the demo or
  regenerate them; do not leave them showing up as noise in `git status`.

---

## 7. Deliberate deviations from the specs

Five, all additive. None is a bug.

| Deviation | Why |
|---|---|
| Admin emails are `@bootcamp.example.com` | `EmailStr` rejects `.local`, so the spec's address returns `422` on login. `seed.py` updated; live DB migrated by SQL |
| `POST /api/v1/connections/{id}/thread` | Not in spec 05. Threads are created lazily on first message, so a client had no way to get a thread id before its first message |
| `csrf_token` in `/users/me`, `/auth/register` and `/auth/login` | Not in specs 02. The cookie is httpOnly, so the token must come from somewhere |
| `named volumes` for `pgdata` and `venv` | Needed for `--reload` to survive a container restart without a rebuild |
| One WebSocket per page | Spec 06 §4 implies one registry, not one socket per component |

**✅ Reconciled in the specs** 2 Oct 2026. Each row now has a dated *As built*
section citing it: `specs/02` §13.1–13.2, `specs/05` §11.1, `specs/06` §10.1,
`specs/00_conventions.md` §13.3. They are also collected in one table under
`roadmap.md` §Deviations from this plan.

---

## 8. Not done

| Missing | Where | Priority |
|---|---|---|
| ~~Fix the live-chat flake~~ | §5.1 | ✅ Root cause found and fixed 2 Oct — the timeout was too low, not a socket race |
| ~~Update spec Implementation status + roadmap checkboxes~~ | §5.2 | ✅ Done 2 Oct |
| ~~Magic link 500, mark-all-read 422, stale badge, vanishing message~~ | §3b | ✅ All four fixed 2 Oct, with regression tests |
| Decide whether `videos/` gets committed | §6 | **Medium** — the demo is on 15 Oct and these are the evidence |
| Component test for the `loadHistory` merge | §3b | Medium — fixed by evidence, not by a test that fails without the fix |
| Magic-link E2E test in `tests/` | §5.2 | Medium |
| Replace native `alert()` in `AdminPage` / `IdeasPage` | §5.2 | Medium — same class as the §3 bug, still unfixed |
| `IdeaFormPage` → `useNavigate`, `Linkish` → `<Link>` | §5.2 | Low |
| Admin / ideas component tests | §5.2 | Low |
| Single `docker compose` command that runs all four suites | — | Low |

**Suggested, not started.** None of these are in `deferred_*.md`, so they are
yours to scope rather than forbidden:

- A single continuous "demo path" take — sign up through to live message in one
  uncut video. The per-feature videos are better evidence; this is better theatre.
- Component tests for `ThreadPage`, `NotificationsPage` and `ConnectionsPage`.
  The merge in §3b and the inline error in §3 are both logic that no HTTP test
  can pin down.
- A route-shadowing guard in the integration suite: assert that every literal
  path in every router is reachable, so §3b's class of bug cannot come back.

---

## 9. First 30 minutes for whoever is next

```bash
docker compose up -d --build
curl localhost:8000/api/v1/health          # {"status":"ok","database":"ok"}

docker compose exec -T backend pytest tests               # 235 passed, ~5.5 min
docker compose exec -T frontend npx vitest run            # 26 passed
docker compose exec -T frontend npx tsc --noEmit           # clean
docker compose exec -T frontend npx playwright test       # 11 passed

# optional: re-record the evidence videos (§6)
docker compose exec -T frontend npx playwright test -c playwright.videos.config.ts
./scripts/build-videos.sh
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

## 10. Things that will bite you

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
- **A green suite is not a quiet server.** Check
  `docker compose logs backend | grep -iE "unhandled|staledata|traceback"`
  after a run. Seven real bugs lived there while all four suites passed,
  because each one fired *after* a successful response, on a race the tests
  never provoke, or on a route no test calls.
- **A passing test is not a working feature either.** Three features were
  simply broken — magic link, mark all read, and the bell badge — with full
  suites green. Coverage counted the calls; nothing checked the outcome. When
  adding a test, assert the *user-visible result*, not that the endpoint
  responds.
- **Check a failure's position across runs.** The centrepiece flake moved
  between the profile form, the connections page and the thread. A moving
  failure point means a budget or timing problem, not a logic bug.
- **`backend/tests/conftest.py` sets `DATABASE_URL` before importing app
  config.** The engine is built at import time; redirecting afterwards points
  tests at the dev database.

---

## 11. Review findings — 2 October 2026

The following issues were found in a read-only code review and are being fixed
one at a time. The specs remain unchanged; the shared conventions and feature
specs already define the expected behavior.

| Finding | Impact | Status |
|---|---|---|
| WebSocket message validation differs from HTTP validation | Oversized bodies can be stored, and non-object JSON frames can terminate the socket | Fixed 2 Oct: validate object frames and enforce 1–2000 trimmed characters |
| Several list endpoints do not implement cursor pagination | Connection/admin lists can silently omit rows or grow without bound | Fixed 2 Oct: connections, admin users/audit/reference lists, and threads use cursor pages; screens expose Load more |
| Malformed pagination cursors could cause server errors | Cursor JSON and UUID parsing happened without converting bad client input to a 4xx response | Fixed 2 Oct: shared, match, thread, and admin reference decoders return `400 invalid_cursor` |
| Magic-link consumption is not atomic | Simultaneous verification requests may both consume one single-use token | Fixed 2 Oct: row lock serializes consumption; later verifier sees the used state |
| Thread list performs per-thread database queries | Query count grows with the user's thread count | Fixed 2 Oct: one page query joins the latest message and computes unread count; database work is bounded to the requested page |

### Verification of the initial review fixes — 2 Oct 2026

All four suites re-run. **First pass: 4 backend tests failed.** All four were
the *same* root cause, and it was in the tests, not the code.

| Failing test | Cause | Fix |
|---|---|---|
| `test_rules.py::test_thread_list_only_contains_participants` | `/threads` returned a **bare JSON array**; the pagination fix wrapped it in the `{"items", "next_cursor"}` envelope. `for thread in threads` then iterated the two dict *keys* → `TypeError: string indices must be integers` | Read `["items"]` |
| `test_rules.py::test_accept_does_not_create_a_thread` | Same: `.json() == []` is now `.json()["items"] == []` | `["items"]` |
| `test_ideas.py::test_interest_does_not_create_a_connection_or_thread` | Same | `["items"]` |
| `test_admin.py::test_overview_counts_match_reality` | Two causes. `?limit=200` now **422s** — the pagination fix lowered the cap to 100 to match `specs/00_conventions.md` §5, so the `KeyError: 'items'` was FastAPI's validation body, not a page | `limit=100`, plus an assertion that `limit=101` is rejected so the cap cannot silently drift again |

**Lesson, and it is the mirror image of §3.** A response-shape change is an
API change: the tests that pin the shape are the tests that break, and here
they broke *loudly and correctly*. Do not "fix" a red test by reverting the
envelope — `specs/00_conventions.md` §5 requires it, and four other list
endpoints already used it. **Before changing the shape of any endpoint, grep
every caller**: `backend/tests/`, `frontend/src/api/client.ts` and the page
components. Here the frontend was already updated (`client.ts` returns
`Page<Thread>` and both admin/connections/messages take a `cursor`) but four
tests were missed, which is the exact pattern §3's stale-module bug predicts.

**Two of the four fixes had no test at all**, so they are now covered:

- `test_websocket.py::test_socket_send_validates_like_http` — a JSON *array*
  frame, a 2001-character body and a whitespace-only body are each refused with
  an error frame, nothing is persisted, the socket still answers `ping`, and an
  exactly 2000-character message is accepted.
- `test_rules.py::test_thread_and_connection_lists_page_by_cursor` — page 2 of
  `/connections` and `/threads` shares no id with page 1 and reports
  `next_cursor: null` on the last page. This is the assertion that catches a
  missing tiebreaker column, which is the whole reason §5 mandates one.

### Review correction — empty-thread cursor behavior

The initial review note incorrectly described empty threads as repeating on
every page. They sort after message-bearing threads; the first cursor after a
message can include them, and once a page ends on an empty thread its cursor
uses the null-message branch, which advances by `(thread.created_at, thread.id)`.
A regression test now pages through one message-bearing thread and several
empty threads and checks that no thread repeats.

The admin courses, skills and interests lists were also found to be exceptions
to the shared pagination rule. They now return the standard page envelope and
the admin reference-data screens expose a Load more control. Added tests cover
all three lists, malformed cursors across list families, multiple empty-thread
pages, and concurrent magic-link consumption. Final verification passed with
240 backend tests, 26 frontend component tests, clean TypeScript, 11 E2E tests,
and 10 evidence recording tests. `git diff --check` also reported no whitespace
errors. Tests were run through WSL Docker; use `wsl.exe` from Windows when the
Docker CLI is not directly available in PowerShell.
