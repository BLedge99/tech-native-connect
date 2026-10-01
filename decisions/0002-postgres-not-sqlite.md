# 0002 — PostgreSQL from day one

**Status:** Accepted
**Date:** 2026-10-01
**Affects:** all specs

## Context

The app has relational data — users, profiles, connection requests, messages,
notifications — with real foreign keys and state machines that must not be
invalid. `AGENTS.md` §5 rules 2, 3 and 4 are all about relationships holding
under pressure, and several feature specs deliberately rely on **database
constraints** rather than application checks:

- one connection request per pair ([05](../specs/05_connection_requests.md) §1)
- one skill per profile, via a composite primary key ([03](../specs/03_profiles.md) §3)
- one RSVP per user per event ([deferred_events](../specs/deferred_events.md))
- `profile_complete` as a stored computed value
- a partial index on unread notifications ([07](../specs/07_notifications.md) §2)

The question was raised explicitly: **SQLite now, Postgres later?** It is a
serious question, because SQLite is zero-setup and Postgres is a container. The
team's instinct was to start on SQLite and migrate near the demo.

## Decision

**PostgreSQL 16, from the first migration. SQLite is not used, not even in
tests.**

## Rejected

| Option | Why it lost |
|---|---|
| **SQLite now, Postgres at the demo** | Rejected after a specific discussion of what the switch actually costs. It is not "change the URL". It is: (1) **`citext` for case-insensitive email** — SQLite has no equivalent, so case-insensitive login silently stops working; (2) **`bytea` photo blobs** — SQLite stores large blobs as incrementing text, which is slow and bloats the file; (3) **`gen_random_uuid()`** — SQLite's `randomblob()` function is not UUID-formatted, so every ID in the schema changes; (4) **partial indexes** — unsupported on SQLite, and the unread-notifications index in [07](../specs/07_notifications.md) §2 depends on them; (5) **`timestamptz`** — SQLite stores naive strings, so all timestamps would need reinterpreting on migration; (6) **concurrent writes** — SQLite's single-writer model returns `database is locked` under concurrent writes, and with five people testing in parallel that is a guaranteed afternoon of confusion. Six real differences, all of them load-bearing, all of them discovered on day 13. |
| **In-memory SQLite for tests** | Tempting for speed. Rejected because tests would pass against a different engine than production, which defeats the purpose of integration tests ([0010](0010-test-strategy.md)). Real Postgres in tests is the only version of this that catches the actual differences. |
| **Postgres with a separate Docker container** — chosen | — |
| **MongoDB** | No foreign keys, no composite-PK uniqueness, no partial indexes. Every constraint above becomes application code, and application code with five contributors in a race condition is how duplicate connection requests appear in the demo. |
| **Supabase / hosted Postgres** | A hosted database would solve setup, but it needs credentials, a network connection and a free-tier project, none of which exist. A local container in the same compose file needs none of that, and works on a plane. |

## Consequences

**Cost.** Postgres is a container, so `docker compose up` must be working before
anyone tests anything. That makes [roadmap](../roadmap.md) §0 (foundations) a
real prerequisite rather than a formality — there is no SQLite fallback if the
container will not start, and there should not be. Integration tests are slower
than they would be against a file; we accept that in exchange for testing the
real engine.

**Gained.** The constraints that make the specs safe are enforced by the
database, which means five people and several AI agents cannot each invent their
own duplicate check. Enum types reject invalid roles at the storage layer.
Partial and composite indexes are available when the query needs them.

**Risk to watch.** Five developers running five Postgres containers is fine, but
**migrations must go through Alembic** and never `create_all`. Someone's local
database will drift from everyone else's otherwise, and the first symptom is a
stack trace that only appears on one machine. [`00_conventions.md`](../specs/00_conventions.md) §8
rule 4.

**Also:** keep `DATABASE_URL` in one place in `config.py` so the switch to a
hosted database, if it ever happens, is one env var and nothing else.

## Related

- [0006](0006-images-as-pg-blob.md) — `bytea`, one of the reasons Postgres is not optional
- [0010](0010-test-strategy.md) — real Postgres in integration tests
- [0012](0012-monorepo-layout.md) — where compose lives