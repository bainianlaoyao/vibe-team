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

## 当前状态（2026-02-07）

1. 项目总体状态：`Backend MVP 按计划推进中`。
2. Phase 1 状态：`已完成并验收通过（3/3）`。
3. Phase 2 状态：`已完成并验收通过（4/4）`。
4. Phase 3 状态：`已完成并验收通过（5/5）`。
5. Phase 4 状态：`已完成并验收通过（4/4）`。
6. 最近里程碑：
`backend/` 已完成安全边界、上下文构建器、CLI 工具命令回写与 `tasks.md` 视图同步闭环。

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
1. [ ] 实现无输出超时检测。
2. [ ] 实现重复动作哈希检测。
3. [ ] 实现错误速率阈值检测。
4. [ ] 命中阈值自动生成 `inbox_items(item_type=await_user_input)` 并附带诊断信息。
5. [ ] 编写误报/漏报评估测试。

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
1. [ ] 对关键 API 和工具调用补齐审计字段。
2. [ ] 演练常见故障：LLM 超时、数据库锁、文件权限错误。
3. [ ] 输出恢复 Runbook 与应急 SOP。
4. [ ] 固化回滚脚本与数据备份策略。

Phase 5 验收：
1. 关键问题可被检测并定位。
2. 成本与健康状态可在 UI 查询。
3. 故障演练后可按 SOP 恢复服务。

---

## Phase 6: 联调、验收与发布

目标：完成前后端联调、端到端验收和首版发布准备。

### 并行任务 P6-A：前后端联调

- Owner: Backend API + Frontend
- 依赖：Phase 5 完成
- 待决策清单（进入 Phase 6 前需确认）：
  - [ ] 前端脚手架：Vite + Vue 3（推荐）vs Nuxt 3
  - [ ] API 客户端生成策略：基于 OpenAPI schema 自动生成（openapi-typescript / orval）vs 手写 fetch/axios
  - [ ] 状态管理：Pinia（推荐）vs 纯 Composables
  - [ ] 后端 CORS 配置：`main.py` 中加入 `CORSMiddleware`
  - [ ] 认证方案：MVP 本地 token / API key header（最小实现）
  - [ ] SSE 前端消费：原生 EventSource API vs fetch stream
- 串行任务：
1. [ ] 联调任务列表、看板状态流、收件箱视图接口。
2. [ ] 联调运行日志流与干预操作。
3. [ ] 修复契约不一致问题并更新 API 文档。
4. [ ] 产出联调问题清单与关闭记录。

### 并行任务 P6-B：端到端验收用例

- Owner: QA
- 依赖：P6-A step 2
- 待决策清单（进入 Phase 6 前需确认）：
  - [ ] E2E 测试范围：纯 API 端到端（pytest + TestClient）vs 浏览器 UI 端到端 vs 两者兼有
  - [ ] 浏览器 E2E 框架（如需要）：Playwright（推荐，Python/JS 双支持）vs Cypress
  - [ ] CI 平台：GitHub Actions（推荐）vs GitLab CI
  - [ ] 测试数据管理：复用已有 `seed.py` + pytest fixture 工厂
- 串行任务：
1. [ ] 设计 MVP 验收用例（成功流、失败流、人工干预流）。
2. [ ] 建立自动化 E2E（可先覆盖核心 happy path）。
3. [ ] 执行回归并归档报告。
4. [ ] 对未覆盖风险给出补救措施。

### 并行任务 P6-C：发布与运维交付

- Owner: Infra
- 依赖：P6-B step 3
- 待决策清单（进入 Phase 6 前需确认）：
  - [ ] 容器化方案：Docker（推荐）vs Podman vs 直接 systemd
  - [ ] 编排方案：docker-compose（推荐，MVP 单机）vs K8s vs 云 PaaS（Fly.io / Railway）
  - [ ] CI/CD 平台：与 P6-B 统一（GitHub Actions 推荐）
  - [ ] 生产数据库：继续 SQLite（单用户场景可行）vs 升级 PostgreSQL（并发写入需求时）
  - [ ] 密钥管理：`.env` 文件 + docker secrets（MVP）vs Vault
  - [ ] 版本号策略：语义版本 + Git tag + CHANGELOG.md（已有）
  - [ ] 数据库迁移生产策略：Alembic upgrade（AGENTS.md 已约定 expand/contract 模式）
- 串行任务：
1. [ ] 固化发布脚本与版本号策略。
2. [ ] 输出部署文档、配置清单、密钥清单。
3. [ ] 输出上线后 7 天监控指标与值班规则。
4. [ ] 创建首版里程碑标签并冻结 MVP 范围。

Phase 6 验收：
1. MVP 主链路全通过。
2. 文档、脚本、回滚预案齐备。
3. 满足首版发布条件。

---

## 关键路径与并行建议

关键路径：
1. `P2-B` -> `P3-A` -> `P3-C0` -> `P3-C` -> `P4-C` -> `P6-A` -> `P6-B`

并行优先级建议：
1. 优先保证数据模型与状态机正确性（先正确，再并发）。
2. 工具层与观测层尽早并行，避免后期排障成本爆炸。
3. 每个 Phase 结束前必须执行一次“全链路冒烟”。
