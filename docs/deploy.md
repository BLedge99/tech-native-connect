# Deploying Bootcamp Connect

**Last updated:** 14 October 2026
**Target:** Render free tier, Neon Postgres, no mail provider
**Branch:** `web-deploy` — the only branch with the production build

---

## 1. Two ways to run this project — do not confuse them

| | Dev stack | Production build |
|---|---|---|
| Entry point | `docker-compose.yml` | `Dockerfile` |
| Command | `./run.bat` (or `docker compose up --build`) | Render Blueprint (`render.yaml`) |
| Shape | 4 containers: db, mailpit, backend, frontend | 1 image: FastAPI serves the built SPA from `static/` |
| Origin | `localhost:5173` (Vite proxies `/api` → `:8000`) | one origin, no proxy, no CORS |
| Mail | Mailpit on `:8025` | none — `DEMO_EXPOSE_MAGIC_LINKS=1` returns the link in the API response |
| Branches | `main`, `ben-test`, feature branches | `web-deploy` only |

**`./run.bat` is still the correct way to run the dev stack.** What it cannot
do is run the production build — that is a single image deployed to Render,
not a compose stack. If a task says "run the app", it means the dev stack
unless it explicitly says "deploy" or "production".

---

## 2. Running the dev stack (all testing happens here)

### Prerequisites

- **Docker Desktop with WSL2 backend** — this is the only supported
  environment. Docker, Node and Python all live inside the containers or
  inside WSL. **They are not installed on the Windows host and must not be.**
- Do not install, uninstall, or "repair" node, npm, python, pip or docker
  on the Windows host. Previous agents have caused serious damage this way.
  If `docker info` fails in PowerShell, that is expected — use `run.bat`,
  which detects WSL automatically.

### Commands

```powershell
.\run.bat              # build + start everything (default)
.\run.bat build        # build images only
.\run.bat down         # stop services (keeps data)
.\run.bat clean        # stop and delete all data
.\run.bat logs         # follow logs
.\run.bat panel        # open the dev panel at http://localhost:5173/dev
```

`run.bat` works with Docker Desktop (Windows), Docker Desktop (WSL2 backend),
and docker installed inside WSL. If `docker` fails on Windows it retries as
`wsl docker` automatically.

### Services

| Service | URL |
|---|---|
| Frontend | http://localhost:5173 |
| Backend API | http://localhost:8000 |
| API docs (Swagger) | http://localhost:8000/docs |
| Mailpit inbox | http://localhost:8025 |
| Adminer (DB GUI) | http://localhost:8080 |
| Dev panel | http://localhost:5173/dev |

### Demo logins

| Email | Password | Role |
|---|---|---|
| `priya@example.com` | `demo-password-123` | Business developer |
| `ben@bootcamp.example.com` | `bootcamp-dev-admin` | Admin |

Seeded by `backend/app/seed.py` on container start.

---

## 3. Running the tests

All four suites run **inside the containers**. Never run `pytest`, `npx` or
`node` on the Windows host.

```powershell
# Backend (unit + integration, real Postgres)
docker compose exec -T backend pytest tests -q

# Frontend component tests
docker compose exec -T frontend npx vitest run

# TypeScript
docker compose exec -T frontend npx tsc --noEmit

# E2E (Playwright, full demo path)
docker compose exec -T frontend npx playwright test

# Guard: no network mocking in E2E
node scripts/check-no-mocking.mjs
```

Expected: 300 backend, 39+ component, clean tsc, 19 E2E.

**After editing frontend source, restart the frontend container** — Vite HMR
does not reliably pick up changes on this WSL/Windows setup:

```powershell
docker compose restart frontend
```

### Deploy verification spec

`frontend/tests/zz-deploy-check.spec.ts` is excluded from the default suite.
Run it manually after a deploy:

```powershell
docker compose exec -T frontend npx playwright test zz-deploy-check
```

---

## 4. Deploying to Render

### One-time setup

1. **Neon** (neon.tech): create a project in **Frankfurt** (matches
   `render.yaml` region). Copy the **pooled** connection string.
2. **Render** dashboard → **New → Blueprint** → select
   `BLedge99/tech-native-connect`, branch `web-deploy`.
3. `render.yaml` prompts for two secrets:
   - `DATABASE_URL` — the Neon pooled connection string
   - `SEED_ADMIN_PASSWORD` — e.g. `bootcamp-dev-admin`
4. **GitHub repo variable** (required): repo Settings → Secrets and variables
   → Actions → Variables → `RENDER_URL` =
   `https://bootcamp-connect.onrender.com`. Without it the keepalive workflow
   fails every 14 minutes.

### What `render.yaml` already sets

| Var | Value | Why |
|---|---|---|
| `APP_ENV` | `production` | strict CSP, HSTS, secure cookies |
| `APP_URL` | `https://bootcamp-connect.onrender.com` | magic links + post-verify redirect |
| `CORS_ORIGINS` | same | WebSocket origin check validates against this |
| `DEMO_EXPOSE_MAGIC_LINKS` | `1` | no mail provider — link returned in API response |
| workers | 1 | WebSocket registry is per-process |

`config.py` rejects non-HTTPS `APP_URL`/`CORS_ORIGINS` in production — both
are already correct.

### What happens on first boot

The container `CMD` runs `alembic upgrade head && python -m app.seed`, then
uvicorn on `$PORT`. The healthcheck (`/api/v1/health`) may fail for ~30s
until migrations finish; Render retries automatically.

### Post-deploy smoke test

1. `curl https://bootcamp-connect.onrender.com/api/v1/health` →
   `{"status":"ok","database":"ok"}`
2. Load the landing page — SPA renders, no CORS or CSP errors in console.
3. Sign in as `priya@example.com` / `demo-password-123`.
4. Request a magic link for a seeded email → `demo_link` appears in the
   response and renders inline on the sign-in page.
5. Full demo path: edit profile → matches → connect → accept → live message
   in two browser windows.
6. Check the Actions tab — the keepalive workflow should pass.

---

## 5. Production build locally (optional)

To build the production image without Render:

```powershell
docker build -t bootcamp-connect .
docker run -p 8000:8000 -e DATABASE_URL=... -e SEED_ADMIN_PASSWORD=... -e APP_ENV=production -e APP_URL=http://localhost:8000 -e CORS_ORIGINS=http://localhost:8000 -e DEMO_EXPOSE_MAGIC_LINKS=1 bootcamp-connect
```

Note: `APP_ENV=production` requires HTTPS origins. For a local image test,
leave `APP_ENV=development` or the settings validator will reject
`http://localhost:8000`.

---

## 6. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `docker` not found in PowerShell | Docker Desktop not running, or WSL backend | Use `./run.bat` — it auto-detects |
| `docker compose` hangs | WSL backend not started | Start Docker Desktop, wait for it |
| Frontend serves stale code | Vite HMR unreliable on WSL | `docker compose restart frontend` |
| Magic link 404s | Link points at API port, not browser origin | `APP_URL` must be the browser origin |
| WebSocket rejected | Origin mismatch | `CORS_ORIGINS` must match the browser origin |
| Keepalive workflow fails | `RENDER_URL` repo variable not set | Add it in repo Settings → Actions → Variables |
| Healthcheck fails after deploy | Migrations still running | Wait 30s, Render retries automatically |
