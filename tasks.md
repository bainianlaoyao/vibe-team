# BeeBeeBrain Backend MVP 并行开发任务计划

## 0. 计划说明

本文件用于指导后端并行开发，组织方式固定为：
1. `Phase`：阶段目标与验收边界。
2. `并行任务`：同一阶段内可由不同开发者并行推进的工作流。
3. `串行任务`：每个并行任务内部按顺序执行的步骤。

约定：
1. 任务状态用 `[ ]` / `[x]`。
2. 阶段完成条件为该 Phase 下所有并行任务完成且通过验收。
3. 默认后端目录为 `backend/`，文档目录为 `docs/`。

---

## 当前状态（2026-02-08）

1. 项目总体状态：`Backend MVP 按计划推进中`。
2. Phase 1 状态：`已完成并验收通过（3/3）`。
3. Phase 2 状态：`已完成并验收通过（4/4）`。
4. Phase 3 状态：`已完成并验收通过（5/5）`。
5. Phase 4 状态：`已完成并验收通过（4/4）`。
6. Phase 5 状态：`已完成并验收通过（4/4）`。
7. Phase 6 状态：`已完成并验收通过（3/3）`。
8. Phase 7 状态：`已完成并验收通过（6/6）` - 人机协作对话。
9. Phase 8 状态：`进行中（4/5）` - 联调、验收与发布（待 Docker 引擎可用后完成容器健康检查实跑）。
   - P8-A0：`已完成（10/10）` - 前端 API 基础设施（联调前置）
   - P8-A：`已完成（10/10）` - 前后端联调（依赖 P8-A0）
   - P8-B：`已完成（5/5）` - 端到端验收用例
   - P8-C：`已完成（5/5）` - 发布与运维交付
   - P8-D：`已完成（4/4）` - 前端优化与打包
10. 最近里程碑：
`backend/` 已完成 API 调用器、失败恢复回归套件与极简调试面板闭环，并补齐开发环境启动自动迁移兜底（避免首次调试缺表）；调试面板已增强 Agent Playground（可执行任务并回显结果）。
11. Phase 9 状态：`已完成并验收通过（6/6）` - 前端 Bug 修复与可访问性收口。

---

## Phase 1: 工程基线与骨架

目标：建立可运行、可测试、可观测的后端基础工程。
状态：`已完成（2026-02-06）`

### 并行任务 P1-A：项目脚手架与依赖基线

- Owner: Backend Core
- 依赖：无
- 串行任务：
1. [x] 初始化 `backend/` 工程结构（`app/`, `tests/`, `pyproject.toml`）。
2. [x] 集成基础依赖：FastAPI、SQLModel、Uvicorn、Pydantic、HTTPX。
3. [x] 建立配置系统（环境变量加载、开发/测试配置切换）。
4. [x] 提供 `GET /healthz` 与 `GET /readyz` 探活接口。
5. [x] 输出本地启动脚本与最小 README。

### 并行任务 P1-B：代码规范与质量门禁

- Owner: Infra/QA
- 依赖：无
- 串行任务：
1. [x] 配置 `ruff`, `black`, `mypy`, `pytest`。
2. [x] 配置 pre-commit 或统一 `make`/`just` 命令入口。
3. [x] 建立 CI 流水线（lint + type check + unit test）。
4. [x] 在 CI 中加入覆盖率报告并设置最低阈值。

### 并行任务 P1-C：数据库初始化与迁移机制

- Owner: Data
- 依赖：P1-A step 1
- 串行任务：
1. [x] 建立 SQLite 连接管理和 session 生命周期。
2. [x] 定义第一版 schema：`projects`, `agents`, `tasks`, `events`。
3. [x] 集成迁移工具（Alembic 或等价方案）。
4. [x] 提供初始化命令（创建库、执行迁移、插入种子数据）。
5. [x] 编写 schema 基础回归测试。

Phase 1 验收：
1. [x] 本地可一键启动 API。
2. [x] CI 稳定通过。
3. [x] 数据库迁移可重复执行且不破坏已有数据。

---

## Phase 2: 领域模型与核心 API

目标：打通任务、Agent、收件箱的基础 CRUD 和状态管理能力。

### 并行任务 P2-A：领域模型与仓储层

- Owner: Data
- 依赖：Phase 1 完成
- 串行任务：
1. [x] 完整建模：`task_dependencies`, `task_runs`, `inbox_items`, `documents`, `comments`, `api_usage_daily`。
2. [x] 建立 repository 层（分页、过滤、乐观锁字段）。
3. [x] 统一枚举与状态常量，避免字符串散落。
4. [x] 增加模型级约束测试与唯一索引测试。

### 并行任务 P2-B：任务与 Agent API

- Owner: Backend API
- 依赖：P2-A step 1
- 串行任务：
1. [x] 实现 `agents` 增删改查接口。
2. [x] 实现 `tasks` 增删改查接口（含优先级、负责人、依赖关系）。
3. [x] 实现参数校验与统一错误码返回。
4. [x] 补齐 OpenAPI 示例请求/响应。
5. [x] 编写集成测试（正常流 + 非法参数流）。

### 并行任务 P2-C：收件箱 API 与用户确认动作

- Owner: Backend API
- 依赖：P2-A step 1
- 串行任务：
1. [x] 实现 `GET /inbox` 与 `item_type/status` 筛选（`await_user_input/task_completed`）。
2. [x] 实现 `POST /inbox/{item_id}/close`，支持携带 `user_input`。
3. [x] 将收件箱动作写入 `events`（`inbox.item.created`、`inbox.item.closed`、可选 `user.input.submitted`）。
4. [x] 编写收件箱集成测试（等待用户输入流、任务完成确认流）。

### 并行任务 P2-D：事件流推送通道

- Owner: Realtime
- 依赖：P2-B step 2
- 串行任务：
1. [x] 定义事件 schema（任务状态、运行日志、告警）。
2. [x] 实现 SSE 或 WebSocket 推送端点。
3. [x] 增加断线重连和最近事件回放机制。
4. [x] 编写高频事件推送压测脚本。

Phase 2 验收：
1. [x] 前端可通过 API 完成任务和 Agent 的基本管理。
2. [x] 收件箱可完成“等待用户输入/任务完成通知”的创建、关闭与回放。
3. [x] 事件流可稳定推送状态变化。

---

## Phase 3: 编排与执行引擎

目标：实现任务状态机、执行生命周期和可恢复运行能力。
说明：本 Phase 为 DAG，`并行任务` 表示可由不同 Owner 并行推进，但存在前置依赖，不代表同一时刻全部可启动。

### 并行任务 P3-A：任务状态机与调度器

- Owner: Orchestration
- 依赖：Phase 2 完成
- 串行任务：
1. [x] 定义 `todo/running/review/done/blocked/failed/cancelled` 状态迁移表。
2. [x] 实现调度器：按优先级与依赖关系挑选可执行任务。
3. [x] 实现暂停、恢复、重试、取消等命令处理。
4. [x] 为每次状态迁移写事件与 trace_id。
5. [x] 为非法迁移编写回归测试。

### 并行任务 P3-B：LLM 适配层（Claude Code 首期）

- Owner: LLM
- 依赖：P3-A step 1
- 串行任务：
1. [x] 统一 LLM 客户端接口（请求、响应、错误映射）。
2. [x] 实现 Claude Code 适配器并接入模型配置（自动读取 `~/.claude/settings.json`）。
3. [x] 对齐 tool call 结构（provider 输出统一为 `LLMToolCall`）。
4. [x] 记录 token 和成本到 `task_runs` 与 `api_usage_daily`。
5. [x] 增加 provider 故障注入测试。

### 并行任务 P3-C0：运行可靠性基础准备

- Owner: Runtime
- 依赖：P3-A step 1
- 串行任务：
1. [x] 定义 `task_runs` 运行状态枚举与字段契约（`attempt`、`idempotency_key`、`next_retry_at`）。
2. [x] 搭建失败注入测试桩（超时、临时错误、进程重启中断）。
3. [x] 补齐 run 级 repository 接口与事件写入契约。
4. [x] 输出 P3-C 实施基线（状态图与恢复时序）。

### 并行任务 P3-C：运行生命周期与失败恢复

- Owner: Runtime
- 依赖：P3-A step 2, P3-B step 1, P3-C0 step 2
- 串行任务：
1. [x] 实现 `task_runs` 创建、完成、失败、重试累计。
2. [x] 加入超时和指数退避策略。
3. [x] 加入幂等键（同一请求防重执行）。
4. [x] 实现服务重启后的运行状态恢复。
5. [x] 编写异常恢复端到端测试。

### 并行任务 P3-D：人工干预接口

- Owner: Backend API
- 依赖：P3-A step 3
- 串行任务：
1. [x] 实现 `POST /tasks/{id}/pause|resume|retry`。
2. [x] 实现广播指令接口（批量作用于多个运行任务）。
3. [x] 干预动作全部写审计日志。
4. [x] 编写并发干预冲突测试。

Phase 3 验收：
1. [x] 任务可自动进入执行并稳定流转。
2. [x] 失败可自动重试或人工恢复。
3. [x] 干预操作对状态机一致性无破坏。

---

## Phase 4: 上下文系统与工具治理

目标：实现“CLI-first”的编排体系，确保 Agent 在安全边界内高效执行并回馈状态。

### 并行任务 P4-A：安全与边界

- Owner: Security/Infra
- 依赖：Phase 2 完成
- 串行任务：
1. [x] 实施 Worktree 隔离：固定执行根目录，限制文件访问范围。
2. [x] 实现敏感文件防护：拦截 `.env`、密钥文件读取，实施日志脱敏。
3. [x] 资源配额控制：限制单次读取大小、文件类型与操作超时。
4. [x] 编写安全边界测试（越权路径、敏感文件访问、资源耗尽）。

### 并行任务 P4-B：上下文构建器

- Owner: Orchestration
- 依赖：P3-B step 1
- 串行任务：
1. [x] 实现 Prompt 组装器：聚合 DB 任务信息、`docs/` 规范与全局规则。
2. [x] 引入 Token Budget 管理：基于优先级动态裁剪上下文长度。
3. [x] 集成模板引擎：支持为不同 Phase/任务类型加载不同 Prompt 模板。
4. [x] 编写上下文生成测试（验证关键约束包含性与 Token 限制）。

### 并行任务 P4-C：领域交互工具

- Owner: Backend API
- 依赖：P3-A step 3, P3-D step 1
- 串行任务：
1. [x] 封装 CLI 专用指令工具（`finish_task`, `block_task`, `request_input`）。
2. [x] 工具实现：通过 HTTP 调用后端命令 API 回写状态（禁止直连 DB）。
3. [x] 实现调用幂等性检查（Idempotency Key）与操作审计。
4. [x] 编写工具交互集成测试（模拟 CLI 触发后端状态变更）。

### 并行任务 P4-D：计划视图同步

- Owner: Data
- 依赖：P4-C step 2
- 串行任务：
1. [x] 实现 `tasks.md` 生成器：基于 DB 状态渲染人类可读视图。
2. [x] 建立同步机制：任务状态变更事件触发 `tasks.md` 刷新。
3. [x] 优化 Markdown 渲染模板，确保与 `docs/` 规范一致。
4. [x] 编写导出一致性测试（DB 变更后文件内容正确更新）。

Phase 4 验收：
1. [x] 敏感文件与越权路径访问被有效拦截。
2. [x] CLI 可接收包含完整上下文的 Prompt 并正确理解任务。
3. [x] CLI 可通过工具正确回写任务状态至数据库。
4. [x] `tasks.md` 始终反映数据库中的最新任务状态。

---

## Phase 5: 观测、告警与稳定性

目标：建立可运营的后端运行质量体系。

### 并行任务 P5-A：结构化日志与链路追踪

- Owner: Observability
- 依赖：Phase 3 完成
- 技术栈决策（2026-02-07）：
	- 日志库：`structlog`（JSON 结构化日志 + 上下文绑定）
	- 上下文传播：`contextvars`（FastAPI middleware 生成/绑定 `trace_id`，日志自动携带 `trace_id/run_id/task_id`）
	- 第三方日志统一：使用 `structlog.stdlib.ProcessorFormatter` 桥接 `uvicorn` / `sqlalchemy` / 其他标准 `logging` 输出
	- 输出与存储：默认 stdout/文件 JSON（标准库 `RotatingFileHandler`），可选写入 DB（仅 `WARNING+`，用于查询接口）
	- OpenTelemetry：MVP 阶段不引入（单体服务优先最小依赖；后续按需扩展）
	- 推荐 logger 命名分层：`bbb.api` / `bbb.orchestration` / `bbb.runtime` / `bbb.tools` / `bbb.security` / `bbb.llm` / `bbb.db`
	- 配置项（Settings）：`LOG_LEVEL`、`LOG_FORMAT(json|console)`、`LOG_FILE`、`LOG_DB_ENABLED`、`LOG_DB_MIN_LEVEL`
- 串行任务：
1. [x] 统一日志格式（JSON + trace_id + run_id + task_id）。
2. [x] 建立日志分层（API、编排、执行、工具、安全）。
3. [x] 接入日志查询接口（按任务/运行过滤）。
4. [x] 编写日志完整性测试。

### 并行任务 P5-B：指标与成本看板数据

- Owner: Observability
- 依赖：P3-B step 4
- 技术栈决策（2026-02-07）：
  - 无需新依赖或新基础设施：直接对已有 `api_usage_daily` 与 `task_runs` 表做 SQL 聚合查询
  - 新增 REST 端点（如 `GET /api/v1/metrics/usage-daily`、`GET /api/v1/metrics/runs-summary`），复用现有 FastAPI + repository 模式
  - 告警策略：基于阈值比较（配置项 `COST_ALERT_THRESHOLD_USD`），命中后写 `alert.raised` 事件并创建 `inbox_items`
  - 不引入时序数据库或 Prometheus（MVP 单机 SQLite 体量无需）
- 串行任务：
1. [x] 落库 `api_usage_daily` 与运行时延指标。
2. [x] 提供聚合接口（按 provider/model/date 统计）。
3. [x] 定义成本超阈值告警策略。
4. [x] 编写统计正确性测试。

### 并行任务 P5-C：卡死检测与用户确认入箱

- Owner: Runtime
- 依赖：P3-C step 2
- 技术栈决策（2026-02-07）：
  - 检测机制：FastAPI lifespan 内启动 `asyncio.create_task` 周期协程（默认每 60s 轮询），不引入 APScheduler/Celery 等外部调度框架
  - 检测维度：① 无输出超时（`task_runs.started_at` 超过阈值仍为 `running`）；② 重复动作哈希（近 N 条 `run.log` 事件 payload 哈希去重率 > 阈值）；③ 错误速率（滑动窗口内 `failed` 占比 > 阈值）
  - 检测结果动作：复用已有 `InboxRepository` 创建 `inbox_items(item_type=await_user_input)` + 写 `alert.raised` 事件，无需新存储
  - 阈值可配置化：`Settings` 新增 `STUCK_IDLE_TIMEOUT_S`、`STUCK_REPEAT_THRESHOLD`、`STUCK_ERROR_RATE_THRESHOLD`
  - 防重复告警：同一 `run_id` 的同类告警在未关闭前不重复创建（基于 `inbox_items` 去重查询）
- 串行任务：
1. [x] 实现无输出超时检测。
2. [x] 实现重复动作哈希检测。
3. [x] 实现错误速率阈值检测。
4. [x] 命中阈值自动生成 `inbox_items(item_type=await_user_input)` 并附带诊断信息。
5. [x] 编写误报/漏报评估测试。

### 并行任务 P5-D：安全审计与故障演练

- Owner: Security/Infra
- 依赖：P4-A step 3, P5-A step 1
- 技术栈决策（2026-02-07）：
  - 审计日志存储：复用现有 `events` 表，以 `security.audit.*` 前缀事件类型记录（如 `security.audit.access_denied`、`security.audit.sensitive_file_blocked`），不新建独立 `audit_logs` 表
  - 审计字段规范：payload 统一包含 `actor`、`action`、`resource`、`outcome(allowed|denied)`、`reason`、`ip`（可选）
  - 故障演练：扩展已有 `FailureInjectionStub`（`tests/test_runtime_failure_injection.py`），新增 DB 锁竞争、文件权限错误场景，无需新依赖
  - Runbook 与 SOP：以 Markdown 文档输出到 `docs/runbook/`，不引入专用事件响应平台
  - 回滚脚本：基于 Alembic `downgrade` + SQLite 文件备份（`cp beebeebrain.db beebeebrain.db.bak`），无需新工具
- 串行任务：
1. [x] 对关键 API 和工具调用补齐审计字段。
2. [x] 演练常见故障：LLM 超时、数据库锁、文件权限错误。
3. [x] 输出恢复 Runbook 与应急 SOP。
4. [x] 固化回滚脚本与数据备份策略。

Phase 5 验收：
1. [x] 关键问题可被检测并定位。
2. [x] 成本与健康状态可在 UI 查询。
3. [x] 故障演练后可按 SOP 恢复服务。

---

## Phase 6: 极简验证器与后端验收

目标：以最小实现验证后端契约、状态机与恢复能力是否正确。

### 并行任务 P6-A：API 调用器（主验证器）

- Owner: QA + Backend API
- 依赖：Phase 5 完成
- 串行任务：
1. [x] 固化核心场景脚本：`health/ready`、`agents/tasks` CRUD、`run/pause/resume/retry/cancel`、`inbox close(user_input)`、`events` 查询/流式。
2. [x] 提供一键入口（`uv run pytest ...` 或 `uv run python scripts/api_probe.py`）。
3. [x] 输出结构化验证报告（JSON + Markdown），记录通过率、时延和失败样例。
4. [x] 接入 CI 冒烟作业，作为发布前强制检查。

### 并行任务 P6-B：失败恢复回归套件

- Owner: Runtime + QA
- 依赖：P6-A step 1, P3-C step 5
- 串行任务：
1. [x] 构建异常场景矩阵（超时、临时错误、重复请求、服务重启中断）。
2. [x] 验证幂等键、防重、指数退避与重启恢复行为。
3. [x] 固化回归报告格式并归档到 `docs/` 或 CI artifact。
4. [x] 将该套件纳入每次版本冻结前的必跑检查。

### 并行任务 P6-C：极简前端/调试面板

- Owner: Frontend + Backend API
- 依赖：P6-A step 1
- 串行任务：
1. [x] 实现极简操作面板（任务列表、任务动作按钮、收件箱关闭输入、事件流查看）。
2. [x] 接入最小鉴权与环境配置（本地 token / API key）。
3. [x] 使用面板跑通一条完整链路并记录联调问题。
4. [x] 明确该面板定位为验收工具，不作为正式产品 UI。

Phase 6 验收：
1. [x] API 调用器可一键验证后端核心链路。
2. [x] 失败恢复场景可重复复现并输出报告。
3. [x] 极简面板可触发核心流程且结果与 API 调用器一致。

---

## Phase 7: 人机协作对话（Agent Conversation）

目标：实现类 Claude Code 的即时对话体验——用户与 Agent 实时双向交互，Agent 执行过程透明可见，用户可随时介入。

### 并行任务 P7-A：对话数据模型与基础 CRUD

- Owner: Data + Backend API
- 依赖：Phase 6 完成
- 串行任务：
1. [x] 新增 `conversations`、`messages`、`conversation_sessions` 表及 Alembic 迁移。
2. [x] 新增 `ConversationRepository`、`MessageRepository`、`SessionRepository`。
3. [x] 新增对话管理 API：`app/api/conversations.py`（CRUD + 消息历史查询）。
4. [x] 新增回归测试：`tests/test_conversations_api.py`。

### 并行任务 P7-B：WebSocket 实时通道

- Owner: Realtime + Backend API
- 依赖：P7-A step 2
- 串行任务：
1. [x] 新增 WebSocket 端点：`app/api/ws_conversations.py`（`WS /ws/conversations/{id}`）。
2. [x] 实现消息协议：`user.message`、`assistant.chunk`、`user.interrupt`、`session.heartbeat` 等。
3. [x] 实现连接管理：心跳（30s）、断线检测（90s）、客户端标识。
4. [x] 新增 WebSocket 回归：`tests/test_ws_conversations.py`。

### 并行任务 P7-C：流式 LLM 响应集成

- Owner: LLM + Orchestration
- 依赖：P7-B step 2
- 串行任务：
1. [x] 扩展 `ClaudeCodeAdapter` 支持流式回调（`on_chunk`、`on_tool_call`、`on_complete`）。
2. [x] 新增 `ConversationExecutor`：协调 LLM 调用与 WebSocket 推送。
3. [x] 流式输出实时写入 `messages` 表并推送 WebSocket。
4. [x] 实现用户打断：收到 `user.interrupt` 时取消 LLM 请求。

### 并行任务 P7-D：执行中交互与工具透明

- Owner: Orchestration + Backend API
- 依赖：P7-C step 2
- 串行任务：
1. [x] Agent 调用工具时推送 `assistant.tool_call`（工具名、参数摘要）。
2. [x] 工具执行结果推送 `assistant.tool_result`。
3. [x] 实现 `request_input`：Agent 暂停并通过 WebSocket 向用户提问。
4. [x] 用户通过 `user.input_response` 回复后 Agent 继续执行。

### 并行任务 P7-E：任务上下文继承与会话恢复

- Owner: Orchestration
- 依赖：P7-C step 3
- 串行任务：
1. [x] 创建对话时可指定 `task_id`，自动注入任务描述、依赖摘要、执行历史。
2. [x] 对话中 Agent 可调用工具（继承任务的 `enabled_tools_json`）。
3. [x] 对话结果可选回写任务状态（如用户确认后从 blocked -> todo）。
4. [x] 实现断线恢复：`last_message_id` 重连、消息缓存、历史补发。

### 并行任务 P7-F：评论触发响应

- Owner: Backend API
- 依赖：P7-A step 3
- 串行任务：
1. [x] 扩展 `comments` 表增加 `conversation_id` 字段及迁移。
2. [x] 新增 `POST /comments/{id}/reply` 创建对话并请求 Agent 响应。
3. [x] Agent 响应后自动更新评论状态为 `addressed`。
4. [x] 新增评论-对话联动回归测试。

Phase 7 验收：
1. [x] 用户可通过 WebSocket 与 Agent 进行实时双向对话。
2. [x] Agent 输出逐块流式推送，用户可随时打断。
3. [x] 工具调用过程透明可见（工具名、参数、结果）。
4. [x] Agent 可主动向用户提问，用户回复后继续执行。
5. [x] 对话可关联任务并继承执行上下文。
6. [x] 断线后可通过 `last_message_id` 恢复会话。

---

## Phase 8: 联调、验收与发布

目标：完成前后端联调、端到端验收和首版发布准备。

### 技术栈决策（已确认）

- **前端脚手架**：Vite + Vue 3（已完成，位于 `frontend/`）
- **状态管理**：Pinia（Setup Store 语法）
- **路由**：Vue Router 4（懒加载）
- **UI 组件**：@phosphor-icons/vue + Tailwind CSS v4
- **API 客户端**：手写 fetch（MVP 阶段），后续可迁移至 openapi-typescript
- **WebSocket 消费**：原生 WebSocket API
- **后端 CORS**：`main.py` 中加入 `CORSMiddleware`
- **认证方案**：MVP 本地 token / API key header

### 前端页面与后端 API 对照表

| 页面/模块 | 路由 | 核心功能 | 后端 API |
|----------|------|---------|---------|
| Dashboard | `/` | 统计卡片、最近更新、Agent 状态 | `GET /agents`, `GET /tasks/stats`, `GET /updates` |
| Inbox | `/inbox` | 消息列表、标记已读、详情 | `GET /inbox`, `PATCH /inbox/{id}/read` |
| Chat | `/chat` | Agent 对话、消息发送、实时响应 | `WS /ws/conversations/{id}`, `GET/POST /conversations/{id}/messages` |
| Table View | `/agents/table` | 按 Agent 分组任务、筛选排序 | `GET /tasks?group_by=agent`, `GET /agents/{id}/health` |
| Kanban View | `/agents/kanban` | 看板拖拽、状态更新 | `GET /tasks`, `PATCH /tasks/{id}` |
| Customize | `/agents/customize` | Agent 配置编辑 | `GET/PUT /agents/{id}/config` |
| Workflow | `/workflow` | 可视化工作流画布 | `GET/PUT /workflows/{id}`, `POST/DELETE /workflows/{id}/nodes` |
| Files | `/files` | 文件树、权限管理 | `GET /files`, `PATCH /files/{id}/permissions` |
| File Viewer | `/files/view/:id` | 文件预览、元信息 | `GET /files/{id}/content`, `GET /files/{id}` |
| Roles | `/roles` | 角色配置 CRUD | `GET/POST/PUT/DELETE /roles` |
| API Usage | `/api` | 预算、健康度、趋势图 | `GET /usage/budget`, `GET /usage/timeline`, `GET /usage/errors` |

### 并行任务 P8-A0：前端 API 基础设施（联调前置）

- Owner: Frontend
- 依赖：Phase 7 完成
- 说明：当前前端仅有 UI 壳子，所有交互控件操作的是本地 mock 数据，刷新即丢失。需先搭建 API 服务层和状态管理，才能进行真正的联调。
- 串行任务：
1. [x] **API 服务层**：创建 `frontend/src/services/api.ts`，封装 fetch 客户端（baseURL、错误处理、token 注入）。
2. [x] **WebSocket 服务**：创建 `frontend/src/services/websocket.ts`，封装 WS 连接管理（心跳、断线重连、消息队列）。
3. [x] **Agents Store**：创建 `frontend/src/stores/agents.ts`，替换 `mockAgents`，实现 `fetchAgents`、`updateAgent` 等 action。
4. [x] **Tasks Store**：创建 `frontend/src/stores/tasks.ts`，替换 `mockTasks`，实现 CRUD + 状态流转 action。
5. [x] **Inbox Store**：创建 `frontend/src/stores/inbox.ts`，替换 `mockInbox`，实现列表加载、标记已读、关闭项 action。
6. [x] **Conversations Store**：创建 `frontend/src/stores/conversations.ts`，管理对话列表、消息历史、WebSocket 消息收发。
7. [x] **Usage Store**：创建 `frontend/src/stores/usage.ts`，替换 `mockApiUsage`，实现预算、趋势、错误流查询。
8. [x] **View 组件改造**：逐个更新 View 组件，从直接操作 mock 数据改为调用 store action。
   - `DashboardView.vue`：调用 agents/tasks store
   - `InboxView.vue`：调用 inbox store
   - `ChatView.vue`：调用 conversations store + WebSocket
   - `TableView.vue` / `KanbanView.vue`：调用 tasks store
   - `ApiView.vue`：调用 usage store
9. [x] **加载与错误状态**：为每个 store 增加 `loading`、`error` 状态，View 组件显示加载中/错误提示。
10. [x] **环境变量配置**：创建 `.env.development` 和 `.env.production`，配置 `VITE_API_BASE_URL`。

---

### 并行任务 P8-A：前后端联调

- Owner: Backend API + Frontend
- 依赖：P8-A0 完成
- 串行任务：
1. [x] **Dashboard 联调**：统计接口 `GET /tasks/stats`、Agent 列表 `GET /agents`、最近更新 `GET /updates`。
2. [x] **Inbox 联调**：收件箱列表 `GET /inbox`、标记已读 `PATCH /inbox/{id}/read`、关闭项 `POST /inbox/{id}/close`。
3. [x] **Chat 联调**：WebSocket 连接 `WS /ws/conversations/{id}`、消息协议（`user.message`、`assistant.chunk`、`user.interrupt`）。
4. [x] **Agents 联调**：任务 CRUD `GET/POST/PATCH /tasks`、Agent 健康度 `GET /agents/{id}/health`、干预操作 `POST /tasks/{id}/pause|resume|retry`。
5. [x] **Files 联调**：文件树 `GET /files`、权限设置 `PATCH /files/{id}/permissions`、内容预览 `GET /files/{id}/content`。
6. [x] **Roles 联调**：角色配置 CRUD `GET/POST/PUT/DELETE /roles`。
7. [x] **API Usage 联调**：预算 `GET /usage/budget`、趋势 `GET /usage/timeline`、错误流 `GET /usage/errors`。
8. [x] **CORS 配置**：后端 `main.py` 添加 `CORSMiddleware`，允许前端域名。
9. [x] 修复契约不一致问题并更新 OpenAPI 文档。
10. [x] 产出联调问题清单与关闭记录（`docs/integration-issues.md`）。

### 并行任务 P8-B：端到端验收用例

- Owner: QA
- 依赖：P8-A step 4
- 技术栈决策：
  - E2E 测试：API 端到端（pytest + TestClient）+ 浏览器 E2E（Playwright）
  - CI 平台：GitHub Actions
  - 测试数据：复用 `seed.py` + pytest fixture
- 串行任务：
1. [x] 设计 MVP 验收用例矩阵：
   - **Dashboard 流**：加载统计、Agent 状态显示
   - **任务管理流**：创建任务 → 分配 Agent → 状态流转 → 完成
   - **对话交互流**：发送消息 → Agent 响应 → 工具调用透明 → 用户打断
   - **文件权限流**：设置权限 → 权限继承验证
   - **失败恢复流**：任务失败 → 自动重试 → 人工干预
2. [x] 建立 API E2E 自动化（`tests/e2e/`）：
   - `test_e2e_dashboard.py`：统计数据正确性
   - `test_e2e_task_lifecycle.py`：任务全生命周期
   - `test_e2e_conversation.py`：WebSocket 对话流
   - `test_e2e_files.py`：文件权限继承
3. [x] 建立浏览器 E2E 自动化（`tests/e2e_browser/`）：
   - 核心 happy path：登录 → Dashboard → 创建任务 → 对话 → 完成
4. [x] 执行回归并归档报告（`docs/e2e-report.md`）。
5. [x] 对未覆盖风险给出补救措施。

### 并行任务 P8-C：发布与运维交付

- Owner: Infra
- 依赖：P8-B step 4
- 技术栈决策：
  - 容器化：Docker + docker-compose（MVP 单机）
  - 生产数据库：SQLite（单用户），后续按需升级 PostgreSQL
  - 密钥管理：`.env` + docker secrets
  - 版本号：语义版本 + Git tag + CHANGELOG.md
- 串行任务：
1. [x] 编写 `Dockerfile`（后端）与 `docker-compose.yml`（前后端 + 数据库卷）。
2. [x] 固化发布脚本（`scripts/release.sh`）：版本号更新、构建、打标签。
3. [x] 输出部署文档（`docs/deployment.md`）：
   - 环境要求、配置清单、密钥清单
   - 启动命令、健康检查、日志查看
4. [x] 输出运维手册（`docs/operations.md`）：
   - 上线后 7 天监控指标（成功率、延迟、错误率、成本）
   - 值班规则与告警响应 SOP
   - 回滚预案与数据备份策略
5. [x] 创建首版里程碑标签（`v0.1.0`）并冻结 MVP 范围。

### 并行任务 P8-D：前端优化与打包

- Owner: Frontend
- 依赖：P8-A step 9
- 串行任务：
1. [x] 配置生产环境变量（`VITE_API_BASE_URL`）。
2. [x] 优化打包配置（代码分割、Tree Shaking、gzip）。
3. [x] 添加错误边界与加载状态处理。
4. [x] 输出前端构建文档（`frontend/README.md`）。

Phase 8 验收：
1. [x] 所有页面与后端 API 联调通过，无契约不一致问题。
2. [x] E2E 验收用例全部通过（API + 浏览器）。
3. [ ] Docker 部署可一键启动并通过健康检查（`docker compose config` 已通过，`docker compose up` 受本地 Docker 引擎不可用阻塞）。
4. [x] 文档、脚本、回滚预案齐备。
5. [x] 首版标签 `v0.1.0` 创建并冻结 MVP 范围。

---

## Phase 9: 前端 Bug 修复（2026-02-08 发现）

目标：修复前端体验测试中发现的 UI 与功能问题。

### 并行任务 P9-A：表单字段可访问性修复

- Owner: Frontend
- 依赖：无
- 优先级：低
- 串行任务：
1. [x] **Chat 页面**：为消息输入框 `<textarea>` 添加 `id="chat-message-input"` 和 `name="message"`。
2. [x] **Workflow 页面**（已禁用，待重构时一并修复）：为搜索框添加 `id` 和 `name` 属性。
3. [x] **Files 页面**：为搜索框和下拉选择器添加 `id`/`name` 属性（共 4 处）。
4. [x] **全局检查**：使用 `grep` 搜索所有 `<input>`、`<textarea>`、`<select>` 元素，确保都有 `id` 或 `name`。

### 并行任务 P9-B："+ Add Task" 按钮功能实现

- Owner: Frontend + Backend API
- 依赖：无
- 优先级：高
- 串行任务：
1. [x] 在 `TableView.vue` 中为 "+ Add Task" 按钮添加点击事件处理。
2. [x] 创建 `TaskCreateModal.vue` 组件（任务标题、描述、分配 Agent、优先级）。
3. [x] 调用 `POST /api/v1/tasks` 接口创建任务。
4. [x] 创建成功后刷新任务列表并关闭模态框。
5. [x] 添加表单验证与错误提示。

### 并行任务 P9-C：Files 页面下拉选项去重

- Owner: Frontend
- 依赖：无
- 优先级：低
- 串行任务：
1. [x] 检查 `FilesView.vue` 中 Agent access 下拉菜单的选项数据源。
2. [x] 移除重复的 "Readable" 选项。
3. [x] 添加单元测试验证下拉选项唯一性。

### 并行任务 P9-D：空按钮可访问性修复

- Owner: Frontend
- 依赖：无
- 优先级：中
- 串行任务：
1. [x] **Agents 页面**：为任务行操作按钮添加 `aria-label`（如 "Edit task"、"Delete task"）。
2. [x] **Workflow 页面**（已禁用，待重构时一并修复）：为工具栏按钮添加 `aria-label`。
3. [x] 全局审查所有图标按钮，确保有可访问性标签。

### 并行任务 P9-E：Dashboard "RECENT UPDATES" 数据渲染

- Owner: Frontend
- 依赖：无
- 优先级：低
- 串行任务：
1. [x] 检查 `DashboardView.vue` 中 `updates` 数据绑定逻辑。
2. [x] 验证 `GET /api/v1/updates` 返回数据格式与前端期望是否一致。
3. [x] 修复数据渲染问题或添加空状态提示。
4. [x] 添加加载状态指示器。

### 并行任务 P9-F：Workflow 页面重构

- Owner: Frontend + Backend API
- 依赖：P9-A, P9-D 完成后
- 优先级：中（待评估）
- 串行任务：
1. [x] 评估 Workflow 页面需求：是否需要后端 API 支持，还是纯前端可视化。
2. [x] 结论：当前采用纯前端可视化方案，无需新增 `GET/PUT /workflows/{id}`。
3. [x] 移除 mock 数据，改为从后端 API 获取真实工作流数据。
4. [x] 确保 Agent 名称与后端返回一致。
5. [x] 重新启用路由和导航链接。
6. [x] 补齐表单字段可访问性属性。

Phase 9 验收：
1. [x] 所有表单字段有 `id` 或 `name` 属性，控制台无相关警告。
2. [x] "+ Add Task" 按钮可正常创建任务。
3. [x] Files 页面下拉选项无重复。
4. [x] 所有图标按钮有 `aria-label`。
5. [x] Dashboard "RECENT UPDATES" 正确显示数据或空状态。
6. [x] Workflow 页面重构完成后重新启用。

---

## 关键路径与并行建议

关键路径：
1. `P2-B` -> `P3-A` -> `P3-C0` -> `P3-C` -> `P4-C` -> `P6-A` -> `P7-A` -> `P8-A` -> `P8-B`

并行优先级建议：
1. 优先保证数据模型与状态机正确性（先正确，再并发）。
2. 工具层与观测层尽早并行，避免后期排障成本爆炸。
3. 每个 Phase 结束前必须执行一次“全链路冒烟”。
