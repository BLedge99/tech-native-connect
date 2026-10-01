# 0001 — FastAPI backend, React frontend

**Status:** Accepted
**Date:** 2026-10-01
**Affects:** all specs

## Context

The team is five bootcamp students, mixed experience, with two weeks. We need a
stack that:

- has a fast feedback loop, because the demo depends on people iterating fast;
- one language per layer rather than a mix, so people can cover each other;
- is boring and well-documented, so an AI agent can write against it from a spec
  without guessing;
- has no hosted dependency, because there is no budget and no production deploy.

The stack was chosen before any feature was specced, so it had to be safe for
every feature we might build.

## Decision

**Python 3.12 + FastAPI + SQLAlchemy 2.0 (async) + Alembic + Pydantic v2 for
the backend. Vite + React 18 + TypeScript + React Router + Tailwind for the
frontend. PostgreSQL 16 for storage.**

## Rejected

| Option | Why it lost |
|---|---|
| **TypeScript everywhere (Next.js)** | Genuinely attractive — one language. Lost on the WebSocket story. Live chat is the demo's centrepiece ([06](../specs/06_messaging.md)), and Next.js splits real-time between a custom Node server and a separate service, or you accept a third-party realtime vendor. FastAPI gives first-class WebSocket support in the same process as the API, with no extra container. We trade one language for a much simpler live-chat path. |
| **Python backend + React** — chosen | — |
| **Django** | Batteries-included, which sounds good, but its ORM and admin are designed around a monolith. We want thin routers, services and an async WebSocket registry ([00_conventions.md](../specs/00_conventions.md) §8). Fighting the framework on both counts is work Django is supposed to save. |
| **Flask** | Synchronous by default. Async WebSockets need an extension, and the sync/async split would end up half-and-half across the codebase. |
| **React Native / Expo** | The brief asks for mobile-*friendly*, not mobile-native. A responsive web app covers it. A mobile app triples the surface for a demo run on a laptop. |
| **Python + Jinja templates** | The app is auth-gated and interaction-heavy — chat, filters, optimistic UI. Server-rendered templates do not fit. |
| **Go, Rust** | Faster, and completely wrong trade for a two-week student project. Nobody here is fast in them and the AI agents would be writing unfamiliar code. |

## Consequences

**Cost.** Two languages. Someone who wants to work "only on the backend" still
needs to read TypeScript in the frontend, and vice versa. Onboarding is slower.
Branch merges occasionally touch both trees.

**Gained.** Async WebSocket support in one process, which is the single
highest-risk feature in the project. Type safety on both sides. SQLAlchemy's
async session is a good fit for the notification writes that fire inside request
handlers ([07](../specs/07_notifications.md) §3).

**Risk to watch.** Python's default is sync. Any blocking call inside an async
handler stalls the event loop and takes the WebSocket down with it — so
`requests`, `time.sleep` and sync DB drivers are banned in request paths. This
is called out in [`00_conventions.md`](../specs/00_conventions.md) §8 rule 6.

**Also:** Pydantic v2 models double as the OpenAPI schema, so Swagger at
`/docs` is generated rather than maintained. That is free API documentation for
a demo, and it is a real part of why FastAPI was chosen.

## Related

- [0003](0003-vite-not-nextjs.md) — why the frontend is a plain SPA
- [0005](0005-websocket-in-process.md) — the realtime architecture
- [0002](0002-postgres-not-sqlite.md) — the database