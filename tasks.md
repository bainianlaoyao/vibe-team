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

## 当前状态（2026-02-06）

1. 项目总体状态：`Backend MVP 按计划推进中`。
2. Phase 1 状态：`已完成并验收通过（3/3）`。
3. Phase 2 状态：`已完成并验收通过（4/4）`。
4. 最近里程碑：
`backend/` 可一键启动 API，`backend-quality` CI 检查链路已就绪并可通过，本地已验证数据库迁移可重复执行且数据不丢失。

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
1. [ ] 定义 `todo/running/review/done/blocked/failed/cancelled` 状态迁移表。
2. [ ] 实现调度器：按优先级与依赖关系挑选可执行任务。
3. [ ] 实现暂停、恢复、重试、取消等命令处理。
4. [ ] 为每次状态迁移写事件与 trace_id。
5. [ ] 为非法迁移编写回归测试。

### 并行任务 P3-B：LLM 适配层（OpenAI/Anthropic）

- Owner: LLM
- 依赖：P3-A step 1
- 串行任务：
1. [ ] 统一 LLM 客户端接口（请求、响应、错误映射）。
2. [ ] 实现 OpenAI 适配器并接入模型配置。
3. [ ] 实现 Anthropic 适配器并对齐 tool call 结构。
4. [ ] 记录 token 和成本到 `task_runs` 与 `api_usage_daily`。
5. [ ] 增加 provider 故障注入测试。

### 并行任务 P3-C0：运行可靠性基础准备

- Owner: Runtime
- 依赖：P3-A step 1
- 串行任务：
1. [ ] 定义 `task_runs` 运行状态枚举与字段契约（`attempt`、`idempotency_key`、`next_retry_at`）。
2. [ ] 搭建失败注入测试桩（超时、临时错误、进程重启中断）。
3. [ ] 补齐 run 级 repository 接口与事件写入契约。
4. [ ] 输出 P3-C 实施基线（状态图与恢复时序）。

### 并行任务 P3-C：运行生命周期与失败恢复

- Owner: Runtime
- 依赖：P3-A step 2, P3-B step 1, P3-C0 step 2
- 串行任务：
1. [ ] 实现 `task_runs` 创建、完成、失败、重试累计。
2. [ ] 加入超时和指数退避策略。
3. [ ] 加入幂等键（同一请求防重执行）。
4. [ ] 实现服务重启后的运行状态恢复。
5. [ ] 编写异常恢复端到端测试。

### 并行任务 P3-D：人工干预接口

- Owner: Backend API
- 依赖：P3-A step 3
- 串行任务：
1. [ ] 实现 `POST /tasks/{id}/pause|resume|retry`。
2. [ ] 实现广播指令接口（批量作用于多个运行任务）。
3. [ ] 干预动作全部写审计日志。
4. [ ] 编写并发干预冲突测试。

Phase 3 验收：
1. 任务可自动进入执行并稳定流转。
2. 失败可自动重试或人工恢复。
3. 干预操作对状态机一致性无破坏。

---

## Phase 4: 知识工具与上下文系统

目标：实现“无 RAG”的 Agent 自主检索闭环与文档索引能力。

### 并行任务 P4-A：安全文件访问层

- Owner: Document Service
- 依赖：Phase 2 完成
- 串行任务：
1. [ ] 实现根目录白名单和 realpath 校验。
2. [ ] 禁止路径穿越和符号链接越界。
3. [ ] 限制单次读取大小、文件类型和编码处理。
4. [ ] 编写安全测试（恶意路径、超大文件、二进制文件）。

### 并行任务 P4-B：知识检索工具实现

- Owner: Document Service
- 依赖：P4-A step 1
- 串行任务：
1. [ ] 实现 `list_path_tool`。
2. [ ] 实现 `read_file_tool`。
3. [ ] 实现 `search_project_files_tool`（文件名 + 内容关键字）。
4. [ ] 工具结果统一结构化（路径、摘要、命中片段）。
5. [ ] 工具调用性能测试（大目录场景）。

### 并行任务 P4-C：上下文组装器

- Owner: Orchestration
- 依赖：P3-B step 1, P4-B step 3
- 串行任务：
1. [ ] 组装初始上下文（persona + 任务 + 全局规则 + tasks 摘要）。
2. [ ] 接入工具调用循环，将工具结果回注 LLM。
3. [ ] 加入上下文裁剪策略（长度预算、优先级规则）。
4. [ ] 编写复杂任务场景测试（多轮 tool call）。

### 并行任务 P4-D：文档索引与导出器

- Owner: Data + Document Service
- 依赖：P4-B step 2
- 串行任务：
1. [ ] 建立 `documents` 的索引流程（扫描、增量更新）。
2. [ ] 同步 mandatory 文档列表给编排层。
3. [ ] 实现 `tasks.md` 导出器（从数据库生成人类可读计划视图）。
4. [ ] 编写导出一致性测试（数据库变更后自动刷新）。

Phase 4 验收：
1. Agent 能在项目目录中自主查找并读取上下文。
2. `tasks.md` 可按数据库状态稳定导出。
3. 文件访问策略可拦截常见越权路径。

---

## Phase 5: 观测、告警与稳定性

目标：建立可运营的后端运行质量体系。

### 并行任务 P5-A：结构化日志与链路追踪

- Owner: Observability
- 依赖：Phase 3 完成
- 串行任务：
1. [ ] 统一日志格式（JSON + trace_id + run_id + task_id）。
2. [ ] 建立日志分层（API、编排、执行、工具、安全）。
3. [ ] 接入日志查询接口（按任务/运行过滤）。
4. [ ] 编写日志完整性测试。

### 并行任务 P5-B：指标与成本看板数据

- Owner: Observability
- 依赖：P3-B step 4
- 串行任务：
1. [ ] 落库 `api_usage_daily` 与运行时延指标。
2. [ ] 提供聚合接口（按 provider/model/date 统计）。
3. [ ] 定义成本超阈值告警策略。
4. [ ] 编写统计正确性测试。

### 并行任务 P5-C：卡死检测与用户确认入箱

- Owner: Runtime
- 依赖：P3-C step 2
- 串行任务：
1. [ ] 实现无输出超时检测。
2. [ ] 实现重复动作哈希检测。
3. [ ] 实现错误速率阈值检测。
4. [ ] 命中阈值自动生成 `inbox_items(item_type=await_user_input)` 并附带诊断信息。
5. [ ] 编写误报/漏报评估测试。

### 并行任务 P5-D：安全审计与故障演练

- Owner: Security/Infra
- 依赖：P4-A step 3, P5-A step 1
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
- 串行任务：
1. [ ] 联调任务列表、看板状态流、收件箱视图接口。
2. [ ] 联调运行日志流与干预操作。
3. [ ] 修复契约不一致问题并更新 API 文档。
4. [ ] 产出联调问题清单与关闭记录。

### 并行任务 P6-B：端到端验收用例

- Owner: QA
- 依赖：P6-A step 2
- 串行任务：
1. [ ] 设计 MVP 验收用例（成功流、失败流、人工干预流）。
2. [ ] 建立自动化 E2E（可先覆盖核心 happy path）。
3. [ ] 执行回归并归档报告。
4. [ ] 对未覆盖风险给出补救措施。

### 并行任务 P6-C：发布与运维交付

- Owner: Infra
- 依赖：P6-B step 3
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


