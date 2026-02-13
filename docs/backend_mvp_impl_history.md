# BeeBeeBrain Backend MVP 实现历史（Phase Log）

本文记录后端 MVP 的阶段性实施日志，主规范请见：`docs/backend_mvp_tech.md`。

## 2026-02-06

### P1-C
1. 后端目录新增 `app/db/engine.py` 与 `app/db/session.py`，统一 SQLite 连接和 session 生命周期。
2. 首版表结构在 `app/db/models.py` 与 Alembic revision 中对齐：`projects`、`agents`、`tasks`、`events`。
3. 提供 `uv run python -m app.db.cli init` 初始化命令（建库目录 + 迁移 + 种子）。

### P2-A
1. 扩展领域表结构并新增 revision：`task_dependencies`、`task_runs`、`inbox_items`、`documents`、`comments`、`api_usage_daily`。
2. 在可变实体引入 `version` 乐观锁字段，并补齐唯一索引与检查约束（含依赖去重、文档路径去重、usage 维度去重）。
3. 新增 repository 层：`TaskRepository`、`InboxRepository`、`DocumentRepository`，统一分页、过滤与乐观锁更新。
4. 回归测试覆盖 schema、约束、唯一索引与 repository 行为。

### P2-D
1. 新增事件 schema：`task.status.changed`、`run.log`、`alert.raised`。
2. 新增 `GET /api/v1/events/stream` SSE 通道，支持 `Last-Event-ID` 断线重连。
3. 新增 `replay_last` 参数用于最近事件回放，支持冷启动补历史。
4. 新增 `backend/scripts/events_stream_stress.py` 高频推送压测脚本。

### P3-A
1. 新增任务状态机模块，统一约束 `todo/running/review/done/blocked/failed/cancelled` 的迁移合法性。
2. 新增调度器模块，按 `priority` 升序并结合 `parent_task_id` 与 `task_dependencies` 判定可执行任务。
3. 新增任务命令：`pause/resume/retry/cancel`，通过状态机进行命令合法性校验。
4. 任务状态迁移事件统一写入 `events`，每条迁移事件强制携带 `trace_id`（请求传入或后端生成）。
5. 补齐非法迁移与非法命令回归测试。

### P3-B
1. 新增统一 LLM 契约层：`app/llm/contracts.py`（`LLMRequest/LLMResponse/LLMUsage/LLMToolCall`）与 `app/llm/errors.py`（统一错误码与 retryable 标记）。
2. 新增 Claude Code 适配器：`app/llm/providers/claude_code.py`，基于 `claude-agent-sdk` 统一映射请求、响应、tool call 与 provider 错误。
3. 新增 Claude 配置加载器：`app/llm/providers/claude_settings.py`，默认自动读取用户目录 `~/.claude/settings.json` 的 `env` 段，并允许环境变量覆盖。
4. 新增 usage 落库服务：`app/llm/usage.py`，将 token/cost 聚合写入 `task_runs` 与 `api_usage_daily`。
5. 新增回归测试：`tests/test_llm_claude_adapter.py`、`tests/test_llm_usage.py`、`tests/test_llm_factory.py`，覆盖 provider 故障注入、settings 自动读取、tool call 对齐与 usage 累加。

### P3-C
1. 新增运行编排服务：`app/runtime/execution.py`（`TaskRunRuntimeService`），打通 run 创建、执行、失败标记、重试调度与完成收敛。
2. 新增重试策略对象：`RuntimeRetryPolicy`，对超时与 retryable provider 错误采用指数退避并写入 `next_retry_at`。
3. 幂等执行统一使用 `idempotency_key`，同一请求重复触发时复用已有 `task_runs` 记录并避免重复执行。
4. 新增重启恢复流程：`interrupt_inflight_runs`（`running -> interrupted`）与 `resume_due_retries`（到期 `retry_scheduled -> running`）。
5. 新增运行恢复测试：`tests/test_runtime_execution.py`，覆盖成功幂等、超时退避、重启恢复与异常恢复端到端场景。
6. 新增运行入口 API：`POST /api/v1/tasks/{task_id}/run`，自动完成任务进入 `running`、run 执行、结果态映射（`review/failed/blocked/cancelled`）与状态事件写入。

### P3-D
1. 补齐人工干预接口：`POST /api/v1/tasks/{task_id}/pause|resume|retry`，支持 `expected_version` 乐观锁参数。
2. 新增批量干预接口：`POST /api/v1/tasks/broadcast/{command}`，默认按 `running` 状态筛选并可按 `task_ids/status` 定向广播。
3. 新增干预审计事件 `task.intervention.audit`，覆盖成功、拒绝与版本冲突三类结果。
4. 新增并发冲突回归测试，验证 stale `expected_version` 返回 `409 TASK_VERSION_CONFLICT` 且写入审计日志。

## 2026-02-07

### P4-A
1. 新增安全文件网关：`app/security/file_guard.py`（`SecureFileGateway`），固定 `root_path` 并基于 `resolve/relative_to` 拦截越权路径。
2. 新增敏感文件策略：默认阻断 `.env`、私钥后缀（`.pem/.key/.p12/.pfx`）和高风险命名文件读取。
3. 新增资源治理：单次读取字节上限、文件扩展名白名单、线程超时保护（防止长耗时读操作占用执行线程）。
4. 新增日志脱敏器：`app/security/redaction.py`，对 `api_key/access_token/secret/password/bearer token` 进行统一脱敏。
5. 运行错误信息与 API 错误响应接入脱敏逻辑，避免在 `task_runs.error_message` 与错误响应中落出密钥明文。
6. 新增安全边界回归：`tests/test_security_file_guard.py` 与 `tests/test_security_redaction.py`，覆盖越权、敏感文件、配额超限、超时与脱敏场景。

### P4-B
1. 新增上下文构建器：`app/agents/context_builder.py`（`PromptContextBuilder`），聚合任务元数据、依赖摘要、`docs/` 规则、索引文档与 `tasks.md` 快照。
2. 新增模板引擎：`PromptTemplateEngine`，支持按 `phase/task_type` 选择模板并按 `phase__type -> phase__default -> default__type -> default__default` 回退。
3. 新增 Token Budget 策略：按任务优先级映射默认预算并支持请求级覆盖。
4. 新增预算裁剪策略：优先裁剪 `tasks.md`、文档与依赖摘要，必要时进行全提示硬截断，保证输出不超过预算。
5. 新增 Prompt 模板目录：`app/agents/prompt_templates/`（首批 `default__default.tmpl`、`phase4__default.tmpl`）。
6. 新增上下文回归：`tests/test_context_builder.py`，校验关键约束包含、模板回退与预算裁剪上限。

### P4-C
1. 新增命令 API：`app/api/tools.py`，提供 `POST /api/v1/tools/finish_task|block_task|request_input`。
2. 工具写回统一走 HTTP 命令 API，不允许工具层直连数据库更新任务状态。
3. 新增幂等检查：按 `tool + task_id + idempotency_key` 回放既有成功结果，避免重复写操作。
4. 新增工具审计事件：`tool.command.audit`，记录 `outcome/applied|rejected`、错误码与响应快照。
5. 新增用户输入请求闭环：`request_input` 自动创建 `inbox_items(item_type=await_user_input)` 并写 `inbox.item.created` 事件。
6. 新增 CLI 工具封装：`app/tools/cli_tools.py`，以 HTTP 客户端形式暴露 `finish_task/block_task/request_input`。
7. 新增集成测试：`tests/test_cli_tools.py`，模拟 CLI 调用命令 API 并校验状态写回、幂等命中与审计事件。

### P4-D
1. 新增计划视图导出器：`app/exporters/tasks_md_exporter.py`（`TasksMarkdownExporter`），基于 `tasks` 表渲染 Markdown 快照。
2. 导出内容包含项目维度状态汇总与任务明细表，作为人类可读视图供审阅与追踪。
3. 新增同步开关：`TASKS_MD_SYNC_ENABLED` 与输出路径 `TASKS_MD_OUTPUT_PATH`（`app/core/config.py`）。
4. 状态同步机制接入 `tasks` 与 `tools` 的状态写路径，状态变化提交后自动触发导出刷新。
5. 新增导出一致性测试：`tests/test_tasks_md_exporter.py`，覆盖 DB 快照渲染与 API 状态变更触发文件刷新。

### P5-A
1. 新增结构化日志模块：`app/core/logging.py`，基于 `structlog + contextvars` 输出 JSON/Console 日志并统一 `trace_id/run_id/task_id/agent_id` 上下文字段。
2. FastAPI 接入 `TraceContextMiddleware`：自动透传或生成 `X-Trace-ID`，请求日志统一记录 `request.received/request.completed/request.failed`。
3. 增加日志分层 logger：`bbb.api` / `bbb.orchestration` / `bbb.runtime` / `bbb.tools` / `bbb.security`，关键路径补齐结构化日志字段。
4. 新增日志查询接口：`GET /api/v1/logs`（`app/api/logs.py`），支持按 `project_id/task_id/run_id/level` 过滤 `run.log` 事件。
5. 新增日志回归：`tests/test_logs_api.py`，覆盖过滤查询、`X-Trace-ID` 透传/生成与脏 payload 容错。

### P5-B
1. 新增指标接口：`app/api/metrics.py`，提供 `GET /api/v1/metrics/usage-daily` 与 `GET /api/v1/metrics/runs-summary`。
2. `usage-daily` 支持按 `provider/model/date` 过滤并输出请求数、token 与成本汇总。
3. `runs-summary` 基于 `task_runs` 聚合运行状态分布、总 token/cost 与平均/最大耗时。
4. 成本阈值告警接入 `app/llm/usage.py`：命中 `COST_ALERT_THRESHOLD_USD` 后写 `alert.raised` 并创建 `inbox_items(await_user_input)`。
5. 新增回归测试：`tests/test_metrics_api.py` 与 `tests/test_llm_usage.py`，覆盖聚合正确性与成本告警去重。

### P5-C
1. 新增卡死检测器：`app/runtime/stuck_detector.py`（`StuckRunDetector`），覆盖无输出超时、重复动作、高错误率三类规则。
2. 检测命中后自动写 `alert.raised`，并创建 `inbox_items(item_type=await_user_input)`，附带诊断信息与去重 `source_id`。
3. 防重复告警策略：同一 `run_id + alert_kind` 在未关闭前仅创建一个开放收件箱项。
4. FastAPI `lifespan` 接入后台轮询协程：`run_stuck_detector_loop`，默认每 `60s` 执行一次检测。
5. 新增配置项：`STUCK_IDLE_TIMEOUT_S`、`STUCK_REPEAT_THRESHOLD`、`STUCK_ERROR_RATE_THRESHOLD`、`STUCK_SCAN_INTERVAL_S`。
6. 新增回归测试：`tests/test_stuck_detector.py`，覆盖超时、重复动作、高错误率与误报抑制场景。

### P5-D
1. 新增安全审计模块：`app/security/audit.py`，统一 `security.audit.allowed|denied` 事件与字段契约（`actor/action/resource/outcome/reason/ip/metadata`）。
2. 关键命令路径接入审计：`app/api/tasks.py` 与 `app/api/tools.py` 在允许/拒绝场景写入安全审计事件。
3. 扩展故障注入模式：`FailureMode` 新增 `database_lock` 与 `file_permission_error`，并补齐异常类型与单测。
4. 输出运维文档：`docs/runbook/phase5_recovery_sop.md`，覆盖 LLM 超时、DB 锁、文件权限错误的排障与恢复流程。
5. 固化回滚脚本：`backend/scripts/rollback_with_backup.ps1` 与 `backend/scripts/rollback_with_backup.sh`，默认执行“先备份再 Alembic downgrade”。

### P6-A
1. 新增主验证器脚本：`backend/scripts/api_probe.py`，覆盖 `health/ready`、`agents/tasks` CRUD、`run/pause/resume/retry/cancel`、`inbox close(user_input)`、`events` 回放与流式续传。
2. 验证器采用隔离测试环境：临时 SQLite + 临时工作目录 + `TestClient`，并通过 patch `create_llm_client` 消除外部 LLM 依赖。
3. 输出结构化报告：默认写入 `docs/reports/phase6/api_probe_report.json` 与 `docs/reports/phase6/api_probe_report.md`，包含通过率、时延与失败样例。
4. 增加一键入口：`backend/Makefile` 新增 `api-probe` 目标（`uv run python scripts/api_probe.py --fail-on-error`）。
5. CI 新增冒烟作业：`.github/workflows/backend-quality.yml` 增加 `api-smoke` job，执行验证器并上传报告 artifact。

### P6-B
1. 新增失败恢复回归探针：`backend/scripts/failure_recovery_probe.py`，覆盖 `timeout`、`transient_error`、重复请求幂等、重启恢复四类场景矩阵。
2. 回归探针验证幂等键防重、指数退避重试、`resume_due_retries` 与 `recover_after_restart` 行为一致性。
3. 统一报告格式并归档：默认写入 `docs/reports/phase6/failure_recovery_report.json` 与 `docs/reports/phase6/failure_recovery_report.md`。
4. 增加冻结前必跑入口：`backend/Makefile` 新增 `failure-recovery-probe` 与 `freeze-gate` 目标。
5. CI 新增回归作业：`.github/workflows/backend-quality.yml` 增加 `failure-recovery-regression` job，执行探针并上传 artifact。

### P6-C
1. 新增极简调试面板：`GET /debug/panel`（`backend/app/api/debug.py` + `backend/app/static/debug_panel.html`），支持任务动作、`request_input`、收件箱关闭与事件流查看。
2. 新增最小鉴权中间件：`backend/app/core/auth.py`，当配置 `LOCAL_API_KEY` 时，对 `/api/v1/*` 请求校验 `X-API-Key` 或 `Authorization: Bearer`。
3. 调试面板支持环境配置（`Base URL/Project ID/Auth Mode/Token`）并提供“一键验收链路”按钮，便于联调复现。
4. 增加鉴权与面板回归：`backend/tests/test_local_api_key_auth.py`，覆盖未授权拒绝、两种鉴权头放行、面板访问可用性。
5. 面板定位明确为验收工具：在 `backend/README.md` 中标注“非正式产品 UI”，避免误作为产品界面演进。
6. 联调记录归档：`docs/reports/phase6/panel_integration_notes.md`，沉淀链路执行结果与非阻塞问题。

### P6-C 修复
1. 新增启动期数据库自动初始化兜底：`backend/app/main.py` 在开发环境默认执行迁移与可选种子，避免调试面板首次运行因缺表报错。
2. 新增配置项：`DB_AUTO_INIT`、`DB_AUTO_SEED`（`backend/app/core/config.py`），默认仅 `APP_ENV=development` 开启，测试与生产默认关闭。
3. 新增回归：`backend/tests/test_health.py` 验证开发环境启动后数据库表自动可用。

### P6-C 增强
1. 调试面板新增 Agent Playground：一键准备 `play_ground/README.md`（`114514`）、测试 Agent（`claude_code`）与测试任务，并支持面板直接触发 `task.run`。
2. 新增调试准备接口：`POST /debug/agent-playground/setup`（`backend/app/api/debug.py`），返回 `agent_id/task_id/readme_path/run_prompt` 供面板联调使用。
3. 运行成功后追加 `run.log` 结果事件：`backend/app/runtime/execution.py` 在 run 成功路径写入模型输出文本，便于面板通过 `GET /api/v1/logs` 回显执行结果。
4. 新增回归：`backend/tests/test_debug_api.py` 与 `backend/tests/test_agents_tasks_api.py`，覆盖 playground 准备链路和 run 输出查询。

### P7
1. WebSocket 对话通道接入执行器：`app/api/ws_conversations.py` 在 `user.message` 与 `user.input_response` 后触发 `ConversationExecutor`，并支持 `user.interrupt` 取消。
2. Claude 流式响应闭环：`app/llm/contracts.py` 与 `app/llm/providers/claude_code.py` 增加流式事件契约（`TEXT_CHUNK/TOOL_CALL_START/COMPLETE/ERROR`）与 `generate_stream`。
3. 对话执行器落地：`app/runtime/conversation_executor.py` 负责上下文构建、流式推送、消息持久化、工具调用透明事件（`tool_call/tool_result/input_request`）与超时/取消处理。
4. 任务上下文继承：`POST /api/v1/conversations` 在指定 `task_id` 时自动注入任务摘要、依赖、近期运行记录与可用工具到 `context_json.task_context`。
5. 执行中交互：`user.input_response` 支持可选 `resume_task=true`，在任务为 `blocked` 时自动回写到 `todo` 并写任务状态事件。
6. 评论触发对话：新增 `POST /api/v1/comments/{id}/reply`，自动创建对话并请求 Agent 响应；成功后回写评论 `status=addressed` 且关联 `conversation_id`。
7. 数据层扩展：新增 migration `9c1a2b3d4e5f_add_comment_conversation_link.py`，为 `comments` 增加 `conversation_id`（SQLite 采用 batch alter）。
8. 回归测试补齐：新增 `tests/test_conversation_executor.py`、`tests/test_comments_reply_api.py`，并扩展 `tests/test_conversations_api.py`、`tests/test_ws_conversations.py`、`tests/test_db_schema.py`。

### P8-A0
1. 前端新增 API 基础设施：`frontend/src/services/api.ts`（fetch 客户端、统一错误处理、token 注入）。
2. 前端新增 WebSocket 基础设施：`frontend/src/services/websocket.ts`（心跳、断线重连、消息队列）。
3. 前端新增 Pinia store：`agents/tasks/inbox/conversations/usage/roles/fileSystem`，替换原 mock 数据源。
4. 前端核心视图完成 store 化改造：`DashboardView`、`InboxView`、`ChatView`、`TableView`、`KanbanView`、`ApiView`、`FilesView`、`FileViewer`、`RolesView`。
5. 前端环境变量分离：`frontend/.env.development` 与 `frontend/.env.production`。

### P8-A
1. 后端补齐联调接口：`app/api/dashboard.py`、`app/api/usage.py`、`app/api/files.py`、`app/api/roles.py`。
2. 扩展现有接口：`app/api/agents.py` 新增 `GET /agents/{id}/health`；`app/api/inbox.py` 新增 `PATCH /inbox/{id}/read`。
3. 接入 CORS：`app/main.py` 增加 `CORSMiddleware`；`app/core/config.py` 增加 `CORS_ALLOW_ORIGINS/CORS_ALLOW_CREDENTIALS` 配置。
4. 联调问题清单归档：`docs/integration-issues.md`。

### P8-B
1. 新增综合联调回归：`backend/tests/test_phase8_integration_api.py`（Dashboard/Inbox/Usage/Files/Roles/CORS/OpenAPI）。
2. 新增 API E2E 套件目录：`backend/tests/e2e/`，覆盖 Dashboard、任务生命周期、对话流、文件权限流。
3. 新增浏览器 E2E：`frontend/tests/e2e_browser/happy-path.spec.ts` 与 Playwright 配置。
4. E2E 报告归档：`docs/e2e-report.md`。

### P8-C
1. 发布交付补齐：`backend/Dockerfile`、`frontend/Dockerfile`、`frontend/nginx.conf`、`docker-compose.yml`。
2. 发布脚本补齐：`scripts/release.sh`（版本更新、质量门禁、构建、打标签）。
3. 部署文档：`docs/deployment.md`。
4. 运维手册：`docs/operations.md`。

### P8-D
1. 前端打包优化落地：`frontend/vite.config.ts`（manualChunks、CSS 分割、ES2020 目标）。
2. 前端错误边界补齐：`frontend/src/App.vue` 增加全局错误捕获提示。
3. 前端构建与 E2E 指南更新：`frontend/README.md`。
