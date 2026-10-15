# Handoff

**Date:** 14 October 2026
**Deadline:** demo 15 October (tomorrow)
**Written for:** whoever picks this up next — human or AI agent
**Docs status:** specs reconciled with code 2 Oct. `c4c7a00`.
**Branch:** `web-deploy` — free-tier Render deployment workstream, pushed to
origin. **§18 is where to pick up.**

Read [`AGENTS.md`](AGENTS.md) first. This file covers only **what state the
code is actually in**, which is not derivable from the specs.

> **⚠ HOW TO RUN THIS PROJECT — read this before any command.**
>
> Everything runs in Docker. Docker, Node and Python live **inside the
> containers or inside WSL** — they are not on the Windows host and must not
> be installed, uninstalled, or "repaired" there. Previous agents have caused
> serious damage by not noticing Docker runs through the WSL backend and
> trying to "fix" a non-existent host environment. If `docker info` fails in
> PowerShell, that is expected — use `./run.bat`, which detects WSL
> automatically. Never run `pytest`, `npx`, `node` or `python` on the Windows
> host; all tests run via `docker compose exec`. After editing frontend
> source, `docker compose restart frontend` (Vite HMR is unreliable here).
> Full instructions: [`AGENTS.md`](AGENTS.md) §6 and
> [`docs/deploy.md`](docs/deploy.md).

---

## 1. Test status

| Suite | Command | Result |
|---|---|---|
| Backend unit + integration | `docker compose exec -T backend pytest tests` | **240 passed** (389s) |
| Frontend components | `docker compose exec -T frontend npx vitest run` | **39 passed** (14 Oct, temporary Windows dependency install; see §17) |
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

**Last verified run: `ben-test` branch, 14 Oct ~14:40** — all four suites
green (298 backend, 39 component, clean tsc, 19 E2E), run through WSL.

**The `web-deploy` branch has NOT been tested.** The deployment workstream
(§18) is committed and pushed but no suite has run against it. Note on
Docker: it has never run natively on the Windows host — it always runs
through the WSL layer, via `./run.bat` (which auto-detects `wsl docker`) or
`wsl docker` directly. "Docker is unavailable on Windows" is never a valid
excuse to change the host environment; it means use `run.bat`.

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

# 2. create British English narration WAVs and synchronized SRT subtitles
powershell -ExecutionPolicy Bypass -File scripts/create-video-narration.ps1

# 3. composite, subtitle, narrate + convert to mp4 (writes videos/*.mp4)
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
  hid the app's own nav on every page, and the nav is part of the evidence. The
  final MP4 also burns in synchronized subtitles for the narrator.
- **Narration is generated locally** by `scripts/create-video-narration.ps1`
  using the installed Microsoft Hazel English (Great Britain) SAPI voice. Run it
  after Playwright: the recorder clears its output directory at the start of a
  fresh run. It writes one WAV and SRT per final clip under
  `frontend/videos-raw/narration/`.
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
| Run all four suites against the §18 changes | §19.5 | **High** — last verified run was `ben-test` ~14:40; web-deploy untested |
| Commit the documentation-phase edits | §19 | **High** — docs/deploy.md, ADR 0013, `.env.example`, helpers.ts, playwright.config.ts, AGENTS.md §6 all uncommitted |
| ~~Write `docs/deploy.md`~~ | §19.1 | ✅ Written 14 Oct |
| ~~Write ADR 0013 for `DEMO_EXPOSE_MAGIC_LINKS`~~ | §19.2 | ✅ Written 14 Oct |
| ~~Add `DEMO_EXPOSE_MAGIC_LINKS` to `.env.example`~~ | §19.3 | ✅ Done 14 Oct |
| ~~Decide fate of `zz-deploy-check.spec.ts`~~ | §19.4 | ✅ Race fixed in helpers.ts; spec kept as manual deploy check, excluded from default suite |
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
docker compose exec -T frontend npx vitest run            # 39 passed
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
240 backend tests, 39 frontend component tests, clean TypeScript, 11 E2E tests,
and 10 evidence recording tests. `git diff --check` also reported no whitespace
errors. Tests were run through WSL Docker; use `wsl.exe` from Windows when the
Docker CLI is not directly available in PowerShell.

---

## 12. Third-party code review — 8 October 2026

A read-only review of every backend and frontend source file. **No product code
was changed.** Findings are numbered **B1–B20**; §13 maps each to the test that
exposes it.

Docker was not available to the reviewing machine, so none of this is
empirically confirmed. It is code-level reasoning plus two checks against
upstream source (Starlette 0.41.3 `responses.py` and FastAPI 0.115.6
`routing.py`). The tests in §13 are the confirmation.

### 12.1 One suspected bug retracted

§3 fixed a logout that answered `JSONResponse(None, 204)`, which serialises a
literal `null` onto a status code defined to have no body. The obvious next
question is whether the same bug survives anywhere else. It does not.

FastAPI 0.115.6, `get_request_handler`:

```python
response = actual_response_class(content, **response_args)
if not is_body_allowed_for_status_code(response.status_code):
    response.body = b""
```

So a route that *returns* `None` with `status_code=204` is safe.
`notifications.mark_all_read`, `admin.delete_skill` and
`admin.delete_interest` are all correct as written. The logout bug was real only
because logout **constructed** `JSONResponse(None, 204)` itself and returned a
`Response` object, which bypasses the line above entirely.

**Do not "fix" those three endpoints.** The inconsistency with the four
endpoints that do return a bare `Response` is cosmetic only.

### 12.2 Findings

| ID | Finding | Where | Severity |
|---|---|---|---|
| B1 | `/matches` cursor pagination **always** returns an empty page 2+. The encoder stores the **positive** score (`encode_cursor(last.score, …)`); the comparator uses `sort_key`, which **negates** it. `sort_key(...) > (after_score, after_id)` can never be true for a non-negative score, so every candidate is filtered out. | `match_service.py:209` | P1 |
| B2 | `unread_messages` is hardcoded to `0`. `specs/05_connection_requests.md:237` documents a real count. It is in no *As built* section and no deviations table, and no frontend code reads it — so nothing catches it. | `connections.py:138` | P1 |
| B3 | Rules-of-hooks violation. `useSocketListener`, `useSocket`, `useEffect` and `useLayoutEffect` all sit **below** `if (loading) return <Spinner/>`, so the first render of `ThreadPage` runs fewer hooks than the second. | `MessagingPage.tsx:150,220` | P1 |
| B4 | The toast dedupe is inverted. Within 5s of the same actor it deletes the **oldest, unrelated** toast (`prev.slice(0, prev.length - 1)`) and discards the **new** notification — the exact opposite of what its comment claims. | `Notifications.tsx:151` | P1 |
| B5 | Magic-link base URL is hardcoded `f"http://localhost:8000"`; no `APP_URL` setting exists at all. The link redirects to `/` on the **API** port, so the user lands on a 404. `tests-videos/helpers.ts:159` already documents a workaround. | `auth.py:107` | P1 |
| B6 | No `Origin` check on the WebSocket handshake. `SameSite=Lax` does block CSWSH today, but every source consulted says not to rely on it alone. | `messaging.py:152` | P2 |
| B7 | Revoking a session does not close live sockets. `load_session` runs once at handshake, so logout and deactivation leave the socket open and still delivering. | `messaging.py:156` | P2 |
| B8 | No rate limiting on `/auth/login` or `/auth/magic-link`. The latter is an unauthenticated mail-sending endpoint. | `auth.py:68,99` | P2 |
| B9 | Photo upload does `await file.read()` — the entire body — before the 2 MB cap, with no `Content-Length` pre-check. | `users.py:90` | P2 |
| B10 | `dev.py` claims traversal protection it does not perform: `_VIDEOS_DIR / filename` plus `.exists()` is not containment, and `\` passes Starlette's `[^/]+`. It also returns `{"error": "not_found"}`, breaking the `specs/00_conventions.md` §2 envelope. | `dev.py:29,31` | P2 |
| B11 | `update_skill` / `update_interest` / `update_course` never check name uniqueness; only the `create_*` pair does. All three columns are `unique=True`, so renaming onto an existing name is an unhandled `IntegrityError` → **500**. | `admin.py:307,356,428` | P3 |
| B12 | `match_out` re-derives shared skills **by name**, because `MatchItem` drops the `shared_skill_ids` that `MatchResult` already computed. Combined with B11 this puts the wrong skills on match cards. | `serializers.py:107` | P3 |
| B13 | `delete_interest` raises `code="skill_in_use"` — copy-pasted from `delete_skill`. `errors.InUseConflict` is defined and never used by either. | `admin.py:449` | P4 |
| B14 | `create_idea` / `update_idea` never validate that `course_id` exists. It is a foreign key, so a well-formed unknown UUID is an unhandled `IntegrityError` → **500**, not 422. Breaks AGENTS.md §5 rule 5. | `ideas.py:105,135` | P3 |
| B15 | `has_more = len(items) == limit`. Every other list endpoint uses `len(rows) > limit` before slicing. This reports "there is more" when the page is exactly full and there is none. | `matches.py:54` | P3 |
| B16 | `ThreadPage` cannot page history: `messages.history()` takes no cursor and there is no "load older". Threads over 50 messages silently truncate, and because `loadHistory` merges by id (§3b) they never arrive. | `client.ts:201` | P2 |
| B17 | One idea detail request runs a 200-row category sweep purely to find interest counts. | `ideas.py:113` | P4 |
| B18 | N+1: `list_connections` runs 2 queries per row, `rank_for_viewer` runs 1 per row. §11 de-N+1'd `/threads` but not these. | `connections.py:85`, `match_service.py:215` | P4 |
| B19 | `WebSocketProvider` wraps the public landing page. A signed-out visitor opens a socket, receives `close(4001)`, and `onclose` retries **indefinitely** at a ≤30s interval, forever. | `App.tsx:155` | P4 |
| B20 | Dead code: `users.eager` (also a no-op — `setattr(user, attr, getattr(user, attr, None))`), `profiles.load_profiles` (ignores its own name and loads every profile), `pagination.next_cursor_or_none`, `messaging.can_access`, `messaging.messages_after`, `schemas.ResolveReportRequest`, `connections.accepted_request_for` (imported and unused in `matches.py`), `match_service`'s shadowed `decode_cursor` import, `ConnectionRequest` imported twice in `admin.py`, and `from sqlalchemy import select` at the **bottom** of `users.py`. | various | P4 |

### 12.3 Why B1 survived a green suite

Every other list family has a cursor test: admin, ideas, threads, connections,
plus a malformed-cursor sweep that *includes* `/matches`. That sweep passes
because a garbage cursor fails to **decode**, raising before the sign bug is
ever reached. No test ever sends `/matches` a **valid** cursor, and
`MatchesPage` never sends one either.

The one list family with the bug is the one family nobody paged. That is worth
more than any individual fix, and it is why §13's pagination contract test is
generic rather than a one-off.

### 12.4 Decisions needed before fixing

| Question | Default taken here |
|---|---|
| B2: implement the real count, or amend `specs/05`? | Implement. The field is already documented at line 237, and AGENTS.md §4 says a wrong spec gets fixed before the code. |
| B1: add a "Load more" to `MatchesPage`, or fix the cursor only? | Fix the cursor **and** add the control, with a line added to `specs/04` §8 first. Without the control the fix is invisible and people 21+ stay unreachable. |
| B6: add the Origin check, or just pin current behaviour with a test? | Add the check. It is ten lines and it is what the OWASP guidance says to do. Flagged because it is defence-in-depth, not a live hole. |

---

## 13. The suite that exposes §12

Added with the review, **before any fix**. Every one of these tests is expected
to **fail** against the code as it stands today; that failure list is the
evidence the tests work. A test that passes before its fix is not exposing
anything and must be rewritten.

### 13.1 Three rules that make the suite hard to fake

1. **No network mocking, and it is enforced.** `playwright.config.ts` already
   states the policy in a comment. `scripts/check-no-mocking.mjs` now fails the
   build if anything under `frontend/tests/` or `frontend/tests-videos/`
   reaches for `page.route`, `route.fulfill`, `route.continue` or
   `context.setOffline`. A comment is not a control.
2. **Every assertion has an independent witness.** No test asserts only on what
   the UI displayed. Each also checks one of: a fresh authenticated
   `page.request` call, a direct Postgres read via `pg`, the real `WebSocket`
   object's `readyState`, the real Mailpit inbox, or the server's stdout. A
   hardcoded response produces the right pixels and the wrong database.
3. **Expected values are derived, never literal.** Nothing asserts
   `unread_messages == 4`. It asserts equality with the sum of the thread list's
   own `unread_count` **and** that one more message moves both by exactly one.
   Nothing asserts a page size of six; it walks `limit=1` to exhaustion and
   compares the union against the `limit=100` answer.

### 13.2 What was added

| File | Covers |
|---|---|
| `backend/tests/integration/test_pagination_contract.py` | B1, B15. A generic walk-to-exhaustion contract over all ten list families, plus a tied-score case that forces the tiebreaker. |
| `backend/tests/integration/test_handoff_regressions.py` | B2, B9, B10, B11, B12, B13, B14, B17, B18. Conservation laws, database assertions, and a query-count bound. |
| `backend/tests/integration/test_websocket.py` (extended) | B6, B7. A raw handshake with a forged `Origin`, and revocation closing a live socket. |
| `frontend/tests/db.ts` (new) | Direct Postgres reads for the Playwright suite. |
| `frontend/tests/regression.spec.ts` (new) | B2, B3, B4, B5, B16, B19, plus a photo-upload round trip. |
| `frontend/src/pages/ThreadPage.test.tsx` (new) | B3, B16. |
| `frontend/src/components/Notifications.test.tsx` (new) | B4. |
| `scripts/check-no-mocking.mjs` (new) | Rule 1 of §13.1. |

### 13.3 Verification gate

```bash
docker compose up -d --build

# 1. New tests against UNFIXED code. Record the failure list — this is the
#    evidence that each test actually exposes its bug.
docker compose exec -T backend  pytest tests -q
docker compose exec -T frontend npx vitest run
docker compose exec -T frontend npx playwright test

# 2. Fix, then all four suites green.
docker compose exec -T backend  pytest tests -q
docker compose exec -T frontend npx vitest run
docker compose exec -T frontend npx playwright test
docker compose exec -T frontend npx tsc --noEmit

# 3. A green suite is not a quiet server (§3).
docker compose logs backend | grep -icE "traceback|staledata|unhandled"

# 4. Guards.
node scripts/check-no-mocking.mjs
```

### 13.4 Status

The B1–B20 findings were addressed in the working tree on 11 October 2026.
The tests listed in §13.2 were run against the fixed code. The first-run
failure was in the ideas **recording scenario**: its locator clicked a heading
but only asserted that some level-one heading existed, so it never proved that
the detail page had opened. The scenario now clicks the idea link, checks the
detail URL and title, then checks the interest action. The corrected scenario
passed, followed by a clean full recording run.

## 14. Review fixes and verification — 11 October 2026

All twenty findings from §12 were fixed and covered by the regression suite:

- **B1–B5:** match cursor encoding; unread message total; stable hook order;
  toast deduplication; configurable browser URL for magic links.
- **B6–B10:** WebSocket Origin validation and session revocation; login and
  magic-link throttles; bounded photo upload; contained dev-video paths and
  standard error envelopes.
- **B11–B15:** uniqueness checks for reference renames; shared-skill IDs kept
  through serialization; correct interest-in-use error; idea course validation;
  correct `has_more` calculation.
- **B16–B20:** load older thread history; avoid the idea detail category sweep;
  batch connection/match lookups; do not open WebSockets on the public landing
  page; remove the reviewed dead code.

The regression coverage includes direct database and live-server checks. The
video idea scenario was also strengthened to assert that clicking the idea
opens its detail page before expressing interest.

| Verification | Result |
|---|---|
| Backend `pytest tests -q` | **298 passed** (suite exited 0) |
| Frontend `npx vitest run` | **39 passed** |
| E2E `npx playwright test` | **19 passed** |
| `npx tsc --noEmit` | clean |
| `node scripts/check-no-mocking.mjs` | passed |
| Backend logs scan (`Traceback`, `Unhandled`, `ERROR`, `RuntimeError`, `StaleDataError`) | no matches |
| Evidence recording suite | **10 passed** |
| Video build | **9 MP4 examples regenerated** in `videos/` |
| `git diff --check` | clean |

The React Router future-flag and existing React `act(...)` warnings remain
non-failing component-test output. This verification ran through WSL Docker
because the Windows shell did not have `docker` on `PATH`.

## 15. Database healthcheck and terminal visual refresh — 11 October 2026

Postgres logged `FATAL: database "bootcamp" does not exist` because the
Compose healthcheck passed `-U bootcamp` without `-d`; libpq then used the
username as the database name. The healthcheck now probes the configured
`POSTGRES_DB` (default `bootcamp_connect`). The database container was
recreated and its startup log showed only that the database system was ready.

The frontend received a dark green terminal visual system, command/status
chrome, animated responsive navigation, subtle entry and hover motion, and
reduced-motion handling. The landing page now uses a terminal-style match
preview. Route labels and product copy remain intact.

## 16. Narrated evidence videos — 11 October 2026

Re-recorded all ten evidence scenarios against the refreshed UI (**10 passed**)
and rebuilt the nine final MP4s. The videos retain their action-specific DOM
captions, now styled to match the terminal UI, and include a locally generated
British English narrator with synchronized burned-in subtitles. Narration
scripts live in `scripts/create-video-narration.ps1`; rerun it after Playwright
recordings and before `scripts/build-videos.sh`. The two-window connection and
messaging videos each have one shared narration track.

## 17. Security hardening review — 14 October 2026

Work started from `ben-branch` at `da053b3` and was moved to a separate
`ben-test` branch before commit. No commit was made on `ben-branch`.

### Source changes in this branch

- Auth throttling was extracted from `routers/auth.py` to
  `services/rate_limit.py`. It uses an in-process sliding window, hashes
  identities before storing keys, prunes stale keys, and caps tracked keys at
  10,000.
- Limits are per normalized email for registration (5/hour), password login
  (5/15 minutes), and magic-link requests (3/15 minutes). Verification is
  limited to 10 attempts per submitted token per 15 minutes. Rejections return
  HTTP 429 with a `Retry-After` header.
- `SecurityMiddleware` now sets a restrictive CSP on API responses. Vite
  development responses set a frontend CSP allowing inline styles for the dev
  toolchain; Vite preview uses a stricter policy that disallows inline styles.
  Both include frame, object, base, form, image, font, and connection
  directives; preview must still be exercised in a real browser to detect
  policy violations.
- `SESSION_SECRET` was removed from settings, Compose, `.env.example`, and
  documentation because it had no runtime consumer. Current sessions use
  random opaque tokens stored as hashes; this change does not add signing or
  encryption.
- Added unit coverage for limiter windows, scopes, and storage cap; added
  integration assertions for rate-limit responses and the API CSP.
- Corrected stale component-test counts in project documentation to 39.
- Modularity review found `pages/IdeasPage.tsx` holds listing, form, and detail
  pages, and `pages/ProfilePages.tsx` holds profile display and edit flows.
  They were noted as possible future splits but were not refactored here.

### Limitations and unresolved findings

- The limiter is process-local: limits reset on application restart and are
  not shared between instances. It has no source-IP/network bucket, so it
  should not be treated as production-grade anti-automation or distributed
  rate limiting. The verification bucket is keyed by submitted token; an
  attacker can vary candidate tokens to create separate buckets (the global
  tracked-key cap bounds memory, not guesses). Before scaling or relying on
  these controls in production, move counters to shared storage such as Redis,
  add a trusted-proxy-aware IP/network limit, and verify thresholds against
  legitimate shared-network use.
- The frontend dependency audit remains unresolved. The restored lockfile
  contains React Router 6.30.6, `@vitest/mocker` 3.2.7, Vitest 3.2.7, and
  Tinypool 1.1.1. `npm audit` reported 5 findings (3 moderate, 2 critical),
  including advisories affecting React Router redirects, Vitest redirect
  mocks, and Tinypool worker options. Dependency upgrades were attempted but
  not retained; `package.json` and `package-lock.json` are unchanged from the
  branch base.

### Validation and environment incidents

- On Windows, the first `npm test`/build attempts could not start because the
  Rollup Windows native optional package was absent. The tests (39 passed) and
  production build later succeeded after a temporary local dependency
  installation, but **were not rerun after `npm ci` restored the original
  lockfile**. Thus they do not verify the final installed dependency tree or
  final CSP policy.
- The user explicitly requested that Windows npm/Python environments not be
  altered. Before that instruction, npm was run in `frontend` (including a
  temporary no-save platform-package install and upgrade attempts). The
  dependency manifests were restored and, after the user authorized it,
  `npm ci` completed from the original lockfile. The final tracked changes
  contain no package manifest or lockfile changes.
- A Windows Python package installation was attempted before the user
  instruction. The package-install tool reported success, but later checks
  found no `pytest` in `c:/python312/python.exe`. A direct pip attempt failed
  with `WinError 2` while replacing `idna.exe`. Whether that failed operation
  changed any other global Python packages was not verified.
- Backend tests were not run. Docker was unavailable in the PowerShell
  environment. Attempts to start the project via `run.bat` from PowerShell
  and `cmd.exe` returned command-parsing errors and did not start services;
  `run.bat` itself was not modified. WSL Docker responsiveness was not
  confirmed.
- Editor diagnostics reported no problems in changed source/test files and
  `git diff --check` passed. These checks do not replace backend integration
  tests or browser validation.

---

## 18. Web deployment workstream — 14 October 2026

Goal: a free-tier Render deployment of the full stack — one Docker image,
one origin, no mail provider. Committed as `3c47d4f` and pushed to origin.
**Nothing has been run against it.**

### What is in the tree

| Piece | File(s) |
|---|---|
| FastAPI serves the built SPA from `static/` — single-origin production | `backend/app/main.py` |
| Traversal-safe static resolution, SPA fallback, cache + security headers | `main.py` |
| Unit tests for that resolution, incl. `../secret/id_rsa` | `backend/tests/unit/test_static_serving.py` |
| `DEMO_EXPOSE_MAGIC_LINKS` — magic link in the API response when there is no mail provider | `config.py`, `routers/auth.py`, `api/client.ts`, `AuthPages.tsx`, 2 integration tests |
| Multi-stage `Dockerfile` (node:22-slim → python:3.12-slim); alembic + seed run in `CMD` | `Dockerfile` |
| Render Blueprint — free tier, Neon DB, single worker, `DEMO_EXPOSE_MAGIC_LINKS=1` | `render.yaml` |
| Keepalive workflow — pings `/api/v1/health` every 14 min | `.github/workflows/keepalive.yml` |
| Build-context exclusions | `.dockerignore` |
| Deploy verification spec (excluded from default suite, run manually post-deploy) | `frontend/tests/zz-deploy-check.spec.ts` |
| Deployment guide | `docs/deploy.md` |
| ADR for the magic-link tradeoff | `decisions/0013-demo-expose-magic-links.md` |

### The design

- **One origin.** The image contains the built SPA and FastAPI serves it —
  no CORS, no cookie domain, no Vite proxy in production. The catch-all
  `api_route` is registered *last* so every router wins; unknown `/api/*`
  paths still get a JSON 404, not the SPA shell.
- **Traversal safety is the entire point of `resolve_static_file`.** The
  path arrives from the URL. `candidate.is_relative_to(root.resolve())`
  is the whole security model; four unit tests pin it. Do not "simplify"
  that function.
- **Migrations + seed run in the container `CMD`**, not a Render
  pre-deploy hook: one instance means no deploy race, and the app never
  serves traffic against an unmigrated schema.
- **`demo_expose_magic_links` is opt-in and documented as an enumeration
  tradeoff.** Off by default — the always-202 contract keeps hiding which
  emails have accounts. On, only real accounts get a `demo_link` in the
  response; the sign-in page renders it inline. This is the one place the
  app deliberately gives up an API guarantee, and it is commented as such at
  all three layers (config, route, page). The two integration tests pin
  both directions.
- **Keepalive exists because the Render free tier sleeps after 15 min
  idle.** `/robots.txt` is answered by Render itself while asleep, so the
  workflow pings `/api/v1/health` — a path that actually reaches the app.

---

## 19. Gaps in the deployment workstream — read before doing anything

Updated 14 Oct after the documentation phase. Items 1–3 are now closed.

1. ~~**`docs/deploy.md` does not exist.**~~ ✅ Written. Covers both stacks
   (dev compose vs production image), `./run.bat`, the four test suites,
   Neon + Render setup, the `RENDER_URL` repo variable, the post-deploy
   smoke test, and a troubleshooting table.
2. ~~**ADR 0013 does not exist.**~~ ✅ Written as
   `decisions/0013-demo-expose-magic-links.md`. Records the enumeration
   tradeoff and the four rejected alternatives.
3. ~~**`.env.example` does not list `DEMO_EXPOSE_MAGIC_LINKS`.**~~ ✅ Added,
   default `false`, cross-referenced to the ADR.
4. ~~**`zz-deploy-check.spec.ts` is marked "Not for commit".**~~ ✅ Resolved.
   The race it documented (`completeProfile` asserting `/matching is
   unlocked/i`, which the form's live preview also matches) is real and is
   now fixed in the helper itself: `frontend/tests/helpers.ts`
   `completeProfile()` waits for the `PATCH /users/me` response and asserts
   `200` before checking the confirmation text. The spec is kept as the
   manual deploy smoke test, excluded from the default suite via
   `testIgnore` in `playwright.config.ts`, with its header updated.
5. **Nothing has been run against the §18 changes.** The last verified run
   was `ben-test` at ~14:40 on 14 Oct — all green, but that predates the
   deployment workstream. **Do not deploy until the §13.3 verification gate
   passes** (all four suites + logs scan + `check-no-mocking.mjs`). The
   `helpers.ts` change in item 4 is also unverified — it is strictly additive
   (waits for a response that must succeed anyway) but the next E2E run is
   the first time it executes. Reminder: Docker always runs through WSL on
   this machine — use `./run.bat` or `wsl docker` directly.
6. ~~**Nothing is committed.**~~ ✅ Committed as `3c47d4f` and pushed to
   `origin/web-deploy`. The documentation-phase edits (docs/deploy.md, ADR
   0013, `.env.example`, `helpers.ts`, `playwright.config.ts`,
   `zz-deploy-check.spec.ts`, this handoff, `AGENTS.md` §6) are uncommitted.

---

## 20. Cloudflare tunnel reachability — 15 October 2026

**Branch:** `cloudflare-deploy` (not committed). **§20.6 is what is left.**

### 20.1 What was reported, and what it actually was

> "`./run.bat tunnel` creates a link that works through the machine hosting
> the site but gives error 1033 on other devices."

Cloudflare **1033** means the edge knows the hostname but no `cloudflared`
instance is registered for it. The URL resolved; nothing was behind it.

**Root cause, confirmed against the live tunnel.** The tunnel container's log
contained **two** hostnames:

| | Hostname | Health check |
|---|---|---|
| first in log | `elizabeth-hanging-him-camping.trycloudflare.com` | **HTTP 000 — dead** |
| last in log | `responsibilities-clocks-friendly-thereof.trycloudflare.com` | **HTTP 200 — live** |

`docker compose logs` prints the container's **entire history**, and
PowerShell's `-match` returns the **first** match. A restarted `cloudflared` is
handed a **new** random hostname while the dead one stays in the log — so
`run.bat` printed the corpse. It worked "on the host" only because that URL had
been live earlier in the session and was still open in a tab.

**The app was never at fault.** Verified before changing anything:
`main.py:101` sets `allow_origin_regex` for `*.trycloudflare.com`,
`messaging.py:163` allows the same on the WebSocket handshake, and
`vite.config.ts` sets `allowedHosts: true` with `ws: true` on the `/api`
proxy. All three were already correct.

### 20.2 Changes

| File | Change |
|---|---|
| `scripts/tunnel-status.ps1` | **New.** Owns URL extraction and the health check. Takes the **last** match. Polls `GET <url>/api/v1/health` for up to 60 s and only prints the green banner on a real `200`; otherwise prints a yellow "NOT serving traffic yet" with the commands to diagnose it |
| `run.bat` | `tunnel` and `url` now call that script. Detected `DOCKER_CMD` is split into `-DockerExe` / `-DockerPrefix` so the script can invoke it without re-parsing a command string |
| `docker-compose.yml` | Removed `restart: unless-stopped` from `tunnel`, with a comment saying why. A silent restart comes back on a **different** hostname and orphans every URL already handed out without a word |
| `docs/cloudflare.md` | New §2a "If you see Cloudflare error 1033" (cause → symptom → fix table) and §2b "Verifying the tunnel from outside". §3 and §5 corrected |

**Why a `.ps1` and not a `node` script:** AGENTS.md §6 — Node is not on the
Windows host. `run.bat` would have had to go through a container to run it.

**Why the Quick Tunnel URL still changes** and that is not a regression: a
Quick Tunnel hostname is random and lives only as long as the `cloudflared`
process. Fixing the *reporting* is all that is possible without an account. A
named tunnel (docs §5) needs a Cloudflare account and a domain; neither exists
here, so that path was deliberately **not** built — untestable dead config.

### 20.3 Two further bugs found while doing it

**a. `is_allowed_origin` matched the bare label, so `https://*.example.test`
also accepted `https://notexample.test`.** The old second branch stripped
`https://*.` and compared the *bare* suffix `example.com`, which
`notexample.com` ends with. Proven directly:

```
old accepts https://notexample.test via https://*.example.test -> True
new accepts https://notexample.test via https://*.example.test -> False
```

Both wildcard forms now go through one `urlsplit` so the leading dot survives
the comparison. **Note the apex is still rejected** — `https://*.example.test`
means subdomains, which is how it always behaved.

**b. The E2E suite could not launch a browser at all.** `frontend/Dockerfile`
ran `npx playwright install chromium`, which installs the browser but **not**
the shared libraries it links against. Every Playwright test — including the
pre-existing `demo.spec.ts` — died with `libglib-2.0.so.0: cannot open shared
object file`. Changed to `npx playwright install --with-deps chromium`. This is
the same gap §17 flagged as a "temporary Windows dependency install"; it was
never actually fixed in the Dockerfile, so **any** fresh `docker compose up
--build` reproduced it. Confirmed pre-existing, not caused by this work.

### 20.4 Tests added

| File | Covers |
|---|---|
| `backend/tests/unit/test_tunnel_origins.py` (new) | 24 cases. Quick Tunnel origins allowed; lookalikes (`…trycloudflare.com.attacker.test`, `…localhost:5173.attacker.test`) rejected; the wildcard regression from 20.3a; malformed origins rejected rather than raising |
| `frontend/tests/tunnel.spec.ts` (new) | **The reproduction.** `test.skip` unless `TUNNEL_URL` is set. Runs inside the Playwright container — a **different network namespace from the host** — so `localhost:5173` and the public hostname are genuinely different paths. Checks health, landing page + assets, sign-in setting a cookie on the tunnel host, and a real WebSocket `readyState` |

Same two rules as the rest of the suite: no network mocking, and every
assertion has a witness that is not the rendered page.

**Both verified to have teeth:**

```
# live URL
4 passed (15.4s)

# dead URL — every one fails
✘ serves the health endpoint          Error: getaddrinfo ENOTFOUND …
✘ serves the landing page             Error: page.goto: ERR_NAME_NOT_RESOLVED
✘ signs in and loads matches
✘ accepts the WebSocket handshake
4 failed
```

### 20.5 Verification status — what is green and what is NOT

| Check | Result |
|---|---|
| `docker compose exec -T backend pytest tests/unit -q` | **98 passed** |
| `npx tsc --noEmit` | clean |
| `tunnel.spec.ts` against the live URL | **4 passed** |
| `tunnel.spec.ts` against the dead URL | 4 failed (correct) |
| `docker compose exec -T backend pytest tests -q` | ⚠️ **NOT COMPLETED** — see 20.6 |
| `npx vitest run` | ⚠️ **NOT RUN** |
| Full `npx playwright test` | ⚠️ **NOT RUN** |
| `node scripts/check-no-mocking.mjs` | ⚠️ **NOT RUN** |
| `scripts/tunnel-status.ps1` syntax | ⚠️ **NEVER EXECUTED — no PowerShell on this box.** Must be run on Windows before the demo |

### 20.6 Bugs and blockers still open

1. **`scripts/tunnel-status.ps1` has never been executed.** No `pwsh` on the
   WSL side and the script targets Windows PowerShell 5.1. `run.bat url` is the
   thing a marker will type — **run it on Windows first.**
2. **The full backend suite did not finish.** It aborted on an environment
   fault, not a code fault: `tests/conftest.py` builds the schema against
   `TEST_DATABASE_URL` = `bootcamp_connect_test`, and that database **did not
   exist** (see 20.7). It has now been created; the suite needs re-running.
3. **The frontend image was rebuilt** for 20.3b, so the 39 component tests and
   19 E2E tests are running against an image that has never been exercised.
   **The demo is today.** Run the full §13.3 gate before showing anyone.
4. `git status` shows **~150 modified files**. This is **CRLF↔LF line-ending
   noise**, not content — insert and delete counts are identical on every
   file (`seed.py` alone: 409/409). Do not "fix" or review that diff, and do
   not let it into a commit as-is.
5. **The tunnel hostname changes whenever the container is recreated.** There
   is no way around this without a Cloudflare account. Re-run `run.bat tunnel`
   and **re-share the URL** after any restart.
6. `APP_URL` still defaults to `http://localhost:5173`, so an *emailed* magic
   link points an outsider at their own localhost. The inline
   `DEMO_EXPOSE_MAGIC_LINKS=true` path covers the demo and this was left alone.

### 20.7 Environment notes worth keeping

- **The test database is not created by anything in the repo.** It has to exist
  before `pytest tests/integration` will run. On a fresh volume:

  ```bash
  docker compose exec -T db psql -U bootcamp -d postgres -c "CREATE DATABASE bootcamp_connect_test;"
  ```

- **`psql -U bootcamp` alone fails** with `FATAL: database "bootcamp" does not
  exist` — libpq uses the username as the database name. Always pass `-d`.
  This is the same trap as the healthcheck fix in §15.
- `docker compose logs tunnel | grep -oE 'https://[a-zA-Z0-9-]+\.trycloudflare\.com'`
  — if that prints **more than one**, the container has restarted and the last
  one is the live URL. That is the diagnostic for 1033.

### 20.8 There are TWO copies of this project — read this first

Discovered while re-running the suite. It changes what "fixed" means.

| | `tech-native-connect/` (this repo) | `../connect-app/` |
|---|---|---|
| Git repo | yes | **yes, separate** — branch `cloudflare-deploy`, HEAD `b87a219` *"feat: add Cloudflare Tunnel support"* |
| Compose project name | `tech-native-connect` | `connect-app` |
| Containers | **none** — all removed partway through this session | `connect-app-tunnel-1` **up**, rotated through **4** hostnames |
| The 1033 bug | **fixed** in this work | **still present** — `run.bat:47` and `:51` both use `$matches[0]` (first match), `docker-compose.yml:96` still has `restart: unless-stopped` |
| `scripts/tunnel-status.ps1` | added | **absent** |

The tunnel that produced the 4 rotated hostnames — and almost certainly the
one that was 1033-ing for the marker — belongs to **`connect-app`**, not to
this repo. The fix has **not** been applied there.

> **✅ DECIDED 15 Oct: `connect-app` is a stale fork. Do not touch it.**
> No fix is owed to that copy. If a marker reports 1033 again, check which
> directory the stack was started from **before** changing anything here —
> `docker compose ls` names the project, and `connect-app` is still running
> with the old `run.bat`. This repo is the one AGENTS.md documents.

**Neither copy's `run.bat` has ever been executed against a PowerShell that
could run it** (§20.6 item 1). Both are unverified.

### 20.9 Corrected blocker status

- §20.6 item 2 is superseded. The correct explanation, confirmed from
  `docker events` after it happened a second time:

  > **This environment kills the whole stack under load.** All five
  > `tech-native-connect-*` containers `die` within ~15 s of each other
  > (`tunnel-1 exit=137` — SIGKILL; the rest exit 0, i.e. a graceful daemon
  > shutdown), and the project then disappears from both `docker ps` and
  > `docker compose ls`. A sibling project's containers survive. Total RAM is
  > **3.7 GB**, and the full backend suite spawns a live uvicorn per test
  > module on top of Postgres, Vite and mailpit.

  So: **the full backend suite cannot be completed in this box**, and a
  container vanishing mid-run is the environment, not the code. Do not go
  hunting for a cause in the application. If it must be run, stop the other
  Compose projects first:

  ```bash
  docker compose -f ../connect-app/docker-compose.yml down
  docker compose exec -T db psql -U bootcamp -d postgres -c "CREATE DATABASE bootcamp_connect_test;"  # already done
  docker compose exec -T backend pytest tests -q
  ```

  **An earlier note in this section called the first occurrence a "transient
  Docker daemon hiccup". That was wrong** — it was the same event, and it
  recurred within minutes.

### 20.10 Two more bugs, found after §20.3 — both from running the thing

**c. `run.bat` printed no URL at all on the native-Windows path.** `run.bat`
passed `-DockerExe docker -DockerPrefix docker`, and `tunnel-status.ps1` ran
them as one command: `docker docker compose logs tunnel` → `unknown command` →
empty log → *"No tunnel URL found"* — **while a perfectly healthy tunnel was
running.** Fixed: the prefix defaults to empty and the argument list is built
conditionally, so it runs `docker compose …` natively and `wsl docker compose
…` through WSL. The no-URL branch now also reports the exact command it ran
and whether the log came back empty, which is what makes the next occurrence
obvious instead of mysterious.

**This is precisely the failure §20.6 item 1 warned about**: the script had
never been executed. It could only be found by running it on Windows. **Do the
same before trusting any of it again.**

**d. The integration suite could never pass inside Compose.**
`docker-compose.yml:65` sets `DEMO_EXPOSE_MAGIC_LINKS=true` on the backend, and
`backend/tests/conftest.py` inherited it. So
`test_magic_link_is_never_returned_in_the_body_by_default` — which asserts the
flag is **off** — failed on every in-container run. This arrived with the §18
deployment workstream and is the concrete instance of §19 item 5 ("nothing has
been run against the §18 changes"). Fixed by forcing the flag off in
`conftest.py` before `app.config` is imported; the demo-mode test that needs it
on monkeypatches the setting itself and still passes.

### 20.11 Verification status, final

| Check | Result |
|---|---|
| `pytest tests/unit -q` | **98 passed** |
| `pytest tests/integration/test_rules.py -k magic_link -q` | **4 passed** (20.10d) |
| `npx tsc --noEmit` | clean |
| `tunnel.spec.ts` vs live URL (`award-troubleshooting-nothing-human`) | **4 passed** |
| `tunnel.spec.ts` vs dead URL | **4 failed** (correct) |
| `pytest tests -q` (full) | ⚠️ **CANNOT COMPLETE HERE** — see §20.9, the environment kills the stack |
| `npx vitest run` | ⚠️ **NOT RUN** |
| Full `npx playwright test` | ⚠️ **NOT RUN** |
| `node scripts/check-no-mocking.mjs` | ⚠️ **NOT RUN** |
| `scripts/tunnel-status.ps1` on **Windows** | ⚠️ **NEVER EXECUTED** — 20.10c |

**Three suites and the PowerShell script are still unverified.** Given the
demo date, that is the remaining risk, not the tunnel code.

---

## 21. "DB isn't working" — it was, the sign-in-link page was lying — 15 October 2026

Report, after §20 made the site externally reachable:

> "not sure the db is working… I logged in but it didn't send any confirmation
> email, then after logging out I couldn't log back in with the credentials I
> signed up with, and the *email me a sign in link* button didn't work."

### 21.1 The database was never the problem

Proven, not assumed:

| Check | Result |
|---|---|
| `GET /api/v1/health` | `{"status":"ok","database":"ok"}` |
| Seeded demo users (`priya@example.com`, `ben@bootcamp.example.com`) | present |
| Earliest user row | `09:12` — **the volume never got wiped** |
| `POST /auth/register` via the tunnel | **201** |
| `POST /auth/login` via the tunnel | **200** |
| `POST /auth/magic-link` for an account | **202 + `demo_link`** |
| Rate limiter | 7 consecutive bad logins, all 401 — the 20/min limit is nowhere near |

### 21.2 What actually happened

All three symptoms are one bug, on one page.

`MagicLinkPage` (`frontend/src/pages/AuthPages.tsx`) had exactly two branches:
a link, or *"The link appears in Mailpit at **localhost:8025**"*. Over the
tunnel an external visitor is not on the host, so `localhost:8025` is their own
empty machine. Reproduced through the live tunnel:

```
Sign-in link  —  If that address has an account, a link is on its way.
Development shortcut: no email is actually sent. The link appears in
Mailpit at localhost:8025.
```

So: **no email** (Mailpit is unreachable off-host — by design), **link button
"broken"** (a dead end), and **couldn't log back in** (if they came in through
this flow, no password was ever set — the flow cannot create an account).

Sign-in and password auth were fine the whole time; a new test now proves the
register → sign out → sign back in round trip over the tunnel.

### 21.3 Fix

`isLocalHost` branch in `MagicPages.tsx`. The dev-only Mailpit pointer is kept
verbatim **on localhost**, so the developer experience is unchanged. Off-host
the visitor is told the demo cannot deliver email and pointed at
`create an account` — wording that renders **identically whether or not the
account exists**, which is what preserves the enumeration guarantee that
`test_magic_link_is_never_returned_in_the_body_by_default` protects. The
backend is untouched.

### 21.4 Branch `cloudflare-deploy` was broken — two files were never committed

`HEAD` (`b87a219`) contains `frontend/tests/regression.spec.ts`, which imports
`./db` — but **`frontend/tests/db.ts` is not in the commit**. The entire
Playwright suite therefore failed to collect:

```
Error: Cannot find module '/app/tests/db' imported from /app/tests/regression.spec.ts
```

`scripts/check-no-mocking.mjs` was missing too, so the guard AGENTS.md §6 tells
you to run did not exist. Both were recovered from `f5703bf` (`origin/main`),
the only commit that has them:

```bash
git checkout f5703bf -- frontend/tests/db.ts scripts/check-no-mocking.mjs
```

**This stages them.** Nothing has been committed. `db.ts` predates this work —
its absence was a packaging mistake in `b87a219`, not something §20 introduced.

### 21.5 Verification, 15 October

| Check | Result |
|---|---|
| `npx tsc --noEmit` | **clean** |
| `npx vitest run` | **39 passed** |
| `node scripts/check-no-mocking.mjs` | **passed** (after 21.4) |
| `tunnel.spec.ts`, live URL | **6 passed** |
| `pytest tests/unit -q` | **98 passed** |
| Full `npx playwright test` | **18 passed, 1 failed, 6 skipped** |
| Backend log scan (`traceback`/`unhandled`/`staledata`) | **0 matches** |

**The one failure is the documented §5.1 centrepiece flake, not a regression.**
`the demo path › request → accept → message` hit its 90 s budget at 1.5 min
under full-suite load. Run alone it **passes in 29.8 s**. Same signature as
§5.1: assertion position moves, budget exceeded, logic fine. This box has
3.7 GB of RAM and the daemon drops the stack under load (§20.9), which makes
the budget easier to miss.

### 21.6 Still open

1. **`scripts/tunnel-status.ps1` has never run on Windows** (§20.10c). `run.bat
   url` is what a marker types.
2. **Full backend suite still cannot complete here** — the environment kills
   the stack (§20.9). Last clean figure was 98 unit + 4 magic-link integration.
3. **Committed locally** as `fix(tunnel): resolve the live tunnel URL…` —
   but see 22.7: **not yet pushed.**
4. **The tunnel hostname changes every time the container is recreated**, and
   this environment recreates containers. Re-run `run.bat tunnel` and
   **re-share the URL** before the demo.

---

## 22. Consolidated state of this session — read this before touching anything

Everything in §20 and §21, in one place. **Branch `cloudflare-deploy`, HEAD
`b87a219`. Nothing is committed.**

### 22.1 Files actually changed (CRLF noise excluded)

`git status` shows ~150 modified files. **Almost all of them are CRLF↔LF
noise** — insert and delete counts are identical, so there is nothing to
review. To see only real changes:

```bash
git diff --ignore-cr-at-eol --numstat HEAD | awk '$1!=0 || $2!=0'
```

| File | ± | What |
|---|---|---|
| `backend/app/routers/messaging.py` | +7 −3 | `is_allowed_origin`: wildcard no longer matches the bare label (§20.3a) |
| `backend/tests/conftest.py` | +9 | forces `DEMO_EXPOSE_MAGIC_LINKS=false` so the integration suite can pass in Compose (§20.10d) |
| `docker-compose.yml` | +8 −1 | removed `restart: unless-stopped` from `tunnel` (§20.2) |
| `run.bat` | +10 −2 | delegates to `tunnel-status.ps1`; no more doubled `docker docker` (§20.10c) |
| `scripts/tunnel-status.ps1` | **new** | last-match URL extraction + health poll (§20.2) |
| `frontend/Dockerfile` | +6 −4 | `playwright install --with-deps` — E2E could not launch a browser (§20.3b) |
| `frontend/src/pages/AuthPages.tsx` | +21 −1 | sign-in-link page no longer dead-ends external visitors on `localhost:8025` (§21.3) |
| `frontend/tests/db.ts` | +134 | **recovered from `f5703bf`** — was missing from HEAD (§21.4) |
| `scripts/check-no-mocking.mjs` | +110 | **recovered from `f5703bf`** — was missing from HEAD (§21.4) |
| `docs/cloudflare.md` | +61 | §2a the 1033 table, §2b off-host verification |
| `frontend/tests/tunnel.spec.ts` | **new** | 6 tests, `TUNNEL_URL`-gated |
| `backend/tests/unit/test_tunnel_origins.py` | **new** | 24 cases |
| `handoff.md` | — | §20, §21, §22 |

### 22.2 Staging state

Everything in 22.1 went in as one commit on `cloudflare-deploy`,
`fix(tunnel): resolve the live tunnel URL, verify it, and fix off-host
auth`. Two notes on
how that commit was assembled, because both are traps:

- **`git checkout <commit> -- <path>` stages as a side effect**, which is how
  `db.ts` and `check-no-mocking.mjs` ended up in the index early.
- **The impeccable tool stages its own files too.** Running `impeccable` left
  all 62 of them *and* the working changes in the index, including a 19 MB
  Windows executable. Check `git diff --cached` after running it, and
  `git rm --cached -r .github/skills/impeccable` before committing.

Files committed were normalized to **LF** to match the repo. The whole working
tree had flipped to CRLF (§20.6 item 4); committing as-is would have mixed
endings in 15 files for no reason.

### 22.3 Untracked files, and a correction

> ⚠️ **This subsection originally said `.github/skills/impeccable/**` was
> "an unrelated tool drop — do not commit". That was wrong, and the user
> corrected it the same day.** It is the `impeccable` design skill, used
> deliberately. Do not treat it as noise.

`.github/skills/impeccable/**` (plus `.github/agents/impeccable-*.md` and
`.github/hooks/impeccable.json`) is the user's own tooling and is **not** part
of the tunnel work — but it is **not** junk either, so the decision to commit
or ignore it belongs to the user, not to a future agent guessing from a
`git status`.

Files that are unambiguously ours, from §20–§22:

- `scripts/tunnel-status.ps1` (new)
- `frontend/tests/tunnel.spec.ts` (new)
- `backend/tests/unit/test_tunnel_origins.py` (new)
- `PRODUCT.md` (new, 15 Oct — `impeccable init` product record)

### 22.4 Final verification figures, 15 October

| Check | Result |
|---|---|
| `npx tsc --noEmit` | **clean** |
| `npx vitest run` | **39 passed** |
| `node scripts/check-no-mocking.mjs` | **passed** |
| `tunnel.spec.ts` vs live URL | **6 passed** |
| `tunnel.spec.ts` vs a dead URL | **6 failed** (proves the tests bite) |
| `pytest tests/unit -q` | **98 passed** |
| `pytest tests/integration/test_rules.py -k magic_link` | **4 passed** |
| Full `npx playwright test` | **18 passed, 1 failed, 6 skipped** |
| `pytest tests -q` (full backend) | **cannot complete here** — §20.9 |
| Backend log scan | **0 matches** for traceback/unhandled/staledata |

The single E2E failure is the §5.1 centrepiece flake: 1.5 min against a 90 s
budget under full-suite load, **29.8 s and passing when run alone**.

### 22.5 The tunnel hostname changed 8 times today

`docker compose logs tunnel | grep -c trycloudflare.com` returns **8**. Every
container recreation mints a new hostname and kills the previous one — and this
environment recreated the stack twice under load (§20.9).

Current: `https://award-troubleshooting-nothing-human.trycloudflare.com`

**Re-run `.\run.bat tunnel` and re-share the URL immediately before the demo.**
This is the single most likely thing to make the demo fail, and it is exactly
the failure that produced the original 1033 report.

### 22.6 What a new agent should do first

1. Read §20.6 item 1 and §22.6 — **run `.\run.bat url` on Windows.** It has
   never executed. Every other claim here was machine-verified; that one was not.
2. `docker compose up -d --build` (the frontend image changed — Playwright deps).
3. Re-run the four suites plus `check-no-mocking.mjs` (§22.4).
4. If the full backend suite dies again, stop the other Compose projects first:
   `docker compose -f ../connect-app/docker-compose.yml down`. 3.7 GB of RAM is
   not enough for the suite plus the stack plus a sibling project.
5. **Push the tunnel fix commit.** It is committed locally and is 1 ahead of
   `origin/cloudflare-deploy`; see 22.7.

---

## 23. PRODUCT.md created — 15 October 2026

`/impeccable init` (the project has an `impeccable` design skill in
`.github/skills/impeccable/`). It captures **durable product truth** and writes
`PRODUCT.md` at the project root. Completion gate verified —
`impeccable context` now resolves `productPath: PRODUCT.md`, `platform: web`.

**Three facts confirmed by the user, which override repo inference:**

1. **This is coursework** — an assessed project, no real users. The
   demonstration audience is an assessor.
2. **Local Docker + Cloudflare tunnel only.** There is no hosted deployment.
   `render.yaml` and the whole `web-deploy` workstream (§18) are *not* a
   deployment commitment and must not be described as one in future docs.
   PRODUCT.md says so explicitly.
3. **Only the terminal identity is a binding brand commitment.** The product
   name is *not* confirmed final, and the prose voice is *not* binding.

Recorded as deliberately undecided rather than invented: the name, any pricing
or licensing model, and any accessibility conformance target.

**Binding absences written into the file**, so future copy and marketing work
cannot invent them: no real users, no testimonials, no usage metrics, no
customer logos, no press.

`PRODUCT.md` holds no visual world, palette, typography or component spec by
design — `init` never writes those. The committed terminal identity is recorded
as a *constraint to preserve*, not as a description of the current look.

**No DESIGN.md exists.** The project has a coherent, deliberately-built
interface (handoff §15) and no record of it; `/impeccable document` is the
command that captures one. `live` mode is also unconfigured — it needs a CSP
source edit, which requires asking first.

`buildPath` was **not** recorded in `.impeccable/config.json`: no image
generation is available in this session, and the rule is code-first when there
is none. Nothing was written, rather than inventing a default nobody chose.

### 22.7 PUSH PENDING — the tunnel fix commit is local only

Committed to `cloudflare-deploy` as `fix(tunnel): resolve the live tunnel URL,
verify it, and fix off-host auth`, but **not pushed**. The push
failed in the agent's shell:

```
fatal: could not read Username for 'https://github.com': No such device or address
```

There is no credential helper and `gh` is not installed, and installing either
is a host change — so it was not done unilaterally. The agent shell also has
no git identity, so the commit was made with `-c user.name/user.email` using
the repo's existing author (`Ben Ledger <benle@example.com>`) rather than by
writing to git config.

**To publish:**

```bash
cd "/mnt/c/Users/benle/Documents/Projects/TechNative/Group Project/tech-native-connect"
git push origin cloudflare-deploy
```

0 behind, 1 ahead at the time of writing — a fast-forward, no rebase needed.
Re-check with `git rev-list --left-right --count origin/cloudflare-deploy...HEAD`
first, in case anyone else pushed.

**Commit contents, 15 files:** `.gitignore`, `PRODUCT.md`,
`backend/app/routers/messaging.py`, `backend/tests/conftest.py`,
`backend/tests/unit/test_tunnel_origins.py`, `docker-compose.yml`,
`docs/cloudflare.md`, `frontend/Dockerfile`,
`frontend/src/pages/AuthPages.tsx`, `frontend/tests/db.ts`,
`frontend/tests/tunnel.spec.ts`, `handoff.md`, `run.bat`,
`scripts/check-no-mocking.mjs`, `scripts/tunnel-status.ps1`.

The impeccable payload (21 MB, 19 MB of it a Windows binary) is gitignored,
not committed — the user's decision.
