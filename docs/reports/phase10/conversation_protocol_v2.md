# Conversation Protocol v2（Phase 10 A-C）

更新时间：2026-02-11

## 1. 目标与结论

1. 后端会话通道升级为 **纯 v2 协议**（breaking change），不再保留 v1/fallback。
2. 执行模型升级为 **会话级 `ClaudeSDKClient` 长连接 + 多轮消息泵**。
3. `ask userquestion`（统一命名 `request_input`）实现 `question_id == tool_use_id` 闭环。

## 2. 协议协商与开关

1. Feature flag：`CHAT_PROTOCOL_V2_ENABLED`（默认 `false`）。
2. WebSocket 必须携带：`?protocol=v2`。
3. 重连补发游标：`?last_sequence=<int>`（按消息 `sequence_num` 回放）。

## 3. WS v2 统一信封

所有服务端事件统一字段：

- `type`: 事件类型
- `conversation_id`: 会话 ID
- `turn_id`: 回合 ID（可空）
- `sequence`: WS 发包序号（连接内递增）
- `timestamp`: ISO8601 UTC
- `trace_id`: 追踪 ID
- `payload`: 事件载荷

备注：可回放事件在 `payload.message_sequence` 中携带持久化序号（`messages.sequence_num`）。

## 4. 事件映射矩阵（Claude SDK -> BeeBeeBrain v2）

### 4.1 Claude 消息类型映射

| Claude SDK 类型 | BeeBeeBrain v2 事件 | 持久化 message_type |
|---|---|---|
| `AssistantMessage` + `TextBlock` | `assistant.chunk` | `text` |
| `AssistantMessage` + `ThinkingBlock` | `assistant.thinking` | `text`（`metadata.thinking=true`） |
| `AssistantMessage` + `ToolUseBlock` | `assistant.tool_call` | `tool_call` |
| `AssistantMessage` + `ToolResultBlock` | `assistant.tool_result` | `tool_result` |
| `AssistantMessage` + `ToolUseBlock(name=request_input)` | `assistant.request_input` | `input_request` |
| `SystemMessage` | `session.system_event` | `text`（role=`system`） |
| `ResultMessage` | `assistant.complete` | 无额外 message（结束事件） |

### 4.2 Claude 控制请求映射

| Claude 控制通道 | BeeBeeBrain 行为 |
|---|---|
| `interrupt` | `user.interrupt` 触发 SDK `interrupt()`，回写 `conversation.interrupted` 事件并更新会话状态 |
| `can_use_tool` | 本阶段未启用 callback，保留在协议矩阵中作为后续扩展点 |

## 5. `request_input` 闭环

1. 提问：`assistant.request_input` payload
- `question_id`（=`tool_use_id`）
- `question`
- `options`
- `required`
- `metadata`
- `inbox_item_id`
- `deadline_at`

2. 回答：`user.input_response` payload
- `question_id`
- `answer`
- `resume_task`

3. 回填 SDK
- 通过 `parent_tool_use_id + tool_use_result` 写入 SDK 用户消息，而不是普通文本追加。

4. 收件箱联动
- 提问时创建/复用 `await_user_input` 项（`source_id=conversation:{id}:question:{question_id}`）。
- 回答后关闭对应收件箱项并写审计事件。

## 6. 状态机与并发控制

对话运行态：`active -> streaming -> waiting_input -> active`，中断/故障分别进入 `interrupted`/`error`。

并发策略：

1. 同一 conversation 仅一个活跃执行回合。
2. 后续输入进入有界队列（`MAX_TURN_QUEUE_SIZE`）。
3. 超出队列上限返回 `TURN_QUEUE_FULL`。

## 7. 重放与恢复

1. `message.replay` 基于 `last_sequence`（消息持久化序号）补发。
2. 回放消息具备幂等键：`payload.message_sequence`。
3. 断线收敛策略：连接关闭时停止 worker、断开 SDK、关闭 session；重连后按序回放持久化消息。

## 8. 原始事件保留（raw_event）

1. Claude 原始消息写入 `messages.metadata_json.raw_event`。
2. 超长原始事件进行裁剪（保留 `payload_preview` + `raw_size`）。
3. 用于联调复盘与问题诊断。

## 9. 关键错误分支

- `INVALID_QUESTION_ID`
- `DUPLICATE_INPUT_RESPONSE`
- `INPUT_TIMEOUT`
- `CONVERSATION_INTERRUPTED`
- `TURN_QUEUE_FULL`
- `PROTOCOL_VERSION_UNSUPPORTED`
- `CHAT_PROTOCOL_DISABLED`
