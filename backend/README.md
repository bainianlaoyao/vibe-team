# BeeBeeBrain Backend

最小可运行后端骨架，基于 FastAPI + SQLModel。

## 目录结构

```text
backend/
  app/
    api/
    core/
    main.py
  scripts/
    start_dev.ps1
    start_dev.sh
  tests/
  pyproject.toml
```

## 初始化

```bash
cd backend
uv sync --dev
```

## 本地运行

```bash
cd backend
uv run uvicorn app.main:app --reload
```

或使用脚本：

```powershell
cd backend
.\scripts\start_dev.ps1
```

## 配置

通过环境变量控制运行参数：

- `APP_ENV`: `development` / `test` / `production`
- `APP_NAME`: 服务名称（默认 `BeeBeeBrain Backend`）
- `HOST`: 绑定地址（默认 `127.0.0.1`）
- `PORT`: 端口（默认 `8000`）
- `DATABASE_URL`: 数据库连接串（默认开发 `sqlite:///./beebeebrain.db`，测试 `sqlite:///./beebeebrain_test.db`）
- `DEBUG`: 调试开关（默认开发/测试 `true`，生产 `false`）
- `TESTING`: 测试模式开关（默认仅 `APP_ENV=test` 为 `true`）
- `TASKS_MD_SYNC_ENABLED`: 是否在任务状态变更后自动刷新任务 Markdown 视图（默认 `false`）
- `TASKS_MD_OUTPUT_PATH`: 导出目标路径（默认 `../tasks.md`）
- `LOG_LEVEL`: 日志级别（默认 `INFO`）
- `LOG_FORMAT`: 日志格式，`json` 或 `console`（默认 `json`）
- `LOG_FILE`: 可选日志文件输出路径（默认不写文件）
- `LOG_DB_ENABLED`: 预留 DB 日志写入开关（默认 `false`）
- `LOG_DB_MIN_LEVEL`: 预留 DB 日志最小级别（默认 `WARNING`）
- `COST_ALERT_THRESHOLD_USD`: 日成本告警阈值（`<=0` 关闭告警，默认 `0`）
- `STUCK_IDLE_TIMEOUT_S`: 无输出超时阈值（秒，默认 `600`）
- `STUCK_REPEAT_THRESHOLD`: 重复动作阈值（0-1，默认 `0.8`）
- `STUCK_ERROR_RATE_THRESHOLD`: 错误率阈值（0-1，默认 `0.6`）
- `STUCK_SCAN_INTERVAL_S`: 卡死检测轮询周期（秒，默认 `60`）

## 数据库初始化与迁移

初始化数据库（创建 SQLite 文件目录、执行 Alembic 迁移、写入种子数据）：

```bash
cd backend
uv run python -m app.db.cli init
```

仅执行迁移：

```bash
cd backend
uv run python -m app.db.cli migrate
```

常用参数：

- `--database-url <url>`：覆盖默认 `DATABASE_URL`
- `--skip-seed`：初始化时跳过种子数据

也可直接使用 Alembic：

```bash
cd backend
uv run alembic upgrade head
```

## 探活接口

- `GET /healthz`
- `GET /readyz`

## 已实现核心 API（`/api/v1`）

- `GET/POST/GET{id}/PATCH{id}/DELETE{id}`: `/agents`
- `GET/POST/GET{id}/PATCH{id}/DELETE{id}`: `/tasks`
- `GET /inbox`（支持 `project_id/item_type/status` 过滤）
- `POST /inbox/{item_id}/close`（支持 `user_input`，`await_user_input` 类型必填）
- `POST /events`（结构化事件写入：`task.status.changed` / `run.log` / `alert.raised`）
- `GET /events/stream`（SSE，支持 `Last-Event-ID` 断线重连与 `replay_last` 回放）
- `GET /logs`（运行日志查询，支持 `project_id/task_id/run_id/level` 过滤）
- `GET /metrics/usage-daily`（按 `provider/model/date` 查询成本与 token 聚合）
- `GET /metrics/runs-summary`（运行状态、耗时、token、成本汇总）
- `POST /tools/finish_task|block_task|request_input`（CLI 工具命令 API，支持 Idempotency Key 与审计）

## 追踪头

- 所有请求默认注入或透传 `X-Trace-ID` 响应头，便于跨日志与事件关联。

## tasks.md 导出

任务状态变更后可自动导出任务视图到 Markdown 文件（默认关闭）：

```bash
cd backend
TASKS_MD_SYNC_ENABLED=true TASKS_MD_OUTPUT_PATH=../tasks.md uv run uvicorn app.main:app --reload
```

## 事件流压测脚本

```bash
cd backend
uv run python scripts/events_stream_stress.py --project-id 1 --total-events 5000
```

常用参数：

- `--producer-concurrency`：并发写入事件请求数
- `--reconnect-every`：每消费 N 条主动断线重连一次（0 表示关闭）
- `--timeout-seconds`：消费等待超时

## API 验证器（Phase 6）

```bash
cd backend
uv run python scripts/api_probe.py --fail-on-error
```

默认输出：

- JSON 报告：`docs/reports/phase6/api_probe_report.json`
- Markdown 报告：`docs/reports/phase6/api_probe_report.md`

## 失败恢复回归（Phase 6）

```bash
cd backend
uv run python scripts/failure_recovery_probe.py --fail-on-error
```

默认输出：

- JSON 报告：`docs/reports/phase6/failure_recovery_report.json`
- Markdown 报告：`docs/reports/phase6/failure_recovery_report.md`

版本冻结前推荐统一执行：

```bash
cd backend
make freeze-gate
```

## 故障恢复与回滚

- Runbook/SOP：`docs/runbook/phase5_recovery_sop.md`
- 回滚脚本（含 DB 备份）：
  - PowerShell: `backend/scripts/rollback_with_backup.ps1`
  - Shell: `backend/scripts/rollback_with_backup.sh`

## 检查与测试

```bash
cd backend
uv run ruff check .
uv run black --check .
uv run mypy app tests
uv run pytest
```

## 统一命令入口（Makefile）

```bash
cd backend
make sync
make quality
```

常用目标：

- `make lint`
- `make format-check`
- `make type-check`
- `make test`
- `make api-probe`
- `make failure-recovery-probe`
- `make freeze-gate`
- `make quality`

## pre-commit

```bash
cd backend
uv run pre-commit install
uv run pre-commit run --all-files
```
