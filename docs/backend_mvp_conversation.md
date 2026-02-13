# BeeBeeBrain Agent Conversation 设计（P7）

本文沉淀人机协作对话（Agent Conversation）能力设计，面向实时交互、工具透明与会话恢复。

## 1. 背景与目标

产品设计要求用户不仅能“管理”Agent，还需与 Agent 进行实时协作：
- 当 Agent 偏离意图时，用户可通过对话纠偏而非仅靠 `pause/cancel`。
- 用户可对产物评论，触发 Agent 基于评论进行优化。
- 用户可与保持特定上下文的 Agent 进行讨论。

核心目标：在前端实现类 Claude Code 的即时对话体验，用户与 Agent 实时双向交互，执行过程透明可见，且可随时介入。

## 2. 实时对话核心能力

### 2.1 双向流式通信
- WebSocket 通道：`/ws/conversations/{id}` 建立持久连接。
- 消息类型：
  - `user.message`：用户发送文本
  - `assistant.chunk`：Agent 流式输出片段
  - `assistant.tool_call`：Agent 发起工具调用（透明展示）
  - `assistant.tool_result`：工具执行结果
  - `assistant.thinking`：Agent 思考过程（可选展示）
  - `assistant.request_input`：Agent 主动向用户提问
  - `user.interrupt`：用户打断当前生成
  - `session.heartbeat`：心跳保活

### 2.2 执行中交互
- Agent 执行任务时可通过 `request_input` 暂停并等待用户输入。
- 用户可在 Agent 输出过程中随时发送 `user.interrupt` 打断。
- 打断后 Agent 停止当前生成，等待用户下一条指令。

### 2.3 工具调用透明
- 每次工具调用通过 WebSocket 推送 `assistant.tool_call`（工具名、参数）。
- 工具执行结果通过 `assistant.tool_result` 推送。
- 前端可实时展示“Agent 正在读取文件 xxx”等状态。

### 2.4 会话恢复
- WebSocket 断线后可通过 `last_message_id` 重连并恢复。
- 服务端缓存最近 N 条消息，支持断点续传。
- 长时间断线后可通过 HTTP API 拉取完整历史。

## 3. 数据模型扩展

1. `conversations`
- `id`, `project_id`, `agent_id`, `task_id`（可空，关联任务上下文）
- `title`, `status`（`active`/`streaming`/`waiting_input`/`archived`）
- `created_at`, `updated_at`, `version`

2. `messages`
- `id`, `conversation_id`, `role`（`user`/`assistant`/`system`/`tool`）
- `message_type`（`text`/`tool_call`/`tool_result`/`request_input`/`interrupt`）
- `content`, `metadata_json`（工具调用参数、结果等）
- `token_count`, `created_at`
- `parent_message_id`（可空，支持分支对话）

3. `conversation_sessions`
- `id`, `conversation_id`, `client_id`
- `connected_at`, `disconnected_at`, `last_message_id`
- 用于 WebSocket 会话管理与断线恢复

4. `comments`（扩展现有表）
- 新增 `conversation_id` 字段，评论可触发对话

## 4. API 与 WebSocket 设计

### 4.1 对话管理（HTTP）
- `POST /api/v1/conversations`：创建对话（可关联 `task_id` 继承上下文）
- `GET /api/v1/conversations`：列出对话（按 project/agent/task 过滤）
- `GET /api/v1/conversations/{id}`：获取对话详情含消息历史
- `GET /api/v1/conversations/{id}/messages`：分页获取消息历史
- `DELETE /api/v1/conversations/{id}`：归档对话
- `POST /api/v1/tasks/{task_id}/run`：支持可选 `conversation_id`，将运行的 prompt 与结果摘要镜像写入该会话消息流（用于 Chat 历史可见）；若同一 task 已有活跃 run（`queued/running/retry_scheduled`）且 `idempotency_key` 不同，返回 `409 TASK_RUN_ALREADY_ACTIVE`

### 4.2 实时对话（WebSocket）
- `WS /ws/conversations/{id}`：建立 WebSocket 连接
- 连接参数：`?last_message_id=xxx`（断线恢复）、`?client_id=xxx`（客户端标识）
- 服务端推送：`assistant.chunk`、`assistant.tool_call`、`assistant.request_input` 等
- 客户端发送：`user.message`、`user.interrupt`、`user.input_response`

### 4.3 备用 SSE 通道
- `GET /api/v1/conversations/{id}/stream`：SSE 只读流（用于不支持 WebSocket 的场景）
- `POST /api/v1/conversations/{id}/messages`：配合 SSE 发送消息

### 4.4 评论触发对话
- `POST /api/v1/comments/{id}/reply`：基于评论创建对话并请求 Agent 响应

## 5. 实现任务拆分

### P7-A：对话数据模型与基础 CRUD
1. 新增 `conversations`、`messages`、`conversation_sessions` 表及 Alembic 迁移。
2. 新增 `ConversationRepository`、`MessageRepository`、`SessionRepository`。
3. 新增对话管理 API：`app/api/conversations.py`。
4. 新增回归测试：`tests/test_conversations_api.py`。

### P7-B：WebSocket 实时通道
1. 新增 WebSocket 端点：`app/api/ws_conversations.py`。
2. 实现消息协议：定义 `user.message`、`assistant.chunk`、`user.interrupt` 等消息格式。
3. 实现连接管理：心跳、断线检测、客户端标识。
4. 新增 WebSocket 回归：`tests/test_ws_conversations.py`。

### P7-C：流式 LLM 响应集成
1. 扩展 `ClaudeCodeAdapter` 支持流式响应回调（`on_chunk`、`on_tool_call`、`on_complete`）。
2. 新增 `ConversationExecutor`：协调 LLM 调用与 WebSocket 推送。
3. 流式输出实时写入 `messages` 表并推送 WebSocket。
4. 实现用户打断：收到 `user.interrupt` 时取消 LLM 请求。

### P7-D：执行中交互与工具透明
1. Agent 调用工具时推送 `assistant.tool_call`（工具名、参数摘要）。
2. 工具执行结果推送 `assistant.tool_result`。
3. 实现 `request_input`：Agent 暂停并通过 WebSocket 向用户提问。
4. 用户通过 `user.input_response` 回复后 Agent 继续执行。

### P7-E：任务上下文继承与会话恢复
1. 创建对话时可指定 `task_id`，自动注入任务描述、依赖摘要、执行历史。
2. 对话中 Agent 可调用工具（继承任务的 `enabled_tools_json`）。
3. 对话结果可选回写任务状态（如用户确认后从 `blocked -> todo`）。
4. 实现断线恢复：`last_message_id` 重连、消息缓存、历史补发。

### P7-F：评论触发响应
1. 扩展 `comments` 表增加 `conversation_id` 字段。
2. 新增 `POST /comments/{id}/reply` 创建对话并请求 Agent 响应。
3. Agent 响应后自动更新评论状态为 `addressed`。
4. 新增评论-对话联动回归测试。

## 6. 技术约束

1. WebSocket 协议：使用 FastAPI 原生 WebSocket 支持，JSON 消息格式。
2. 对话历史 token 预算：默认 8000 tokens，超出时自动裁剪早期消息。
3. 单次响应超时：复用 `default_timeout_seconds`（90s），超时自动推送错误。
4. 消息持久化：所有消息立即落库，支持断线续传。
5. 并发限制：单个对话同时仅允许一个活跃 WebSocket 连接。
6. 心跳间隔：30s，超过 90s 无响应视为断线。

## 7. 与现有模块的关系

| 模块 | 关系 |
|------|------|
| `task_runs` | 对话独立于 run，但可引用 run 上下文；`task.run` 可选绑定 `conversation_id` 将运行摘要写入 `messages`，以便 Chat 统一查看 |
| `inbox_items` | `request_input` 可触发创建对话而非仅等待表单提交 |
| `events` | 新增 `conversation.started`、`conversation.message.created`、`conversation.ended` 事件 |
| `SecureFileGateway` | 对话中 Agent 调用文件工具时复用安全边界 |
| `ClaudeCodeAdapter` | 扩展支持流式回调，复用认证与配置 |

## 8. 前端集成要点

1. WebSocket 连接管理：自动重连、心跳、断线提示。
2. 流式渲染：逐块追加 Agent 输出，支持 Markdown 实时渲染。
3. 工具调用展示：显示“Agent 正在执行 `read_file(path=xxx)`”。
4. 打断按钮：用户可随时点击“停止生成”。
5. 输入等待：Agent 发起 `request_input` 时，前端高亮输入框并提示用户。
