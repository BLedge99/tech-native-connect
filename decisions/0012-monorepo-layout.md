# 0012 — Single repo, `backend/` and `frontend/`

**Status:** Accepted
**Date:** 2026-10-01
**Affects:** every spec; [`AGENTS.md`](../AGENTS.md) §3

## Context

Five people, two languages, four Docker services, one repository. The layout has
to answer three questions:

1. Where does a contributor start?
2. How does a runnable stack come up with one command?
3. Where do the docs live relative to the code they describe?

The obvious default is a monorepo with `backend/` and `frontend/`, and the
alternative is two repos. That was the only real question, plus whether the
compose file lives at the root or inside the backend.

## Decision

**One repository. `backend/` and `frontend/` as top-level directories,
`docker-compose.yml` at the root, and the documentation at the root next to it.**

```
.
├── AGENTS.md          ← the agent entry point
├── PRD.md
├── roadmap.md
├── README.md
├── specs/             ← one doc per feature
├── decisions/         ← numbered ADRs
├── backend/           ← FastAPI, SQLAlchemy, Alembic, pytest
├── frontend/          ← Vite, React, TS, Vitest, Playwright
├── e2e/               ← Playwright, full stack
└── docker-compose.yml
```

**One `docker compose up` starts Postgres, the backend, the frontend and
Mailpit.** Every contributor runs the identical stack, and it is the only
supported path.

Supporting decisions, recorded here so they are not re-litigated:

- **Backend and frontend have separate `package.json` / `pyproject.toml`.**
  Separate dependency lifecycles.
- **The frontend talks to `/api` relatively**, via a Vite proxy.
- **Playwright tests live at the root `e2e/`**, not inside `frontend/e2e/`,
  because they drive the whole stack, not the frontend alone.
- **No workspace monorepo tooling.** No Turborepo, no Nx, no pnpm workspaces
  for two packages.

## Rejected

| Option | Why it lost |
|---|---|
| **Two repositories, one per language** | Rejected on the demo, which is the actual test. `git clone` twice, two terminals, two branches to keep in step, and a schema change that touches the frontend needs two coordinated PRs. For five people, the coordination cost is larger than the benefit of clean language boundaries — and TypeScript already gives us the type boundary we actually want. |
| **A monorepo with Turborepo or Nx** | Optimised for large repos with dozens of packages and incremental build caching. We have two. The config file would be longer than the thing it configures, and it is another tool for five people and several AI agents to agree about. |
| **pnpm workspaces / Yarn workspaces** | Genuinely useful for shared packages. We have no shared package — the API contract lives in the specs, which is the right place for it. Zero shared code, zero need for workspaces. |
| **Next.js API routes as the backend** | Would remove the backend directory entirely, which is appealing. Rejected because FastAPI's WebSocket support is the reason for the whole split ([0001](0001-fastapi-and-react.md)), and because Pydantic-generated OpenAPI at `/docs` is worth a lot for demonstrating the API. |
| **Compose file inside `backend/`** | Then `docker compose up` needs a `-f` flag or a `cd`, and the frontend service has to reach out with `../frontend`. The root is where a person standing in the repo expects it. |
| **A separate `infra/` directory for compose** | Organised in principle, and one more place to look. Four services do not need their own directory. |
| **`docs/` subdirectory for all the markdown** | Tidy, but it puts the entry point two levels down. **`AGENTS.md` at the root is the first thing an AI agent reads**, and `README.md` next to it is the first thing a person reads. Both should be found by `ls`. |
| **Kebab-case directory names (`my-project/`)** | Avoided deliberately. Dashes in directory names break Python imports unless they are packages, and they break `FROM` paths. |

## Consequences

**Cost: repository-level git operations are slower.** Every commit includes both
languages, so `git log -- backend/` is the way to read history for one area.
At this size that is a minor inconvenience; at ten times this size it would not
be, and we would split then.

**Cost: the frontend has no build-time access to backend types.** We chose specs
as the contract rather than generating types from the OpenAPI schema. If the
frontend starts hand-maintaining interface definitions that drift from the
backend, that is the signal to generate them from `/openapi.json` — as a later
ADR, not silently.

**Gained: one command, one stack, no drift.** The "works on my machine"
problem is solved by there being only one supported way to run things
([0001](0001-fastapi-and-react.md), [0002](0002-postgres-not-sqlite.md)).
Documentation sits beside the code it describes, so a spec and the feature it
specifies are edited in the same PR.

**Gained: a coherent PR.** A feature is backend, frontend, tests, spec status
update and ADR if needed — one branch, one review, one merge. With two repos
that is five PRs and a merge window.

**Gained: documentation is the entry point.** [`AGENTS.md`](../AGENTS.md) at the
root is findable by `ls`, and it is the first file any AI agent reads. That is
the mechanism that makes this whole set of documents work.

**Risk to watch:** five contributors and several AI agents writing to one
directory tree. Mitigated by branch-per-feature naming in `AGENTS.md` §4 and by
keeping routers thin so most conflicts land on distinct files.

**Also:** because there is no workspace tooling, `docker-compose.yml` must be
the only entry point. Do not add a Makefile or task runner that duplicates it —
that is a second thing to keep in step, and it is the exact problem workspaces
were rejected for.

## Related

- [0001](0001-fastapi-and-react.md) — why there are two directories at all
- [0003](0003-vite-not-nextjs.md) — the frontend's shape
- [0002](0002-postgres-not-sqlite.md) — one of the four services