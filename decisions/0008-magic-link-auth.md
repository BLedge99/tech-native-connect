# 0008 — Build auth ourselves, with a magic link

**Status:** Accepted
**Date:** 2026-10-01
**Affects:** [02](../specs/02_registration_and_login.md), [03](../specs/03_profiles.md)

## Context

Registration and login are on the brief's essential list, and every other
feature depends on them. Auth is also the one place where a wrong choice is a
security problem rather than an inconvenience.

Three constraints shaped this. We are not running in production. We have no
budget. And the project brief explicitly asked for magic links.

The tempting default for a student project is Supabase Auth or Firebase Auth —
free tier, drop-in, and it would have saved us most of a day.

## Decision

**Build authentication ourselves: email and password with Argon2id hashing,
plus a passwordless magic link. No third-party auth vendor.**

- Argon2id via `argon2-cffi`.
- Opaque server-side sessions in Postgres, hashed at rest
  ([0004](0004-cookie-sessions-not-jwt.md)).
- Magic link: single-use, 15-minute expiry, previous token invalidated on
  re-request.
- A seeded list of admin emails, since project participants are admins
  ([09](../specs/09_admin.md)).

## Rejected

| Option | Why it lost |
|---|---|
| **Supabase Auth** | The strongest alternative and the one most likely to be the right call in a different project. Rejected for three reasons: it needs an account and an API key, which means five people each need project credentials and a deploy key — a real setup tax before anyone can sign in. It introduces a hosted dependency, violating the "no third-party services" constraint in [`PRD.md`](../PRD.md) §7. And it pulls Supabase's Postgres convention along with it, which collides head-on with [0002](0002-postgres-not-sqlite.md) — we would end up with two databases. |
| **Auth0 / Clerk** | Polished and genuinely good, but both require an account, a domain, and for Auth0, paid tiers. Clerk's free tier is limited to a fixed user count, which is a bad property for something a marker might sign up for. Not worth a dependency for a cohort app. |
| **Firebase Auth** | Needs a Google Cloud project. Same objection. |
| **OAuth with Google and GitHub** | Tempting because developers already have accounts. Rejected because it requires client IDs and callback URLs, which means every developer's local environment needs its own registration — the "works on my machine" problem in its purest form. It also adds a provider dependency to the most security-sensitive feature. |
| **Sessions in `localStorage`, no httpOnly cookie** | Rejected on security; see [0004](0004-cookie-sessions-not-jwt.md) §Rejected. XSS-readable. |
| **Building a custom cryptography scheme** | Obviously rejected. Argon2id via a well-known library; never roll your own. |
| **JWTs** | Rejected — cannot be revoked, which breaks logout and admin deactivation. [0004](0004-cookie-sessions-not-jwt.md). |

## Consequences

**Cost, and it is the largest single cost in this project: we build and own
password reset, email verification, session expiry, session revocation, login
throttling and account enumeration defences.** That is real work, and it is
roughly what a vendor would have given us for free.

Specifically:

- Password hashing and its configuration are ours to get right
  ([02](../specs/02_registration_and_login.md) §4).
- Magic links need a table, a token generator, an expiry policy, single-use
  enforcement, and invalidation of prior tokens.
- **Account enumeration** has to be handled deliberately in four places
  ([02](../specs/02_registration_and_login.md) §3) — unknown email and wrong
  password must be byte-identical, and `POST /magic-link` must always return
  `202`. A vendor would have done this by default; ours will not unless we write
  it.
- Login rate limiting is ours. The `429` code is reserved in
  [`00_conventions.md`](../specs/00_conventions.md) §2 but the implementation is
  not required for the demo.

**Gained.** Full control, no keys, no accounts, no vendor outage, no per-user
pricing, no callback URL configuration on five machines. The auth logic is a
dozen unit-testable functions and it is all in one repo where it can be read in
one sitting. And "we built our own auth" is a defensible answer for a
bootcamp project with a real security surface.

**Risk to watch, and it is the thing a marker will probe:** hand-rolled auth is
where hand-rolled bugs live. The mitigations are specific — Argon2id rather than
a hand-rolled hash, hashed session tokens, byte-identical enumeration responses,
single-use magic links with short expiry, httpOnly cookies. Each has a test in
[02](../specs/02_registration_and_login.md) §8. **Do not "simplify" any of them.**

**Also:** because there is no vendor, there is no vendor dashboard to inspect, no
webhook to handle, and no way to delete a user through an admin API.
Deactivation is ours ([09](../specs/09_admin.md)), which is a fine outcome.

**Password reset is not implemented.** The magic link covers the common case —
"I cannot log in" — with no separate flow. If someone specifically needs to reset
a password they know, that is deferred scope, and honestly a fair thing to
admit in a demo.

## Related

- [0004](0004-cookie-sessions-not-jwt.md) — the session mechanism
- [0007](0007-mailpit-dev-mail.md) — where magic link emails go in development
- [0002](0002-postgres-not-sqlite.md) — why sessions need a real store