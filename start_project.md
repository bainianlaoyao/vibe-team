# BeeBeeBrain Quick Start (AI-Readable)

This document is a deterministic startup playbook for a fresh clone.
Goal: quickly configure environment and start backend + frontend correctly.

## 0. Preconditions

- OS: Windows (PowerShell examples below).  
- Installed:
  - `git`
  - `Node.js >= 20`
  - `npm`
  - `uv` (Python package manager)

## 1. Clone And Enter Repo

```powershell
git clone <YOUR_REPO_URL> beebeebrain
cd beebeebrain
```

## 2. Backend Setup (must use uv)

```powershell
cd backend
uv sync --dev
cd ..
```

## 3. Frontend Setup

```powershell
cd frontend
npm ci
cd ..
```

## 4. Start Backend

Use repo root script (recommended on Windows):

```powershell
.\start-backend.bat
```

Expected:
- backend listens on `http://127.0.0.1:8000`
- `PROJECT_ROOT` is set to `<repo>\play_ground`

Health check in another terminal:

```powershell
curl http://127.0.0.1:8000/healthz
```

Expected JSON contains healthy status.

## 5. Start Frontend

Use repo root script:

```powershell
.\start-frontend.bat
```

Expected:
- frontend listens on `http://localhost:5173`
- frontend API base is `http://127.0.0.1:8000/api/v1`

## 6. Verify Frontend Project Binding

Frontend default project id is controlled by:

- `frontend/.env.development`
- key: `VITE_PROJECT_ID`

For fresh DB, this is usually `1`.

Open and verify:

```powershell
Get-Content frontend/.env.development
```

If you need to switch project:

```powershell
(Get-Content frontend/.env.development) -replace 'VITE_PROJECT_ID=\d+','VITE_PROJECT_ID=1' | Set-Content frontend/.env.development
```

Then restart frontend.

## 7. Verify Claude Working Directory Is play_ground

Runtime now prefers backend `PROJECT_ROOT`.  
Backend script sets:

- `PROJECT_ROOT=<repo>\play_ground`

So Claude cwd should resolve to `play_ground`.

If conversation output still shows wrong cwd, do this:

1. Stop backend.
2. Ensure you start backend with `.\start-backend.bat` (not ad-hoc command without `PROJECT_ROOT`).
3. Start a new conversation (old conversation history may still show old cwd messages).

## 8. Fast Recovery (if state is messy)

If DB has stale project mappings, reset local DB under `play_ground`:

```powershell
if (Test-Path .\play_ground\.beebeebrain\beebeebrain.db) { Remove-Item .\play_ground\.beebeebrain\beebeebrain.db -Force }
```

Then restart backend with `.\start-backend.bat`.

## 9. Optional Quality Check

```powershell
cd backend
uv run ruff check .
uv run black --check .
uv run mypy app tests
uv run pytest
cd ..
```

---

## Minimal Two-Terminal Routine

Terminal A:

```powershell
cd <repo>
.\start-backend.bat
```

Terminal B:

```powershell
cd <repo>
.\start-frontend.bat
```

Open `http://localhost:5173`.
