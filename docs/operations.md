# Operations Handbook (MVP v0.1.0)

Date: 2026-02-07

## 1. First 7 Days Monitoring Targets

Track these indicators daily after go-live:

| Category | Metric | Target | Source |
| --- | --- | --- | --- |
| Reliability | Task run success rate | >= 95% | `GET /api/v1/metrics/runs-summary` |
| Latency | P95 API latency | <= 1.5s | structured logs (`request.completed`) |
| Errors | 5xx ratio | <= 1% | API logs + alert stream |
| Cost | Daily model cost increase | <= planned budget | `GET /api/v1/metrics/usage-daily` + `GET /api/v1/usage/budget` |
| Realtime | WS reconnect frequency | stable/no bursts | frontend logs + websocket state telemetry |

## 2. On-Call Rules

1. Business hours: one primary on-call owner per day.
2. Response time:
   - P1 (service down/data risk): acknowledge within 15 minutes.
   - P2 (major feature blocked): acknowledge within 30 minutes.
   - P3 (degraded but workaround exists): acknowledge within 4 hours.
3. Escalation:
   - Primary -> backup engineer -> tech lead.

## 3. Alert Response SOP

### 3.1 P1: Backend Unavailable

1. Check `docker compose ps` and container restart loops.
2. Validate `/healthz` and `/readyz`.
3. Capture backend logs (`docker compose logs --tail=200 backend`).
4. If DB-related failure, execute backup-first rollback path (section 4).

### 3.2 P2: High Error Rate or Task Failures

1. Query `GET /api/v1/usage/errors` for latest failure clusters.
2. Query `GET /api/v1/logs?level=error`.
3. Pause impacted tasks using task command APIs when needed.
4. Create an inbox item for manual intervention if automatic retries exceed threshold.

### 3.3 P2: WebSocket Degradation

1. Confirm backend `/ws/conversations/{id}` upgrade path health.
2. Verify frontend proxy config for `/ws/` in `frontend/nginx.conf`.
3. Roll restart frontend container first, backend second if needed.

## 4. Rollback and Backup Strategy

1. Before rollback, back up database volume.
2. Use existing scripts:
   - `backend/scripts/rollback_with_backup.sh`
   - `backend/scripts/rollback_with_backup.ps1`
3. Validate after rollback:
   - `/healthz`, `/readyz`
   - core API smoke (`/api/v1/agents`, `/api/v1/tasks/stats`, `/api/v1/inbox`)

## 5. Daily Operation Checklist

1. Review open inbox incidents: `GET /api/v1/inbox?status=open`.
2. Review usage/cost drift: `GET /api/v1/usage/budget`.
3. Review failed runs and retry backlog.
4. Verify latest backup artifact exists and is restorable.
5. Record findings in daily ops log.
