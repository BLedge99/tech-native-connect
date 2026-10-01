# 0007 — Mailpit for development email

**Status:** Accepted
**Date:** 2026-10-01
**Affects:** [02](../specs/02_registration_and_login.md)

## Context

The brief and our auth decision ([0008](0008-magic-link-auth.md)) both require
sending real emails — magic links at minimum. We are running entirely on our own
laptops, with no production deploy, no domain, and no budget for a transactional
email provider.

The team already knows the pattern: ddev ships Mailpit for Drupal projects, so
there was existing recognition of "a local mail server that catches mail in a
web UI". The question was which one, and whether to write our own.

## Decision

**Mailpit in Docker Compose as the development SMTP server. Real SMTP on port
1025, a web inbox on port 8025, and a REST API for tests. Zero configuration,
zero code.**

| Setting | Value |
|---|---|
| `MAILPIT_SMTP_HOST` | `mailpit` (the compose service name) |
| `MAILPIT_SMTP_PORT` | `1025` |
| `MAILPIT_WEB_URL` | `http://localhost:8025` |

In development there are no real SMTP credentials to store, because nothing is
actually delivered.

## Rejected

| Option | Why it lost |
|---|---|
| **Writing our own "mail catcher"** | Genuinely tempting — it is about forty lines: accept SMTP, write the message to a table, render it at a route. Rejected because it is forty lines that must stay working for the whole project and are not the point. Mailpit is a maintained Go binary that does the same thing, plus MIME parsing, attachments, search and a REST API for tests. The custom version is strictly the same with worse edge cases. |
| **python `smtpd` / `aiosmtpd` in-process** | Deprecated in the stdlib, and ties email into the backend's event loop. A crash in the app takes the mailbox with it. |
| **A `.eml`-file drop directory** | No SMTP, so it cannot be a genuine integration test of the send path. You end up testing your file writer rather than your SMTP configuration, and you find out at deploy time that the SMTP call was wrong. |
| **MailHog** | The previous generation, and what ddev used to bundle. Works, but Mailpit is actively maintained, faster, and has a better API. |
| **Mailpit in a Go process we run by hand** | Mailpit is one static binary — but running it inside the compose file means `docker compose up` is the only command anyone needs. That consistency is worth more than saving a container. |
| **A real provider (Resend, SendGrid, SES)** | Needs an account, an API key, a verified domain and a paid tier once the trial ends. Also breaks the "no third-party services" constraint and would send real emails to real addresses during testing. |
| **No email at all — password only** | Would have been the fastest path, and the brief's magic link was a soft requirement. Rejected because the brief asked for it and it is a small feature: a table, a token generator, and an SMTP call. Dropping it to save half a day would also have made the brief's auth story slightly weaker for a marker. |

## Consequences

**Cost: none.** This is the cheapest good decision in the set. No credentials, no
account, no code, no cleanup. Mailpit is a compose service someone writes once.

**Gained.** Magic links work end to end during development, including in tests.
The REST API means tests can assert on delivery and follow links without
parsing HTML. Everyone on the team has the same inbox at the same URL. And when
someone says "I clicked the link and it did not work", the answer is visible in
a browser rather than hidden in a real inbox somewhere.

**Two conveniences worth knowing about:**

1. **A dev-only shortcut in the login UI.** When `APP_ENV === 'development'`,
   the magic-link page also shows the link inline
   ([02](../specs/02_registration_and_login.md) §5). This makes testing login
   instant and is stripped from production builds. Guarded on the env var — it
   must not exist in production, or it is a login bypass for anyone who knows
   the build is unconfigured.
2. **The REST API in tests.** `GET /api/v1/messages` on Mailpit returns
   delivered mail as JSON. Playwright can read the magic link and click it
   directly, which is what makes the magic-link E2E test
   ([02](../specs/02_registration_and_login.md) §8) possible without a human in the
   loop.

**Risk to watch: Mailpit being unreachable must not break a request.** If the
mail container is down, `POST /auth/magic-link` should still return `202` with a
log line and a startup warning. Returning `500` for an optional convenience is
wrong — the user asked for a link and we should not show them a server error.
Specified in [02](../specs/02_registration_and_login.md) §6.

**Also:** no templating engine. Emails are plain text with a subject and a
one-line purpose. There are two email types and both are trivial; Jinja2 for
them is a dependency with no payoff. If the email count grows past about five,
revisit.

## Related

- [0008](0008-magic-link-auth.md) — the feature that makes this necessary
- [0012](0012-monorepo-layout.md) — where the service is defined