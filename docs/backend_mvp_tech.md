# BeeBeeBrain Backend MVP 技术设计（详细版）

本文基于以下文档收敛而来：
- `docs/product_design_decisions.md`
- `docs/technical_feasibility.md`
- 当前 MVP 决策：不引入 RAG，Agent 通过工具自主搜索项目知识。

## 1. 目标与边界

### 1.1 MVP 目标
1. 支持单项目内多 Agent 并行执行任务，并提供可干预的状态机。
2. 支持任务流转：待办 -> 进行中 -> 待审查 -> 已完成/失败/阻塞。
3. 支持 Agent 对本地知识库的自主探索（列目录、读文件、关键字搜索）。
4. 支持收件箱机制（仅处理“等待用户输入”和“任务完成通知”）。
5. 支持基础观测能力（日志、事件流、API 使用统计、卡死检测）。

### 1.2 MVP 非目标
1. 不做向量检索与 RAG。
2. 不做分布式微服务部署（先单进程/单机）。
3. 不做复杂权限系统（先单用户本地安全边界）。
4. 不做任意 DSL 工作流可视化编译（先以 Python 编排为主）。

## 2. 架构原则

1. 单进程部署，分层设计：MVP 用一个 Python 服务进程，内部严格模块化，后续可拆分。
2. SQLite + 文件系统双存储：结构化状态入库，原始知识与产物留在文件系统。
3. 事件优先：任务状态变化、Agent 输出、收件箱创建/关闭都以事件形式记录，支持追溯。
4. 可恢复执行：每次运行有 `run_id`，失败后可基于持久化状态重试。
5. 先可观测再扩展：关键路径必须有日志、指标和告警点，避免“黑盒 Agent”。

## 2.5 项目现有知识与关键概念（避免重复搜索）

1. 事件系统（Events）
- 事件落库：`events` 表字段含 `event_type`、`payload_json`、`created_at`、`trace_id`。
- 事件流：`GET /api/v1/events/stream`（SSE），支持 `Last-Event-ID` 断线续传与 `replay_last` 回放。
- 事件类型：
  - `task.status.changed`（任务状态变更）
  - `run.status.changed`（运行状态变更）
  - `run.log`（运行日志增量）
  - `alert.raised`（告警）
  - `tool.command.audit`、`task.intervention.audit`（审计类）
  - `inbox.item.created`、`inbox.item.closed`、`user.input.submitted`（收件箱链路）

2. Trace 与 Run 关联
- `trace_id`：API 传入或后端生成，写入 `events.trace_id`，用于跨事件关联。
- `run_id`：每次任务运行唯一主键，贯穿运行生命周期与事件。

3. 状态机核心概念
- 任务状态：`todo` / `running` / `review` / `done` / `blocked` / `failed` / `cancelled`。
- 运行状态：`queued` / `running` / `retry_scheduled` / `interrupted` / `succeeded` / `failed` / `cancelled`。

4. 运行恢复与幂等
- `task_runs` 使用 `idempotency_key` 防重执行。
- 重启恢复：中断运行标记为 `interrupted`，到期重试转为 `running`。
- 重试策略：指数退避（含 `next_retry_at`）。

5. LLM 适配与成本统计
- 首期模型：Claude Code（`claude-agent-sdk`）。
- 使用统计：`task_runs` 记录 token/cost，`api_usage_daily` 汇总日维度成本。

6. 安全边界
- 文件安全：`SecureFileGateway` 限制 root_path、拦截敏感文件、限制读取大小与超时。
- 脱敏：统一对 key/token/password 等敏感字段做日志脱敏。

7. CLI 工具回写
- 工具：`finish_task` / `block_task` / `request_input` 通过 HTTP 命令 API 回写状态。
- 幂等：按 `tool + task_id + idempotency_key` 去重。

8. tasks.md 视图同步
- `TasksMarkdownExporter` 负责生成根目录 `tasks.md` 快照。
- 通过配置 `TASKS_MD_SYNC_ENABLED` / `TASKS_MD_OUTPUT_PATH` 控制同步。

## 3. 逻辑架构与职责

### 3.1 模块划分
1. API 网关层（FastAPI）
- 对外暴露 REST/WebSocket。
- 做参数校验、错误映射、请求级鉴权（MVP 可为本地 token）。

2. 任务与编排层（Orchestration）
- 维护任务状态机与依赖判定。
- 触发执行、暂停、重试、人工干预。

3. Agent 执行层（Execution Pool）
- 封装 LLM provider 调用（当前首期接入 Claude Code，预留 OpenAI/Anthropic 扩展位）。
- 处理 Tool Calling 循环、超时、重试、token/成本统计。

4. 文档与知识工具层（Document Tools）
- 文件系统安全访问（路径校验、根目录白名单）。
- 目录列举、文件读取、关键字搜索。

5. 收件箱与反馈层（Inbox/Review）
- 归集“等待用户输入”和“任务完成通知”项。
- 用户通过关闭收件箱项提交输入，回写任务后续动作。

6. 监控与审计层（Observability）
- 结构化日志、运行指标、事件审计流水。

### 3.2 MVP 运行拓扑

```text
Frontend (Vue)  <->  FastAPI (REST/WebSocket)
                         |
                         +-- Orchestrator (asyncio)
                         |      |
                         |      +-- Execution Pool (LLM + Tool Loop)
                         |      +-- Task State Machine
                         |
                         +-- Document Service (safe file ops)
                         +-- Inbox Service
                         +-- Monitoring Service
                         |
                         +-- SQLite (state/events/metrics)
                         +-- Local FS (docs/code/artifacts/tasks.md export)
```

## 4. 后端项目结构建议

```text
backend/
  pyproject.toml
  app/
    main.py
    api/
      v1/
        routes_agents.py
        routes_tasks.py
        routes_runs.py
        routes_inbox.py
        routes_docs.py
        routes_events.py
    core/
      config.py
      logging.py
      security.py
      constants.py
    domain/
      models.py
      enums.py
      schemas.py
    infra/
      db.py
      repositories/
      event_bus.py
      storage/
        safe_fs.py
    services/
      orchestrator.py
      execution_engine.py
      task_service.py
      inbox_service.py
      document_service.py
      metrics_service.py
    agents/
      context_builder.py
      llm_clients/
        openai_client.py
        anthropic_client.py
      tools/
        list_path_tool.py
        read_file_tool.py
        search_project_files_tool.py
    workers/
      watchdog.py
      scheduler.py
    exporters/
      tasks_md_exporter.py
  tests/
    unit/
    integration/
    e2e/
```

## 5. 数据模型设计（SQLite + SQLModel）

实现落地（P1-C，2026-02-06）：
1. 后端目录新增 `app/db/engine.py` 与 `app/db/session.py`，统一 SQLite 连接和 session 生命周期。
2. 首版表结构已在 `app/db/models.py` 与 Alembic revision 中对齐：`projects`、`agents`、`tasks`、`events`。
3. 提供 `uv run python -m app.db.cli init` 初始化命令（建库目录 + 迁移 + 种子）。

实现落地（P2-A，2026-02-06）：
1. 扩展领域表结构并新增 revision：`task_dependencies`、`task_runs`、`inbox_items`、`documents`、`comments`、`api_usage_daily`。
2. 在可变实体引入 `version` 乐观锁字段，并补齐唯一索引与检查约束（含依赖去重、文档路径去重、usage 维度去重）。
3. 新增 repository 层：`TaskRepository`、`InboxRepository`、`DocumentRepository`，统一分页、过滤与乐观锁更新。
4. 回归测试覆盖 schema、约束、唯一索引与 repository 行为。

实现落地（P2-D，2026-02-06）：
1. 新增事件 schema：`task.status.changed`、`run.log`、`alert.raised`。
2. 新增 `GET /api/v1/events/stream` SSE 通道，支持 `Last-Event-ID` 断线重连。
3. 新增 `replay_last` 参数用于最近事件回放，支持冷启动补历史。
4. 新增 `backend/scripts/events_stream_stress.py` 高频推送压测脚本。

实现落地（P3-A，2026-02-06）：
1. 新增任务状态机模块，统一约束 `todo/running/review/done/blocked/failed/cancelled` 的迁移合法性。
2. 新增调度器模块，按 `priority` 升序并结合 `parent_task_id` 与 `task_dependencies` 判定可执行任务。
3. 新增任务命令：`pause/resume/retry/cancel`，通过状态机进行命令合法性校验。
4. 任务状态迁移事件统一写入 `events`，每条迁移事件强制携带 `trace_id`（请求传入或后端生成）。
5. 补齐非法迁移与非法命令回归测试。

实现落地（P3-D，2026-02-06）：
1. 补齐人工干预接口：`POST /api/v1/tasks/{task_id}/pause|resume|retry`，支持 `expected_version` 乐观锁参数。
2. 新增批量干预接口：`POST /api/v1/tasks/broadcast/{command}`，默认按 `running` 状态筛选并可按 `task_ids/status` 定向广播。
3. 新增干预审计事件 `task.intervention.audit`，覆盖成功、拒绝与版本冲突三类结果。
4. 新增并发冲突回归测试，验证 stale `expected_version` 返回 `409 TASK_VERSION_CONFLICT` 且写入审计日志。

实现落地（P3-B，2026-02-06）：
1. 新增统一 LLM 契约层：`app/llm/contracts.py`（`LLMRequest/LLMResponse/LLMUsage/LLMToolCall`）与 `app/llm/errors.py`（统一错误码与 retryable 标记）。
2. 新增 Claude Code 适配器：`app/llm/providers/claude_code.py`，基于 `claude-agent-sdk` 统一映射请求、响应、tool call 与 provider 错误。
3. 新增 Claude 配置加载器：`app/llm/providers/claude_settings.py`，默认自动读取用户目录 `~/.claude/settings.json` 的 `env` 段，并允许环境变量覆盖。
4. 新增 usage 落库服务：`app/llm/usage.py`，将 token/cost 聚合写入 `task_runs` 与 `api_usage_daily`。
5. 新增回归测试：`tests/test_llm_claude_adapter.py`、`tests/test_llm_usage.py`、`tests/test_llm_factory.py`，覆盖 provider 故障注入、settings 自动读取、tool call 对齐与 usage 累加。

实现落地（P3-C，2026-02-07）：
1. 新增运行编排服务：`app/runtime/execution.py`（`TaskRunRuntimeService`），打通 run 创建、执行、失败标记、重试调度与完成收敛。
2. 新增重试策略对象：`RuntimeRetryPolicy`，对超时与 retryable provider 错误采用指数退避并写入 `next_retry_at`。
3. 幂等执行统一使用 `idempotency_key`，同一请求重复触发时复用已有 `task_runs` 记录并避免重复执行。
4. 新增重启恢复流程：`interrupt_inflight_runs`（`running -> interrupted`）与 `resume_due_retries`（到期 `retry_scheduled -> running`）。
5. 新增运行恢复测试：`tests/test_runtime_execution.py`，覆盖成功幂等、超时退避、重启恢复与异常恢复端到端场景。
6. 新增运行入口 API：`POST /api/v1/tasks/{task_id}/run`，自动完成任务进入 `running`、run 执行、结果态映射（`review/failed/blocked/cancelled`）与状态事件写入。

实现落地（P4-A，2026-02-07）：
1. 新增安全文件网关：`app/security/file_guard.py`（`SecureFileGateway`），固定 `root_path` 并基于 `resolve/relative_to` 拦截越权路径。
2. 新增敏感文件策略：默认阻断 `.env`、私钥后缀（`.pem/.key/.p12/.pfx`）和高风险命名文件读取。
3. 新增资源治理：单次读取字节上限、文件扩展名白名单、线程超时保护（防止长耗时读操作占用执行线程）。
4. 新增日志脱敏器：`app/security/redaction.py`，对 `api_key/access_token/secret/password/bearer token` 进行统一脱敏。
5. 运行错误信息与 API 错误响应接入脱敏逻辑，避免在 `task_runs.error_message` 与错误响应中落出密钥明文。
6. 新增安全边界回归：`tests/test_security_file_guard.py` 与 `tests/test_security_redaction.py`，覆盖越权、敏感文件、配额超限、超时与脱敏场景。

实现落地（P4-B，2026-02-07）：
1. 新增上下文构建器：`app/agents/context_builder.py`（`PromptContextBuilder`），聚合任务元数据、依赖摘要、`docs/` 规则、索引文档与 `tasks.md` 快照。
2. 新增模板引擎：`PromptTemplateEngine`，支持按 `phase/task_type` 选择模板并按 `phase__type -> phase__default -> default__type -> default__default` 回退。
3. 新增 Token Budget 策略：按任务优先级映射默认预算并支持请求级覆盖。
4. 新增预算裁剪策略：优先裁剪 `tasks.md`、文档与依赖摘要，必要时进行全提示硬截断，保证输出不超过预算。
5. 新增 Prompt 模板目录：`app/agents/prompt_templates/`（首批 `default__default.tmpl`、`phase4__default.tmpl`）。
6. 新增上下文回归：`tests/test_context_builder.py`，校验关键约束包含、模板回退与预算裁剪上限。

实现落地（P4-C，2026-02-07）：
1. 新增命令 API：`app/api/tools.py`，提供 `POST /api/v1/tools/finish_task|block_task|request_input`。
2. 工具写回统一走 HTTP 命令 API，不允许工具层直连数据库更新任务状态。
3. 新增幂等检查：按 `tool + task_id + idempotency_key` 回放既有成功结果，避免重复写操作。
4. 新增工具审计事件：`tool.command.audit`，记录 `outcome/applied|rejected`、错误码与响应快照。
5. 新增用户输入请求闭环：`request_input` 自动创建 `inbox_items(item_type=await_user_input)` 并写 `inbox.item.created` 事件。
6. 新增 CLI 工具封装：`app/tools/cli_tools.py`，以 HTTP 客户端形式暴露 `finish_task/block_task/request_input`。
7. 新增集成测试：`tests/test_cli_tools.py`，模拟 CLI 调用命令 API 并校验状态写回、幂等命中与审计事件。

实现落地（P4-D，2026-02-07）：
1. 新增计划视图导出器：`app/exporters/tasks_md_exporter.py`（`TasksMarkdownExporter`），基于 `tasks` 表渲染 Markdown 快照。
2. 导出内容包含项目维度状态汇总与任务明细表，作为人类可读视图供审阅与追踪。
3. 新增同步开关：`TASKS_MD_SYNC_ENABLED` 与输出路径 `TASKS_MD_OUTPUT_PATH`（`app/core/config.py`）。
4. 状态同步机制接入 `tasks` 与 `tools` 的状态写路径，状态变化提交后自动触发导出刷新。
5. 新增导出一致性测试：`tests/test_tasks_md_exporter.py`，覆盖 DB 快照渲染与 API 状态变更触发文件刷新。

实现落地（P5-A，2026-02-07）：
1. 新增结构化日志模块：`app/core/logging.py`，基于 `structlog + contextvars` 输出 JSON/Console 日志并统一 `trace_id/run_id/task_id/agent_id` 上下文字段。
2. FastAPI 接入 `TraceContextMiddleware`：自动透传或生成 `X-Trace-ID`，请求日志统一记录 `request.received/request.completed/request.failed`。
3. 增加日志分层 logger：`bbb.api` / `bbb.orchestration` / `bbb.runtime` / `bbb.tools` / `bbb.security`，关键路径补齐结构化日志字段。
4. 新增日志查询接口：`GET /api/v1/logs`（`app/api/logs.py`），支持按 `project_id/task_id/run_id/level` 过滤 `run.log` 事件。
5. 新增日志回归：`tests/test_logs_api.py`，覆盖过滤查询、`X-Trace-ID` 透传/生成与脏 payload 容错。

实现落地（P5-B，2026-02-07）：
1. 新增指标接口：`app/api/metrics.py`，提供 `GET /api/v1/metrics/usage-daily` 与 `GET /api/v1/metrics/runs-summary`。
2. `usage-daily` 支持按 `provider/model/date` 过滤并输出请求数、token 与成本汇总。
3. `runs-summary` 基于 `task_runs` 聚合运行状态分布、总 token/cost 与平均/最大耗时。
4. 成本阈值告警接入 `app/llm/usage.py`：命中 `COST_ALERT_THRESHOLD_USD` 后写 `alert.raised` 并创建 `inbox_items(await_user_input)`。
5. 新增回归测试：`tests/test_metrics_api.py` 与 `tests/test_llm_usage.py`，覆盖聚合正确性与成本告警去重。

实现落地（P5-C，2026-02-07）：
1. 新增卡死检测器：`app/runtime/stuck_detector.py`（`StuckRunDetector`），覆盖无输出超时、重复动作、高错误率三类规则。
2. 检测命中后自动写 `alert.raised`，并创建 `inbox_items(item_type=await_user_input)`，附带诊断信息与去重 `source_id`。
3. 防重复告警策略：同一 `run_id + alert_kind` 在未关闭前仅创建一个开放收件箱项。
4. FastAPI `lifespan` 接入后台轮询协程：`run_stuck_detector_loop`，默认每 `60s` 执行一次检测。
5. 新增配置项：`STUCK_IDLE_TIMEOUT_S`、`STUCK_REPEAT_THRESHOLD`、`STUCK_ERROR_RATE_THRESHOLD`、`STUCK_SCAN_INTERVAL_S`。
6. 新增回归测试：`tests/test_stuck_detector.py`，覆盖超时、重复动作、高错误率与误报抑制场景。

实现落地（P5-D，2026-02-07）：
1. 新增安全审计模块：`app/security/audit.py`，统一 `security.audit.allowed|denied` 事件与字段契约（`actor/action/resource/outcome/reason/ip/metadata`）。
2. 关键命令路径接入审计：`app/api/tasks.py` 与 `app/api/tools.py` 在允许/拒绝场景写入安全审计事件。
3. 扩展故障注入模式：`FailureMode` 新增 `database_lock` 与 `file_permission_error`，并补齐异常类型与单测。
4. 输出运维文档：`docs/runbook/phase5_recovery_sop.md`，覆盖 LLM 超时、DB 锁、文件权限错误的排障与恢复流程。
5. 固化回滚脚本：`backend/scripts/rollback_with_backup.ps1` 与 `backend/scripts/rollback_with_backup.sh`，默认执行“先备份再 Alembic downgrade”。

实现落地（P6-A，2026-02-07）：
1. 新增主验证器脚本：`backend/scripts/api_probe.py`，覆盖 `health/ready`、`agents/tasks` CRUD、`run/pause/resume/retry/cancel`、`inbox close(user_input)`、`events` 回放与流式续传。
2. 验证器采用隔离测试环境：临时 SQLite + 临时工作目录 + `TestClient`，并通过 patch `create_llm_client` 消除外部 LLM 依赖。
3. 输出结构化报告：默认写入 `docs/reports/phase6/api_probe_report.json` 与 `docs/reports/phase6/api_probe_report.md`，包含通过率、时延与失败样例。
4. 增加一键入口：`backend/Makefile` 新增 `api-probe` 目标（`uv run python scripts/api_probe.py --fail-on-error`）。
5. CI 新增冒烟作业：`.github/workflows/backend-quality.yml` 增加 `api-smoke` job，执行验证器并上传报告 artifact。

实现落地（P6-B，2026-02-07）：
1. 新增失败恢复回归探针：`backend/scripts/failure_recovery_probe.py`，覆盖 `timeout`、`transient_error`、重复请求幂等、重启恢复四类场景矩阵。
2. 回归探针验证幂等键防重、指数退避重试、`resume_due_retries` 与 `recover_after_restart` 行为一致性。
3. 统一报告格式并归档：默认写入 `docs/reports/phase6/failure_recovery_report.json` 与 `docs/reports/phase6/failure_recovery_report.md`。
4. 增加冻结前必跑入口：`backend/Makefile` 新增 `failure-recovery-probe` 与 `freeze-gate` 目标。
5. CI 新增回归作业：`.github/workflows/backend-quality.yml` 增加 `failure-recovery-regression` job，执行探针并上传 artifact。

实现落地（P6-C，2026-02-07）：
1. 新增极简调试面板：`GET /debug/panel`（`backend/app/api/debug.py` + `backend/app/static/debug_panel.html`），支持任务动作、`request_input`、收件箱关闭与事件流查看。
2. 新增最小鉴权中间件：`backend/app/core/auth.py`，当配置 `LOCAL_API_KEY` 时，对 `/api/v1/*` 请求校验 `X-API-Key` 或 `Authorization: Bearer`。
3. 调试面板支持环境配置（`Base URL/Project ID/Auth Mode/Token`）并提供“一键验收链路”按钮，便于联调复现。
4. 增加鉴权与面板回归：`backend/tests/test_local_api_key_auth.py`，覆盖未授权拒绝、两种鉴权头放行、面板访问可用性。
5. 面板定位明确为验收工具：在 `backend/README.md` 中标注“非正式产品 UI”，避免误作为产品界面演进。
6. 联调记录归档：`docs/reports/phase6/panel_integration_notes.md`，沉淀链路执行结果与非阻塞问题。

实现落地（P6-C 修复，2026-02-07）：
1. 新增启动期数据库自动初始化兜底：`backend/app/main.py` 在开发环境默认执行迁移与可选种子，避免调试面板首次运行因缺表报错。
2. 新增配置项：`DB_AUTO_INIT`、`DB_AUTO_SEED`（`backend/app/core/config.py`），默认仅 `APP_ENV=development` 开启，测试与生产默认关闭。
3. 新增回归：`backend/tests/test_health.py` 验证开发环境启动后数据库表自动可用。

### 5.1 核心实体
1. `projects`
- `id`, `name`, `root_path`, `created_at`, `updated_at`, `version`

2. `agents`
- `id`, `project_id`, `name`, `role`, `model_provider`, `model_name`, `initial_persona_prompt`, `enabled_tools_json`, `status`, `version`

3. `tasks`
- `id`, `project_id`, `title`, `description`, `status`, `priority`, `assignee_agent_id`, `parent_task_id`, `created_at`, `updated_at`, `due_at`, `version`

4. `task_dependencies`
- `id`, `task_id`, `depends_on_task_id`, `dependency_type`（finish_to_start 等）

5. `task_runs`
- `id`, `task_id`, `agent_id`, `run_status`, `attempt`, `idempotency_key`, `started_at`, `ended_at`, `next_retry_at`, `error_code`, `error_message`, `token_in`, `token_out`, `cost_usd`, `version`

6. `inbox_items`
- `id`, `project_id`, `source_type`, `source_id`, `item_type`（await_user_input/task_completed）, `title`, `content`, `status`（open/closed）, `created_at`, `resolved_at`, `resolver`, `version`

7. `documents`
- `id`, `project_id`, `path`, `title`, `doc_type`, `is_mandatory`, `tags_json`, `version`, `updated_at`

8. `comments`
- `id`, `document_id`, `task_id`, `anchor`, `comment_text`, `author`, `status`, `created_at`, `version`

9. `events`
- `id`, `project_id`, `event_type`, `payload_json`, `created_at`, `trace_id`

10. `api_usage_daily`
- `id`, `provider`, `model_name`, `date`, `request_count`, `token_in`, `token_out`, `cost_usd`

### 5.2 状态机约束（tasks.status）
1. `todo`
2. `running`
3. `review`
4. `done`
5. `blocked`
6. `failed`
7. `cancelled`

允许迁移由编排层统一控制，不允许前端直接跨级写状态。
状态迁移（P3-A）：
1. `todo` -> `running/blocked/cancelled`
2. `running` -> `review/blocked/failed/cancelled`
3. `review` -> `running/done/blocked/failed/cancelled`
4. `blocked` -> `todo/running/cancelled`
5. `failed` -> `todo/running/cancelled`
6. `cancelled` -> `todo`（仅用于重试）
7. `done` -> （终态，不允许迁移）

### 5.3 运行状态约束（task_runs.run_status）
1. `queued`
2. `running`
3. `retry_scheduled`
4. `interrupted`
5. `succeeded`
6. `failed`
7. `cancelled`

运行状态迁移（P3-C0）：
1. `queued` -> `running/cancelled`
2. `running` -> `succeeded/failed/retry_scheduled/cancelled/interrupted`
3. `retry_scheduled` -> `running/cancelled`
4. `interrupted` -> `running/failed/cancelled`
5. `succeeded/failed/cancelled` -> 终态

字段契约（P3-C0）：
1. `attempt >= 1`，且 `(task_id, attempt)` 唯一，按同一任务重试次数递增。
2. `idempotency_key` 全局唯一且非空，用于幂等防重创建 run。
3. `next_retry_at` 仅允许在 `run_status=retry_scheduled` 时非空，其他状态必须为空。

## 6. API 设计（MVP）

### 6.1 Agent 管理
1. `GET /api/v1/agents`
2. `POST /api/v1/agents`
3. `GET /api/v1/agents/{agent_id}`
4. `PATCH /api/v1/agents/{agent_id}`
5. `DELETE /api/v1/agents/{agent_id}`

### 6.2 任务管理
1. `GET /api/v1/tasks`
2. `POST /api/v1/tasks`
3. `GET /api/v1/tasks/{task_id}`
4. `PATCH /api/v1/tasks/{task_id}`
5. `DELETE /api/v1/tasks/{task_id}`
6. `POST /api/v1/tasks/{task_id}/run`（P3）
7. `POST /api/v1/tasks/{task_id}/pause`（P3）
8. `POST /api/v1/tasks/{task_id}/resume`（P3）
9. `POST /api/v1/tasks/{task_id}/retry`（P3）
10. `POST /api/v1/tasks/{task_id}/cancel`（P3）

### 6.3 收件箱与用户确认
1. `GET /api/v1/inbox`
2. `POST /api/v1/inbox/{item_id}/close`（支持 `user_input`）
3. `await_user_input` 项关闭时必须提供 `user_input`，`task_completed` 项可直接关闭。

### 6.4 文档与知识
1. `GET /api/v1/docs`
2. `POST /api/v1/docs/index`
3. `POST /api/v1/tools/list-path`
4. `POST /api/v1/tools/read-file`
5. `POST /api/v1/tools/search-files`

### 6.5 事件流
1. `POST /api/v1/events`（写入结构化事件，当前支持三类）：
- `task.status.changed`：任务状态变更。
- `run.log`：运行日志增量。
- `alert.raised`：告警事件。
2. `GET /api/v1/events/stream`（SSE）：
- 支持 `Last-Event-ID` 或 `last_event_id` 续传。
- 支持 `replay_last` 最近事件回放。
- 支持心跳注释帧与批量抓取参数（`batch_size`、`poll_interval_ms`）。
- 支持 `max_events`（测试/压测场景下自动结束流）。
3. `GET /api/v1/runs/{run_id}/logs`（P3）。

### 6.6 统一错误响应
1. 全部错误接口统一返回：
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request validation failed.",
    "issues": [
      {
        "field": "body.title",
        "message": "String should have at least 1 character"
      }
    ]
  }
}
```
2. 典型错误码：`VALIDATION_ERROR`、`PROJECT_NOT_FOUND`、`AGENT_NOT_FOUND`、`TASK_NOT_FOUND`、`INVALID_ASSIGNEE`、`INVALID_TASK_DEPENDENCY`、`TASK_HAS_DEPENDENTS`。

## 7. Agent 上下文与工具调用设计

### 7.1 初始上下文包
1. Agent persona（系统消息）
2. 项目全局规则摘要（如 `project_overview.md`）
3. 当前任务描述、验收标准、依赖任务摘要
4. `tasks.md` 精简视图（只含当前相关任务）

### 7.2 工具调用闭环
1. LLM 返回 tool call。
2. 执行层校验工具与参数（路径、大小、超时）。
3. 调用 document service 获取结果。
4. 将结果作为下一轮上下文继续推理。
5. 达到停止条件（完成、失败、超时、人工中断）。

### 7.3 MVP 工具白名单
1. `list_path_tool(path)`
2. `read_file_tool(path)`
3. `search_project_files_tool(query, types, max_results)`

## 8. 并发模型与调度策略

1. 基础并发：`asyncio` + 有界并发队列（按项目和 Agent 限流）。
2. 任务抢占：MVP 不做抢占式调度，仅支持人工暂停/恢复。
3. 重试策略：指数退避 + 最大重试次数 + 可配置错误白名单。
4. 幂等约束：
- `run_id` 唯一。
- 写操作通过事务和状态版本号防止重复提交。
5. 卡死检测：
- 超时无输出。
- 重复动作哈希命中阈值。
- 连续错误率超过阈值自动生成 `await_user_input` 收件箱项并附带诊断上下文。

## 9. 安全与治理

1. 文件访问安全
- 执行隔离基于 `git worktree + 版本控制`，每次运行只允许访问当前 worktree 根目录。
- 所有路径必须通过 `realpath/commonpath` 校验，拦截 `..` 跳转与符号链接越界。
- 工具默认只读，并限制单次读取大小、文本类型与超时。

2. API 安全
- 本地 token 或 session 鉴权（MVP 最小实现）。
- 关键操作写审计日志（暂停、恢复、重试、手动关闭）。

3. 密钥治理
- API Key 只从环境变量读取，不落库明文。
- 日志脱敏（key、token、用户隐私片段）。

## 10. 观测性设计

1. 日志
- JSON 结构化日志，字段含 `trace_id`, `task_id`, `run_id`, `agent_id`, `event_type`。

2. 指标
- 任务吞吐、平均完成时长、失败率、阻塞率、重试率、token 与成本。

3. 事件审计
- 所有状态变更写 `events` 表，收件箱最小事件为 `inbox.item.created` 与 `inbox.item.closed`（可选 `user.input.submitted`），支持回放与问题复盘。

## 11. 测试与质量门禁

1. 单元测试：状态机迁移、路径校验、工具参数校验、重试策略。
2. 集成测试：API + SQLite + 文件系统 + tool loop。
3. 端到端测试：从建任务到完成/用户输入/干预完整链路。
4. 质量门禁（Phase 1 当前实现）：
- 本地统一入口：`cd backend && make quality`，执行 `ruff + black + mypy + pytest`。
- 提交前钩子：根目录 `.pre-commit-config.yaml` 执行 backend 的 `ruff/black/mypy`。
- CI 流水线：`.github/workflows/backend-quality.yml` 执行 lint + type check + unit test。
- 覆盖率阈值：`pytest --cov-fail-under=70`，并在 CI 上传 `coverage.xml` 报告。

## 12. 演进路线（MVP -> 下一阶段）

1. 执行层扩展为多进程 worker（Celery/RQ）。
2. SQLite 升级为 PostgreSQL（并发与远程部署）。
3. 引入 Git Worktree 隔离执行环境。
4. 引入 Workflow DSL 或 LangGraph 作为编排内核。
5. 在确认信息检索瓶颈后再评估 RAG。

## 13. 与 `tasks.md` 的关系

1. `tasks` 表是系统真实数据源。
2. 根目录 `tasks.md` 由导出器定期或事件触发刷新。
3. 导出格式与本设计的 Phase/并行任务视图一致，便于人类快速审阅。
