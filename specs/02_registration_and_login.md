# 02 — Registration, login and sessions

**Goal:** a user can create an account, get back in, and be identified
reliably. Everything else depends on this working.

**Depends on:** foundations only ([roadmap](../roadmap.md) §0)
**Blocks:** every other feature.

**Implementation status:** Implemented 2 Oct 2026 — see the *As built* note at the end of this document for deviations from the spec.

---

## 1. Scope

| In | Out |
|---|---|
| Email + password registration | OAuth (Google, GitHub) — see [ADR 0008](../decisions/0008-magic-link-auth.md) |
| Password login | SMS, 2FA |
| Magic-link login (passwordless) | Choosing course/role/skills at signup — see [03](03_profiles.md) |
| Logout, server-side session revocation | Account deletion — [`deferred_*`](deferred_privacy_settings.md) |
| `current_user` endpoint | |
| Seeded admin accounts | Admin screens — [09](09_admin.md) |

### Why signup does not collect profile details

The brief's flow is: sign up, **then** complete a profile. Collecting role,
course and skills at signup makes the form long, gives an invalid state (half
finished registration), and puts profile fields in two places.

Signup takes exactly three fields: email, password, display name. Everything
else happens in [03](03_profiles.md). If you are tempted to add a course
dropdown to the signup form, stop and read [03](03_profiles.md) §2.

## 2. Data model

### `users`

| Column | Type | Notes |
|---|---|---|
| `id` | `uuid` PK | `gen_random_uuid()` |
| `email` | `citext` | **Unique.** Case-insensitive — `Alice@x.com` and `alice@x.com` are one user. |
| `password_hash` | `text` | Argon2id. Never plaintext, never reversible. |
| `display_name` | `varchar(80)` | What other users see |
| `first_name` | `varchar(50)` | Greets the user, defaults from email local part |
| `is_admin` | `boolean` | Default `false` |
| `is_active` | `boolean` | Default `true`; admin can deactivate |
| `created_at` | `timestamptz` | |
| `last_login_at` | `timestamptz` nullable | |
| `email_verified_at` | `timestamptz` nullable | Set by magic-link verification |

### `sessions`

| Column | Type | Notes |
|---|---|---|
| `id` | `uuid` PK | |
| `user_id` | `uuid` FK → `users.id` | `ON DELETE CASCADE` |
| `token_hash` | `bytea` | **Hash of** the cookie value, never the token itself |
| `csrf_token` | `bytea` | |
| `expires_at` | `timestamptz` | 7 days out |
| `created_at` | `timestamptz` | |
| `last_used_at` | `timestamptz` | Sliding expiry |

**Storing a hash of the session token matters.** A leaked database dump must not
hand over live sessions. Same reasoning as the password hash.

### `magic_link_tokens`

| Column | Type | Notes |
|---|---|---|
| `id` | `uuid` PK | |
| `user_id` | `uuid` FK → `users.id` | |
| `token_hash` | `bytea` | |
| `expires_at` | `timestamptz` | **15 minutes.** Shorter than a session — this is a login credential. |
| `used_at` | `timestamptz` nullable | Single use |
| `created_at` | `timestamptz` | |

### Indexes

- `users.email` unique (`citext` gives case-insensitivity).
- `sessions.token_hash` unique — this is the auth lookup, it runs on every request.
- `sessions.user_id`, `sessions.expires_at` for cleanup.
- `magic_link_tokens.token_hash` unique.

## 3. Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `POST` | `/api/v1/auth/register` | none | Create account |
| `POST` | `/api/v1/auth/login` | none | Password login |
| `POST` | `/api/v1/auth/logout` | session | Revoke current session |
| `POST` | `/api/v1/auth/magic-link` | none | Request a link |
| `GET` | `/api/v1/auth/magic-link/verify?token=` | none | Consume link, create session |
| `GET` | `/api/v1/users/me` | session | Current user |
| `GET` | `/api/v1/health` | none | Liveness + DB check |

### `POST /auth/register`

```jsonc
// request
{ "email": "sam@example.com", "password": "correct-horse", "display_name": "Sam" }

// 201
{
  "id": "…uuid…",
  "email": "sam@example.com",
  "display_name": "Sam",
  "first_name": "Sam",
  "is_admin": false,
  "profile_complete": false,
  "created_at": "2026-10-02T10:00:00Z"
}
```

Sets the session cookie on success — registration logs you in. Redirecting to
the login form after signup is a worse experience and nobody asked for it.

| Case | Status | `code` |
|---|---|---|
| Success | `201` | — |
| Email already registered | `409` | `email_taken` |
| Invalid email / short password | `422` | `validation_error` |
| Deactivated account | `403` | `account_deactivated` |

**`409` not `422` for a duplicate email.** It is a state conflict, not a
format problem. Distinguishing them matters because a `422` on email reads as
"your email is malformed" and confuses users.

### `POST /auth/login`

```jsonc
// request
{ "email": "sam@example.com", "password": "correct-horse" }

// 200 — same user shape as register
```

| Case | Status | `code` |
|---|---|---|
| Success | `200` | — |
| Wrong email or password | `401` | `invalid_credentials` |
| Deactivated | `403` | `account_deactivated` |

**Wrong email and wrong password return the identical response.** Different
messages leak which emails are registered. A single integration test must
assert both cases produce byte-identical bodies.

### `POST /auth/logout`

`204`, deletes the session row, clears the cookie. Idempotent — logging out
twice is not an error.

### `POST /auth/magic-link`

```jsonc
{ "email": "sam@example.com" }  // → 202
```

**Always `202`, whether or not the email exists.** A `404` here turns the
endpoint into an account-enumeration oracle. The response says "if that address
has an account, a link is on its way."

Generates a single-use token, stores its hash, and sends an email through
Mailpit with the link. Only one active token per user — requesting a new one
invalidates the old, or old links in inboxes keep working.

### `GET /auth/magic-link/verify?token=`

Consumes the token, marks the user verified, creates a session, redirects to
`/` or the `from` path.

| Case | Result |
|---|---|
| Valid | Session cookie set, `302` to `/` |
| Expired | `400` `magic_link_expired` |
| Already used | `400` `magic_link_used` |
| Unknown | `400` `invalid_magic_link` |

Used and invalid must be **different codes** (both `400`). It helps debugging
and leaks nothing to an attacker who already holds a dead token.

### `GET /users/me`

Returns the full current-user shape including `profile_complete`. `401`
without a valid session. This is the endpoint the whole frontend bootstraps
from.

## 4. Validation

| Field | Rule | Error |
|---|---|---|
| `email` | Valid, ≤ 254 chars, normalised (trim, lowercase) | `422` |
| `password` | 8–128 chars, not in a small common-password list | `422` |
| `display_name` | 2–80 chars, trimmed, not whitespace-only | `422` |
| `first_name` | 1–50 chars, auto-derived if absent | `422` |

**Normalise before you store.** Trim and lowercase the email at the boundary so
whitespace and case never create a second account.

**Password length cap of 128 is deliberate.** Argon2id is deliberately slow;
without a cap a 10 MB password is a trivial denial-of-service.

## 5. Frontend

Three pages: `/register`, `/login`, `/forgot-password`.

### Registration

Three fields. On success go straight to `/` — the user is logged in.

Show a duplicate-email `409` inline on the email field, not as a toast. The
user is looking at the form; that is where the answer belongs.

### Login

Email and password. On `401 invalid_credentials`, show "Incorrect email or
password" — never which one was wrong.

Preserve the destination. Read `from` from the query string, then:

```ts
// Guard against open redirect: only same-origin, single-slash paths.
const dest = from && from.startsWith('/') && !from.startsWith('//') ? from : '/';
navigate(dest);
```

### Magic link

Email input → "check your inbox". Because there is no real inbox, add a
development convenience: when `APP_ENV === 'development'`, also show the link
inline with a note that this is a dev-only shortcut to Mailpit. It makes
testing login trivial and it is stripped from production builds.

### Session bootstrap

Every page load needs to know whether there is a session before rendering.

```ts
const { data, isLoading } = useQuery({
  queryKey: ['me'],
  queryFn: () => api.get('/users/me'),
  retry: false,          // 401 means "logged out", not "try again"
  staleTime: 5 * 60_000,
});
```

`retry: false` matters. Without it, a logged-out visitor gets three retries
with backoff on every page load before the guard fires. While `isLoading`, the
route guard renders a spinner rather than deciding the user is logged out —
otherwise a logged-in user sees a login flash on every refresh.

## 6. Mail

| Setting | Value |
|---|---|
| SMTP host | `mailpit` |
| SMTP port | `1025` |
| Web UI | `http://localhost:8025` |
| From address | `no-reply@bootcampconnect.local` |

In development, Mailpit credentials are hardcoded — it is a local sink, there
is no credential to leak.

**Be honest about delivery.** In development, `mailpit` unreachable must not
break the request. Log it and still return `202` — a user asking for a link
should not see a `500`. Add a startup warning that mail is not being delivered.

Emails are plain text first, and have a subject and a one-line purpose. No
templating engine — [ADR 0007](../decisions/0007-mailpit-dev-mail.md).

## 7. Seeding

`seed.py` must be idempotent — safe to run repeatedly without duplicating.

### Admin accounts

The five project participants are admins from day one. A config file lists
them:

```python
ADMIN_EMAILS = ["ben@…", "joey@…", "james@…", "alys@…", "mick@…"]
ADMIN_PASSWORD = os.environ["SEED_ADMIN_PASSWORD"]  # never a hardcoded default
```

Set `is_admin=True` on those emails, and let the admin panel grant admin to
anyone else — [09](09_admin.md).

`SEED_ADMIN_PASSWORD` must be required with no fallback. A hardcoded default
password is a committed secret and will outlive the project.

### Demo data

Also seed ~15 realistic users (a mix of `software_developer` and
`business_developer`), courses, skills, interests, connections in mixed states
(pending, accepted, none), threads with messages, notifications and project
ideas. Without this, matching has nothing to rank and the demo shows empty
screens.

Demo data must be obviously fake. Not `user1@…`. Use names, not
`Test User`, and plausible bios.

## 8. Tests

### Unit — `services/auth.py`

| Test | Asserts |
|---|---|
| `test_register_normalises_email` | `"  Sam@Example.COM "` → `sam@example.com` |
| `test_register_rejects_short_password` | 7 chars → validation error |
| `test_register_rejects_known_common_password` | `"password123"` rejected |
| `test_login_unknown_email_equals_wrong_password` | **Byte-identical responses.** Enumeration guard. |
| `test_magic_link_invalidates_previous_token` | Old link `400`, new one works |
| `test_magic_link_is_single_use` | Second consume → `400` |
| `test_magic_link_expires` | Past `expires_at` → `400` |
| `test_magic_link_unknown_email_returns_202` | Enumeration guard |
| `test_password_hash_is_argon2id` | Prefix `$argon2id$` |
| `test_session_token_is_hashed_at_rest` | No raw token in `sessions` |
| `test_logout_revokes_session` | Cookie after logout → `401` |
| `test_deactivated_user_cannot_login` | `403 account_deactivated` |

### Integration — every `AGENTS.md` §5 rule

| Test | Asserts |
|---|---|
| `test_me_requires_session` | **Rule 1.** No cookie → `401` |
| `test_me_rejects_bogus_cookie` | Forged token → `401` |
| `test_me_rejects_expired_session` | Past `expires_at` → `401` |
| `test_register_sets_session_cookie` | `httponly`, `samesite=lax` |
| `test_mutating_request_without_csrf_token` | **§3 CSRF** → `403 csrf_failed` |
| `test_mutating_request_with_wrong_csrf_token` | `403` |
| `test_duplicate_email` | `409 email_taken` |
| `test_error_bodies_match_conventions` | Every shape from `00` §2 |
| `test_health` | `200`, DB reachable |

### E2E

1. Register with a new email → logged in → home feed.
2. Log out → log back in → still there.
3. Request a magic link → open Mailpit → click → logged in.
4. Wrong password → inline error, no navigation.
5. Logged out, deep-link `/matches` → redirected to login → after login,
   back at `/matches`.
6. Register → duplicate email → inline "already registered".

## 9. Out of scope

OAuth, password reset by email (covered by magic link for now), two-factor,
email verification on password signup (only magic-link verification sets it),
session listing UI, "remember me" (the cookie already lasts 7 days), account
deletion.

## 10. Definition of done

- [x] All seven endpoints implemented
- [x] `seed.py` creates 5 admins + realistic demo data, idempotently
- [x] Argon2id password hashing, hashed session tokens
- [x] CSRF enforced on all mutating routes
- [x] Unknown email and wrong password byte-identical
- [x] Magic link single-use, 15-minute expiry, previous token invalidated
- [x] Dev-only magic-link shortcut behind `APP_ENV` guard
- [x] Every §8 test passes

## 11. Agent notes

- **Argon2id, not bcrypt.** Both are fine; bcrypt's 72-byte input limit silently
  truncates longer passwords. Pick one library and use it everywhere.
- **`retry: false` on the `/users/me` query.** Easy to miss, causes a visible
  delay on every logged-out page load.
- **Don't reveal whether an email exists.** Four separate endpoints need this
  treatment. It is an enumeration rule, not a nicety.
- **`SEED_ADMIN_PASSWORD` has no default.** Do not "temporarily" hardcode one.
- Check `00_conventions.md` §2 before inventing any error code.
---

## 13. As built — 2 October 2026

**Four deviations.** All additive; none changes the specified behaviour.

### 13.1 `csrf_token` is returned by `/users/me`, `/auth/register` and `/auth/login`

The session cookie is `httpOnly`, so JavaScript cannot read it. The client
therefore has no way to learn the CSRF token except from a response body. This
spec only listed `/users/me`.

Without it there is a window — up to a second after signup — in which the
client has a session but no token, and **every mutating request fails `403`**.
Two bugs shipped in that window during implementation: registration appeared
broken entirely, and logout silently did nothing.

`GET /users/me` returns `MeOut`, a `UserPrivate` plus `csrf_token`. The two auth
endpoints return the same shape via `_session_body()` in
[`routers/auth.py`](../backend/app/routers/auth.py), which reads
`session.csrf_token` — **not** the session token.

### 13.2 Admin accounts use `@bootcamp.example.com`, not `@bootcampconnect.local`

`EmailStr` rejects `.local`, so the address in §7 returns `422` on login and no
admin could ever sign in. `seed.py` uses the reserved `example.com` domain,
which can never be a real address. Five accounts, unchanged otherwise.

### 13.3 `POST /auth/register` returns `201` and logs the user in

As specified in §4. Worth restating because the frontend depends on it: the
response *is* the session, so registration is a single round trip.

### 13.4 `REVALIDATE` the session after login

Not a spec change — an implementation rule worth recording. The initial
`GET /users/me` fires on app mount and can resolve *after* a fast login, writing
a stale `null` session over the new one. `useSessionState()` guards this with a
`sessionGeneration` ref, and `adopt()` (used by register and login) bumps it so an
in-flight check cannot undo the session it raced.

**Test coverage:** 26 backend tests in `tests/unit/test_auth.py` and
`tests/integration/test_permissions.py` covering password hashing, token hashing
at rest, CSRF, email normalisation, byte-identical enumeration responses, magic
link single-use, and session expiry. 4 E2E tests covering the pitch page,
wrong-password inline error, deep-link return, and duplicate-email rejection.

**Known gap:** the magic link flow has **no E2E test**. `POST /magic-link` and
the Mailpit container are covered by backend tests, but nothing follows the link
in a browser. Mailpit's REST API makes this easy and it is the one auth path
without browser-level coverage.
