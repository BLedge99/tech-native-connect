# 0004 — Cookie sessions, not JWT

**Status:** Accepted
**Date:** 2026-10-01
**Affects:** [02](../specs/02_registration_and_login.md), all authenticated specs

## Context

Two authentication questions had to be answered: how the session is carried, and
how we protect against cross-site request forgery once cookies are in play.

The brief requires **no third-party auth vendor** ([0008](0008-magic-link-auth.md)),
so there was no provider to inherit an answer from.

The decisive consideration: **who is the client?** This is a browser SPA on the
same origin as the API, reached via the Vite proxy
([0003](0003-vite-not-nextjs.md)). Not a native app, not a third-party
integration.

## Decision

**Server-side sessions in a Postgres table, carried in an httpOnly cookie, with
a CSRF token header on mutating requests.**

- Opaque random 256-bit token in the cookie named `session`.
- **Only a hash of the token is stored** ([02](../specs/02_registration_and_login.md) §2).
- 7-day lifetime, sliding on activity.
- Logout deletes the row. Revocation is server-side, never just clearing the
  cookie.
- CSRF: `X-CSRF-Token` header must match the session's token on `POST`, `PUT`,
  `PATCH`, `DELETE`.

## Rejected

| Option | Why it lost |
|---|---|
| **JWT in `localStorage`** | The default advice for SPAs, and worse than cookies for this app. `localStorage` is readable by any XSS payload, so one unescaped field or a risky `dangerouslySetInnerHTML` hands over a session that works from anywhere for 7 days. HttpOnly cookies are not reachable from JavaScript at all. Beyond that, a JWT cannot be revoked before it expires — our logout requirement ([02](../specs/02_registration_and_login.md) §3) becomes "log out and hope", and the admin deactivate-user flow ([09](../specs/09_admin.md)) has no mechanism at all. |
| **JWT in an httpOnly cookie** | Better than `localStorage`, and the "best of both" answer. Rejected because it keeps the parts that cost us: two CSRF strategies (cookie needs the token header anyway, same as sessions), stateless verification that means the token cannot be revoked, and a signing secret plus expiry claims to get wrong. Since we pay CSRF costs either way, we take the simpler option that also gives revocation. |
| **Server-side session without a CSRF token, relying on `SameSite=Lax`** | Genuinely close, and it is what a lot of production apps do. `SameSite=Lax` blocks cross-site POSTs in current browsers, so the CSRF header is defence in depth. Rejected because `SameSite` has been a source of browser bugs, it does not protect against a subdomain attacker, and the header is about twenty lines. We keep both. |
| **Sessions in Redis** | The standard choice, and faster for a high-traffic app. Rejected: Redis would be a fifth container with no other reason to exist, we already need Postgres, and a session table is a `SELECT` by an indexed hash. For a cohort-sized app, a session table is the laziest thing that works. |
| **HttpOnly cookie holding a signed session blob (cookie-session style)** | No database, no lookup per request. Rejected for the same reason as JWT: no server-side revocation. |
| **Token in a query parameter** | Leaks into logs, `Referer` headers and browser history. Never. |

## Consequences

**Cost.** Every request does a `SELECT` on `sessions`. That is the real price:
no session cache, so an auth check is a database round trip on every API call
including `/users/me` and `/notifications/unread-count`, which runs on every page
load. At cohort scale, irrelevant.

**Second cost:** CSRF is our problem to implement and test correctly. It is in
[`00_conventions.md`](../specs/00_conventions.md) §3 and required in
[02](../specs/02_registration_and_login.md) §8.

**Gained.** XSS cannot steal a session — the cookie is unreachable from
JavaScript. Logout and admin deactivation both actually revoke. Revoking one
user's sessions is a row update, which is what makes
[09](../specs/09_admin.md)'s deactivate flow work at all.

**Risk to watch.** The cookie must be `httpOnly` and `SameSite=Lax` on every
response that sets it. Forgetting `httponly` on the logout response is harmless;
forgetting it on login is a real vulnerability, and
[02](../specs/02_registration_and_login.md) §8 asserts the cookie flags explicitly
for that reason.

**Also:** because tokens are opaque and stored hashed, "decode my session to get
the user id" is not a thing. Every handler gets the user from the session
dependency, never from a token payload —
[`00_conventions.md`](../specs/00_conventions.md) §3, and the reason client-supplied
user ids are banned.

## Related

- [0008](0008-magic-link-auth.md) — why we build auth ourselves at all
- [0002](0002-postgres-not-sqlite.md) — sessions need a real store
- [0007](0007-mailpit-dev-mail.md) — where magic link emails go in development