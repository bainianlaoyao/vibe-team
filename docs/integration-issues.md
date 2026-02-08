# Phase 8 Integration Issues

Date: 2026-02-07  
Scope: Frontend (`frontend/`) and backend (`backend/`) contract alignment for MVP pages.

## Summary

1. Total issues tracked: 8
2. Blocking issues closed: 8
3. Remaining blocking issues: 0

## Issue Register

| ID | Module | Symptom | Root Cause | Fix | Status |
| --- | --- | --- | --- | --- | --- |
| INT-001 | Dashboard | `GET /tasks/stats` and `GET /updates` missing | Backend lacked page-level aggregation APIs | Added `backend/app/api/dashboard.py` and router registration in `backend/app/main.py` | Closed (2026-02-07) |
| INT-002 | Inbox | `PATCH /inbox/{id}/read` not available | Inbox API only supported close action | Added read endpoint and `is_read` support in `backend/app/api/inbox.py` | Closed (2026-02-07) |
| INT-003 | Agents | No health endpoint for table view | Agent list API had no runtime health aggregate | Added `GET /agents/{agent_id}/health` in `backend/app/api/agents.py` | Closed (2026-02-07) |
| INT-004 | Files | Frontend file tree and permissions could not persist | Backend lacked file tree, metadata, and permission endpoints | Added `backend/app/api/files.py` with tree/content/permission APIs and workspace-level permission store | Closed (2026-02-07) |
| INT-005 | Roles | Roles page had no backend CRUD | Backend had no role persistence endpoint | Added `backend/app/api/roles.py` with JSON-backed CRUD storage | Closed (2026-02-07) |
| INT-006 | API Usage | Usage page had no budget/timeline/error APIs | Missing dashboard usage aggregate endpoints | Added `backend/app/api/usage.py` and usage router registration | Closed (2026-02-07) |
| INT-007 | CORS | Browser preflight failed between frontend and backend | Backend middleware lacked CORS configuration | Added `CORSMiddleware` in `backend/app/main.py` and CORS settings in `backend/app/core/config.py` | Closed (2026-02-07) |
| INT-008 | Frontend data layer | Views still used mock data and contracts diverged | Missing API service/store abstraction and WS lifecycle | Added `frontend/src/services/api.ts`, `frontend/src/services/websocket.ts`, and Pinia stores for agents/tasks/inbox/conversations/usage/files/roles | Closed (2026-02-07) |

## Validation Evidence

1. Backend integration regression: `backend/tests/test_phase8_integration_api.py`
2. API E2E suite: `backend/tests/e2e/`
3. Browser E2E happy path: `frontend/tests/e2e_browser/happy-path.spec.ts`
4. OpenAPI route checks include new endpoints and CORS preflight assertions.

## Remaining Risks

1. Roles and file permission stores are workspace JSON files, suitable for MVP single-node deployment only.
2. Chat WebSocket happy path is covered; large-scale concurrent sessions are not yet stress tested.
