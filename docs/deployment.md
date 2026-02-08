# Deployment Guide (MVP v0.1.0)

Date: 2026-02-07

## 1. Scope

This guide covers single-host MVP deployment for BeeBeeBrain using Docker Compose:
1. `backend` (FastAPI + SQLite)
2. `frontend` (Vite build served by Nginx)
3. Persistent volumes for database and workspace data

## 2. Environment Requirements

1. Docker Engine 24+
2. Docker Compose v2+
3. At least 2 CPU and 4 GB memory
4. Disk space: 5 GB minimum for image + DB + logs

## 3. Configuration and Secrets

Create a root `.env` file (same directory as `docker-compose.yml`) and set:

| Key | Required | Description |
| --- | --- | --- |
| `LOCAL_API_KEY` | Optional | If set, backend requires `X-API-Key` or Bearer token for `/api/v1/*` |

Compose defaults already include:
1. `DATABASE_URL=sqlite:///./data/beebeebrain.db`
2. `DB_AUTO_INIT=true` and `DB_AUTO_SEED=true`
3. `CORS_ALLOW_ORIGINS=http://localhost:5173,http://127.0.0.1:5173`

## 4. One-Command Startup

From repository root:

```bash
docker compose up -d --build
```

Expected exposed ports:
1. Frontend: `http://127.0.0.1:5173`
2. Backend API: `http://127.0.0.1:8000`

## 5. Health Checks

1. Backend health:
   - `curl http://127.0.0.1:8000/healthz`
2. Backend ready:
   - `curl http://127.0.0.1:8000/readyz`
3. OpenAPI:
   - `curl http://127.0.0.1:8000/openapi.json`
4. Frontend:
   - `curl -I http://127.0.0.1:5173`

## 6. Logs and Diagnostics

1. All service logs:
   - `docker compose logs -f`
2. Backend only:
   - `docker compose logs -f backend`
3. Frontend only:
   - `docker compose logs -f frontend`

## 7. Stop and Cleanup

1. Stop services:
   - `docker compose down`
2. Stop and remove volumes (destructive):
   - `docker compose down -v`

## 8. Data Persistence

Named volumes:
1. `backend_data`: SQLite database under `/app/data`
2. `workspace_data`: workspace content under `/workspace`

Backup example:

```bash
docker run --rm -v beebeebrain-mvp_backend_data:/from -v "$PWD":/to alpine \
  sh -c "cd /from && tar czf /to/backend_data_backup.tgz ."
```
