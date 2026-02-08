# Phase 5 Recovery Runbook & SOP

## 1. Scope

This runbook covers three high-frequency operational incidents introduced in Phase 5:

1. LLM timeout and retry storms
2. SQLite lock contention (`database is locked`)
3. File permission failures in local workspace

All procedures assume backend root is `backend/` and runtime is managed with `uv`.

## 2. Fast Triage Checklist

1. Confirm service health: `uv run python -c "import httpx; print(httpx.get('http://127.0.0.1:8000/healthz').status_code)"`
2. Check recent alerts: `GET /api/v1/events/stream?replay_last=50`
3. Check open inbox incidents: `GET /api/v1/inbox?status=open`
4. Query run logs for affected run/task:
   - `GET /api/v1/logs?run_id=<RUN_ID>`
   - `GET /api/v1/logs?task_id=<TASK_ID>`
5. Capture current DB snapshot before any destructive action:
   - PowerShell: `Copy-Item .\\beebeebrain.db .\\beebeebrain.db.pre_recovery.bak -Force`

## 3. Incident SOP

### 3.1 LLM Timeout / Retry Scheduled Growth

Symptoms:
- `task_runs.run_status=retry_scheduled` grows quickly
- `alert.raised` with timeout-related code

Actions:
1. Verify provider availability and key validity.
2. Reduce blast radius:
   - Pause affected tasks: `POST /api/v1/tasks/{id}/pause`
3. Collect evidence:
   - `/api/v1/logs?run_id=<RUN_ID>`
   - `/api/v1/metrics/runs-summary`
4. Resume controlled subset:
   - `POST /api/v1/tasks/{id}/resume`
5. If provider outage persists, keep tasks blocked and create operator note in inbox.

### 3.2 SQLite Lock Contention

Symptoms:
- write operations fail intermittently
- lock-related exceptions in runtime/api logs

Actions:
1. Stop high-frequency write paths temporarily (pause batch commands).
2. Ensure only one backend process writes to the same SQLite file.
3. Restart backend process.
4. Re-run a single representative write request.
5. If still locked:
   - backup DB
   - perform planned rollback (see section 4)
   - restart and revalidate `/healthz`, `/readyz`.

### 3.3 File Permission Errors

Symptoms:
- file read/write denied in workspace
- security/runtime logs contain permission exceptions

Actions:
1. Confirm target path and ownership/ACL.
2. Ensure service process account has read/write permissions for worktree.
3. Retry operation on a minimal file path.
4. If still denied, redirect task to `request_input` with required manual intervention.

## 4. Rollback and Backup

Primary script:
- `backend/scripts/rollback_with_backup.ps1`
- `backend/scripts/rollback_with_backup.sh`

Default behavior:
1. backup SQLite database with timestamp
2. run `uv run alembic downgrade -1`
3. print backup location and downgrade result

## 5. Post-Incident Validation

1. `uv run ruff check .`
2. `uv run mypy app tests`
3. `uv run pytest`
4. Verify:
   - `/api/v1/metrics/usage-daily`
   - `/api/v1/metrics/runs-summary`
   - `/api/v1/inbox?status=open`
   - `/api/v1/events/stream?replay_last=20`
