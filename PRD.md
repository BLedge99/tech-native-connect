# PRD — Bootcamp Connect

**Status:** agreed 1 October 2026 · **all nine required features built 2 October 2026**
**Demo:** 15 October 2026
**Owner:** Ben, Joey, James, Alys, Mick

Every feature in §4 is implemented and its Definition-of-done checklist is
ticked. Each spec has an *As built* section recording where the build differs
from what was specified; `roadmap.md` §Status summary has the test totals and
the two gaps that remain.

---

## 1. The problem

A bootcamp puts software developers and business developers in the same
building, on the same schedule, for the same course. They never actually meet.

The developers want a business partner who can sell what they build. The
business developers want someone who can build the thing they keep describing.
Neither group has a way to find the other, so introductions happen by luck, in
the corridors, and mostly between the people who happened to sit near each
other. Everything else in the bootcamp is designed. This is the part that
isn't.

## 2. Who it serves

**Primary — software developers on a bootcamp course.** They can list their
skills, say what kind of collaborator they want, and get a ranked list of
business developers on the same course who are looking for exactly what they
build.

**Primary — business developers on a bootcamp course.** They post project ideas
and approaches developers to. They are the supply side of the market the
developers want to enter.

**Secondary — the bootcamp itself.** Cohort-level network density is the thing
being demonstrated. The admin screens exist so staff can see and manage it.

**Explicitly not served:** established professionals, recruiters, investors,
anyone outside the cohort. There is no public directory and no search by
organisation. If a feature would only make sense for a non-cohort user, it is
out of scope.

## 3. What it does

A logged-in user sees a feed of suggested people on their course, ranked by
how much they overlap — shared skills, complementary roles, shared interests.
Each suggestion says *why* it was made in plain English. The user can send a
connection request. Nothing happens until the other person accepts. On
acceptance a private chat thread opens and both sides get a notification. Users
can also post project ideas, which developers can express interest in.

That is the whole loop, and it is the whole demo:

> sign up → complete profile → browse matches → send request → accept → message → see notification

## 4. Scope

### In scope — required for the demo

| # | Feature | Spec |
|---|---|---|
| 1 | Public landing page + logged-in home feed | [`specs/01_landing_page.md`](specs/01_landing_page.md) |
| 2 | Registration, login, magic link, admin seed | [`specs/02_registration_and_login.md`](specs/02_registration_and_login.md) |
| 3 | Profiles: photo, bio, skills, interests, course, role | [`specs/03_profiles.md`](specs/03_profiles.md) |
| 4 | Matching and search | [`specs/04_matching_and_search.md`](specs/04_matching_and_search.md) |
| 5 | Connection requests, mutual opt-in | [`specs/05_connection_requests.md`](specs/05_connection_requests.md) |
| 6 | Private messaging, live updates | [`specs/06_messaging.md`](specs/06_messaging.md) |
| 7 | In-app notifications | [`specs/07_notifications.md`](specs/07_notifications.md) |
| 8 | Project ideas board | [`specs/08_project_ideas.md`](specs/08_project_ideas.md) |
| 9 | Admin screens | [`specs/09_admin.md`](specs/09_admin.md) |

### Out of scope for the demo — specced, not built

These have real specs so they can be added later without touching required
code. **Do not build them during the sprint.**

| Feature | Spec |
|---|---|
| Events and meetups | [`specs/deferred_events.md`](specs/deferred_events.md) |
| Privacy settings | [`specs/deferred_privacy_settings.md`](specs/deferred_privacy_settings.md) |
| Safety tools: block, report, moderation queue | [`specs/deferred_safety_moderation.md`](specs/deferred_safety_moderation.md) |
| AI icebreaker suggestions | [`specs/deferred_ai_icebreakers.md`](specs/deferred_ai_icebreakers.md) |

Also out of scope, and **not** specced because they are not in the brief and we
should not invent them: mobile native apps, push notifications, email
notification digests, GDPR account deletion and data export, admin analytics
dashboard, video calls, payment, public profiles reachable by search engines,
importing cohort rosters from an LMS.

### Explicitly rejected interpretations

- **"Connection" does not mean dating or social.** It means a working
  relationship. This app has no swiping, no follower counts, no public posts.
- **Role is a filter, not a wall.** Any user may connect with any other user.
  Matching weights complementary roles higher but never forbids a same-role or
  cross-role pairing. The gate is cohort membership and profile completion.
- **No third-party login.** No Google, no GitHub OAuth. Email and password,
  plus a magic link. If you think this is a mistake, that is an ADR, not a
  silent change.

## 5. Non-goals

- Not a jobs board. No applications, no hiring, no company profiles.
- Not a learning platform. We assume the courses exist.
- Not a general professional network. There is no feed of posts, no comments,
  no follower graph.
- Not multi-tenant. One cohort world, one database.

## 6. Success criteria

The demo succeeds if a marker can do the following unaided, in under two
minutes, on a laptop with the stack already running:

1. Sign up as a new user and land somewhere sensible.
2. See why the app exists, without reading anything.
3. Reach a profile with real content and a photo.
4. Get a match list where the top result is obviously right, and can read the
   reason for it.
5. Send a connection request.
6. See the demo happen **from both sides** — this is why live updates matter.
   In one browser you accept; in the other the thread is already there and a
   message sent on one side appears on the other with no refresh.
7. Post a project idea.

Secondary criteria, in priority order: nothing crashes during the demo; the
admin panel can be shown; the code has tests someone can point at.

## 7. Constraints

- **Two weeks.** Fourteen days, five people, full-time. Every scope decision
  follows from this.
- **Local only.** Everything runs on a contributor's machine via Docker
  Compose. No production deploy, no migration story, no real email delivery.
  See [`decisions/0002-postgres-not-sqlite.md`](decisions/0002-postgres-not-sqlite.md)
  for the one place this was nearly decided the other way.
- **No third-party services.** No auth vendor, no AI provider, no error
  tracker, no hosted database, no cloud storage. Costs money, adds latency, or
  both.
- **Tests are part of done.** A feature without tests is not finished. This is
  deliberate and non-negotiable — see
  [`decisions/0010-test-strategy.md`](decisions/0010-test-strategy.md).

## 8. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Scope creep into the 6 deferred features | Nothing ships polished | Deferred specs are physically separate files. See `roadmap.md` §Cut line. |
| WebSocket reliability on a shared laptop | Demo breaks live | In-process registry, reconnect with backoff, optimistic UI. Spec 06. |
| Five people, five local DBs | "Works on my machine" | Compose is the only supported path. Migrations, never auto-create. |
| Photo blobs bloat Postgres | Slow queries, big backups | 2 MB cap, downscaled on upload, `bytea` not base64 in JSON. Spec 03. |
| Postgres never actually used because SQLite was quicker to start | Migration crunch on day 13 | Postgres from commit one. No exceptions. |

## 9. Where the detail lives

| Question | File |
|---|---|
| What does this feature do, exactly? | `specs/` |
| Why is the stack what it is? | `decisions/` |
| What do I do next? | `roadmap.md` |
| How do I run this? | `README.md` |
| What may I not do? | `AGENTS.md` §5 |