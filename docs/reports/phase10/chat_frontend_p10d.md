# Phase 10 P10-D 前端实现记录

更新时间：2026-02-11

## 1. 范围

1. 仅保留一条聊天实现路径：`/chat -> ChatInterface -> chat store`。
2. 移除未使用旧链路与兼容逻辑（breaking change）。
3. 对齐 Conversation Protocol v2（`protocol=v2 + last_sequence replay`）。

## 2. 关键改动

1. `frontend/src/stores/chat.ts`
   - 完整消费 `assistant.chunk/thinking/tool_call/tool_result/request_input/complete/session.state/session.system_event/message.replay`。
   - `request_input` 卡片状态流转：`awaiting -> pending -> acknowledged/error`。
   - `user.input_response` 绑定 `question_id`，并按 ACK 回填问题卡。
   - 重连携带 `last_sequence`，对 `payload.message_sequence` 做幂等去重。
   - streaming 文本按 `turn_id` 归并拼接。
2. `frontend/src/components/chat/MessageItem.vue`
   - 按 part 类型渲染文本、思考、工具调用、提问卡、系统事件。
3. `frontend/src/components/chat/InputRequestBlock.vue`
   - 新增提问交互卡，支持 options 快选与文本回答。
4. `frontend/src/views/ChatInterface.vue`
   - 增加连接状态和运行状态显示。
   - Stop 按钮由 runtime state 驱动（仅 `streaming` 可点击）。
   - 移除弹窗式输入确认路径，改为消息流内联交互。

## 3. 删除项（无兼容保留）

1. `frontend/src/stores/conversations.ts`
2. `frontend/src/services/websocket.ts`
3. `frontend/src/views/ChatView.vue`
4. `frontend/src/components/chat/ToolConfirmation.vue`
5. `frontend/src/services/api.ts` 中未使用的 `listMessages/createMessage` 前端调用逻辑
6. `frontend/src/types/index.ts` 中未使用的 `ConversationMessage`
