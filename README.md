# Cohort Connect

Full-stack cohort networking demo built from specs 00–09 supplied with the project.

## Stack
- React + TypeScript + Vite + Tailwind
- FastAPI + async SQLAlchemy + PostgreSQL
- Alembic migrations
- httpOnly server-side cookie sessions + CSRF
- WebSocket endpoint for realtime expansion

## Run
```bash
docker compose up -d --build
```

On Windows PowerShell, use `\.\run.bat` to start the stack in the background.
Stop it with `docker compose down`.
Open http://localhost:5173

Seed users:
- admin@example.com / password123
- priya@example.com / password123
- sam@example.com / password123

## Implemented product loop
Register/login → complete profile → deterministic matches → connection request → accept → thread → messages → notifications. Project ideas and an admin surface are included.

## Deferred by specification
AI icebreakers, events, privacy/account export, and safety moderation are intentionally not included.
