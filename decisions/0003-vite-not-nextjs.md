# 0003 — Vite SPA, not Next.js

**Status:** Accepted
**Date:** 2026-10-01
**Affects:** [01](../specs/01_landing_page.md), [03](../specs/03_profiles.md), [06](../specs/06_messaging.md)

## Context

The frontend has to do a few things that are unusual: an auth-gated app behind
a login, optimistic message sending, a long-lived WebSocket, and one public page
that a marker sees first. Those pull in different directions — the public page
argues for server rendering, everything else argues against it.

## Decision

**Vite + React 18 + TypeScript + React Router + Tailwind CSS. A single-page
application talking to the FastAPI backend over `/api/v1`.**

## Rejected

| Option | Why it lost |
|---|---|
| **Next.js** | Rejected mainly on container count and architectural fit. Next.js needs a Node process for the app and, if you want a WebSocket, either a custom Node server or a separate realtime service — a third container and a second place for realtime bugs. The pitch page could use SSR, but it is five static sections ([01](../specs/01_landing_page.md) §2); Vite builds it as static assets with a Lighthouse score above 90 and nobody can tell the difference. The one genuine advantage of Next.js — SEO for a public page — does not apply, because the only public page is a pitch page that is never meant to be found by a search engine. |
| **Remix / React Router 7 in framework mode** | The React Router data layer is genuinely nice, but it re-couples the frontend to a server runtime, which is the coupling we just removed. We want the frontend to be a pure client that could be hosted anywhere. |
| **Create React App** | Effectively unmaintained. Vite is the same idea with a maintained tool and far faster cold start. |
| **Vue, Angular, Svelte** | No project-specific reason. React has the deepest AI-agent training data, which matters when the implementers are models as much as people. |
| **Tailwind + a component library (MUI, shadcn)** | Tailwind alone, no component library. See consequences. |
| **Server-rendered Jinja templates + HTMX** | Excellent for simple forms, poor for a chat client with optimistic updates. Not worth a hybrid. |

## Consequences

**Cost.** No server-side rendering. The pitch page ships as static assets, which
means the first paint needs a JS round trip. Acceptable because the audience is
a marker on a laptop on the same network, not a search crawler. If SEO ever
matters, that is a migration — not something we are buying speculatively.

**Gained.** One frontend container that is `vite build` plus a static file
server. Vite's dev server is fast enough that the edit-save-refresh loop does
not interrupt thought. And the dev proxy means the frontend only ever calls
relative `/api` paths, so no one hardcodes `localhost:8000` and breaks the app
on a different host.

**No component library.** Hand-rolled components with Tailwind. This is
deliberate: a component library is a large, opinionated dependency that has to
be learned before it can be used, and every person here would spend their first
day fighting it instead of shipping. Tailwind covers the styling and the
primitives are small enough to write. If a component is genuinely painful
without one — a date picker or a rich text editor — add that one library alone,
with an ADR.

**Risk to watch.** No server rendering means an unauthenticated flash is possible
if session state is not awaited before rendering a protected route. That is why
[`01_landing_page.md`](../specs/01_landing_page.md) §5 requires the auth guard
to wait for session resolution, and why
[`00_conventions.md`](../specs/00_conventions.md) §7 rule 5 forbids optimistic
UI for actions with real consequences.

**Also:** React Router v6's `createBrowserRouter` with a data-less fetch layer.
Do not pull in a server-state library to replace the two hooks we actually need
— see the consequences note in [0012](0012-monorepo-layout.md).

## Related

- [0001](0001-fastapi-and-react.md) — the full stack
- [0005](0005-websocket-in-process.md) — why no realtime vendor was needed