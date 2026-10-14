# One image, one origin: the built SPA is served by FastAPI from /app/static.
# See docs/deploy.md. The backend/Dockerfile is still there for the dev stack.

# ─── Frontend ────────────────────────────────────────────────────────────────
# node:22-slim, not alpine: rollup 4 has no musl build of its native binary and
# vite dies with "Cannot find module @rollup/rollup-linux-x64-musl". Same
# reason frontend/Dockerfile uses -slim.
FROM node:22-slim AS frontend
WORKDIR /build
# Lockfile first: this layer is cached until a dependency actually changes.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ─── Backend ─────────────────────────────────────────────────────────────────
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH="/app/.venv/bin:$PATH"

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt .
RUN python -m venv /app/.venv && pip install -r requirements.txt

COPY backend/ .
COPY --from=frontend /build/dist ./static

EXPOSE 8000

# Migrations and seed run here, not in a Render pre-deploy hook: there is one
# instance, so there is no deploy race, and the app cannot serve traffic against
# a schema it has not migrated. `python -m app.seed` is idempotent.
# $PORT is set by Render; the default keeps `docker run` and the dev stack honest.
CMD ["sh", "-c", "alembic upgrade head && python -m app.seed && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
