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

## 3. 逻辑架构与职责

### 3.1 模块划分
1. API 网关层（FastAPI）
- 对外暴露 REST/WebSocket。
- 做参数校验、错误映射、请求级鉴权（MVP 可为本地 token）。

2. 任务与编排层（Orchestration）
- 维护任务状态机与依赖判定。
- 触发执行、暂停、重试、人工干预。

3. Agent 执行层（Execution Pool）
- 封装 OpenAI/Anthropic 调用。
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
- `id`, `task_id`, `agent_id`, `run_status`, `attempt`, `started_at`, `ended_at`, `error_code`, `error_message`, `token_in`, `token_out`, `cost_usd`, `version`

6. `inbox_items`
- `id`, `project_id`, `source_type`, `source_id`, `category`（needs_review/blocked/risk）, `title`, `content`, `status`（open/resolved/escalated）, `created_at`, `resolved_at`, `resolver`, `version`

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
1. `GET /api/v1/events/stream`（SSE 或 WebSocket）
2. `GET /api/v1/runs/{run_id}/logs`

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
- 所有路径必须在项目根目录白名单内。
- 禁止 `..` 跳转与符号链接越界（需要 realpath 校验）。
- 限制单次读取大小和文本类型。

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
