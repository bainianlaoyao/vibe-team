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

## 当前状态（2026-02-11）

1. **已完成阶段**：Phase 1-9 全部完成并验收通过。
2. **当前阶段**：Phase 10 进行中（4/6）- 聊天系统对齐 Claude Code 交互体验。
3. **关键风险**：现有 Chat 前端仅渲染 `assistant.chunk`/`assistant.complete`，工具透明、输入请求、系统事件和问题回填未形成完整闭环。

---

## 已完成阶段快速索引

- **Phase 1**（工程基线与骨架，2026-02-06 完成）：项目脚手架、代码规范、数据库迁移机制 ✓
- **Phase 2**（领域模型与核心 API）：任务/Agent/收件箱 CRUD + 事件流推送 ✓
- **Phase 3**（编排与执行引擎）：状态机、LLM 适配、失败恢复、人工干预 ✓
- **Phase 4**（上下文系统与工具治理）：安全边界、上下文构建、CLI 工具、计划同步 ✓
- **Phase 5**（观测、告警与稳定性）：结构化日志（structlog）、指标看板、卡死检测、审计演练 ✓
- **Phase 6**（后端验收）：API 调用器、恢复回归套件、极简调试面板 ✓
- **Phase 7**（人机协作对话）：数据模型、WebSocket 实时通道、流式 LLM、工具透明、评论触发 ✓
- **Phase 8**（联调、验收与发布，4/5）：前端 API 基础、联调、E2E 验收、前端优化（Docker 实跑待本地引擎可用）
- **Phase 9**（前端 Bug 修复，2026-02-08 完成）：表单可访问性、Add Task 功能、下拉去重、Dashboard 渲染、Workflow 重构 ✓

---

## Phase 10: 聊天系统对齐 Claude Code 交互体验（2026-02-11 新增，进行中）

目标：基于现有 `claude-agent-sdk` 接入，补齐并复刻 Claude Code 的关键交互逻辑与输出体验，重点实现 `ask userquestion`（项目内统一为 `request_input`）闭环。

### 10.1 背景与上下文（基于 2026-02-11 代码审计）

1. 后端已实现基础会话通道，但 Claude 事件采样不足，当前适配层主要消费 `AssistantMessage` 与 `ResultMessage`，未完整利用 `UserMessage/SystemMessage/StreamEvent` 的可视化信号。
2. WebSocket 协议已预留 `assistant.tool_call`、`assistant.tool_result`、`assistant.request_input`、`assistant.thinking` 等类型，但前端 Chat store 仅消费 `assistant.chunk`、`assistant.complete`、`session.error`。
3. `user.input_response` 目前作为普通用户消息继续执行，尚未按 `tool_use_id` 建立“问题-回答-工具结果”关联回填，`ask userquestion` 交互语义不完整。
4. `user.interrupt` 目前主要触发本地 cancel_event，未完全走 SDK 控制通道中断，和 Claude Code 的可中断行为仍有偏差。
5. 现有 `request_input` 已能创建 `inbox_items(await_user_input)`，但“对话内提问卡片 + 实时回答 + 继续执行”的产品闭环未形成。

### 10.2 范围与非目标

范围：
1. 对齐 Claude 事件到 BeeBeeBrain 对话协议的映射与持久化。
2. 补齐 `ask userquestion/request_input` 端到端交互链路（后端执行器、WebSocket 协议、前端渲染）。
3. 复刻 Claude Code 关键交互体验：流式输出、工具透明、提问阻塞、用户回答恢复、打断。

非目标（本 Phase 不做）：
1. 不做“100% 像素级”复制 Claude Code UI，优先保证交互语义一致与可恢复性。
2. 不改变现有核心任务状态机定义（`todo/running/review/...`），仅增强对话链路。
3. 不引入破坏性迁移；如需 schema 扩展，遵循 expand/contract 向后兼容策略。

### 计划里程碑（预计 1-2 周）

1. M1（第 1-2 天）：完成 Claude SDK 事件采样与协议映射矩阵，冻结 v2 协议字段。
2. M2（第 3-5 天）：完成后端执行器改造与 `ask userquestion` 闭环。
3. M3（第 6-8 天）：完成前端 Chat 交互复刻（多事件渲染 + 输入请求卡片 + 打断/恢复）。
4. M4（第 9-10 天）：完成回归、E2E、压测与灰度开关接入。
5. M5（第 11-12 天）：完成联调验收、文档更新与主干合并。

### 并行任务 P10-A：协议与事件映射基线（Conversation Protocol v2）

- Owner: Runtime + LLM
- 依赖：Phase 7 完成
- 优先级：高
- 串行任务：
1. [x] 梳理 `claude-agent-sdk` 消息类型与控制请求（含 `can_use_tool`/`interrupt`）并形成映射矩阵。
2. [x] 定义 Conversation WS v2 事件契约（统一字段：`conversation_id`、`turn_id`、`sequence`、`timestamp`、`trace_id`）。
3. [x] 在后端保留 `raw_event`（可选裁剪）以支持调试与问题复盘。
4. [x] 规范 `message.replay` 的事件重放行为（按 sequence 幂等补发）。
5. [x] 增加版本协商与 feature flag：`CHAT_PROTOCOL_V2_ENABLED`（默认关闭）。
6. [x] 产出文档：`docs/reports/phase10/conversation_protocol_v2.md`。

### 并行任务 P10-B：`ask userquestion` / `request_input` 闭环

- Owner: Runtime + Backend API
- 依赖：P10-A step 2
- 优先级：最高
- 串行任务：
1. [x] 统一问题标识：`question_id == tool_use_id`，贯穿 `assistant.request_input` 与 `user.input_response`。
2. [x] 扩展 `assistant.request_input` payload（`question_id/question/options/required/metadata`）。
3. [x] 扩展 `user.input_response` payload（`question_id/answer/resume_task`）并校验必填关系。
4. [x] 后端将输入回答按 `parent_tool_use_id + tool_use_result` 语义回填到 Claude SDK，而非仅作为普通文本消息。
5. [x] 保持与收件箱联动：可选创建或关联 `await_user_input` 项，支持跨页面继续处理。
6. [x] 增加异常分支：无效 `question_id`、重复回答、超时未答、会话已中断。

### 并行任务 P10-C：执行器改造为长连接交互模式

- Owner: Runtime
- 依赖：P10-A step 2
- 优先级：高
- 串行任务：
1. [x] 将“单次 `query + receive_response`”改为“会话级 `ClaudeSDKClient` 长连接 + 多轮消息泵”。
2. [x] 建立对话级状态机：`active/streaming/waiting_input/interrupted/error`。
3. [x] `user.interrupt` 对接 SDK 原生 `interrupt()` 控制通道。
4. [x] 强化并发控制：同一 conversation 仅允许一个活跃执行回合，重复消息进入队列或拒绝。
5. [x] 补齐断线重连后的恢复策略（session 恢复 + 未完成回合收敛）。
6. [x] 对接结构化日志，记录 turn 级耗时、错误、取消原因与工具链路。

### 并行任务 P10-D：前端 Chat 界面与交互复刻

- Owner: Frontend
- 依赖：P10-A step 2, P10-B step 2
- 优先级：高
- 串行任务：
1. [x] 改造 `chat` store，完整消费 `assistant.tool_call/tool_result/thinking/request_input/message.replay`。
2. [x] Chat 消息区按类型渲染：文本流、思考块、工具调用卡、工具结果卡、提问卡、系统事件卡。
3. [x] 增加 `ask userquestion` 交互卡：展示问题、候选项（若有）、回答输入与提交状态。
4. [x] 回答提交后显示 pending 与 ack，按 `question_id` 回填对应提问卡。
5. [x] 打断按钮改为真实状态驱动（streaming 才可打断；中断后可继续提问）。
6. [x] 重连策略升级：携带 `last_sequence`，前端对 replay 幂等去重并修复流式拼接。
7. [x] 更新浏览器端可访问性与移动端布局，保证桌面/移动均可读可操作。

### 并行任务 P10-E：回归测试、E2E 与压力验证

- Owner: QA + Runtime + Frontend
- 依赖：P10-B, P10-C, P10-D
- 优先级：高
- 串行任务：
1. [ ] 后端单测：Claude 事件映射、`ask userquestion` 回填、`interrupt`、错误分支。
2. [ ] WebSocket 集成测试：消息顺序、replay、断线恢复、重复回答幂等。
3. [ ] 前端单测：store reducer、消息归并、提问卡状态流转。
4. [ ] Playwright E2E：`user.message -> assistant.request_input -> user.input_response -> assistant.complete` 全链路。
5. [ ] 压测：并发会话与高频 chunk 下 UI 渲染和 WS 稳定性。
6. [ ] 质量门禁：`uv run ruff check .`、`uv run black --check .`、`uv run mypy app tests`、`uv run pytest`、前端构建与测试全通过。

### 并行任务 P10-F：灰度发布、观测与文档收敛

- Owner: Infra + Observability + Backend API
- 依赖：P10-E step 1-4
- 优先级：中
- 串行任务：
1. [ ] 引入运行开关：`CHAT_PROTOCOL_V2_ENABLED`，默认关闭，按环境灰度启用。
2. [ ] 增加观测指标：提问次数、提问响应耗时、中断率、重连恢复成功率、消息丢失率。
3. [ ] 增加关键审计事件：`conversation.input.requested`、`conversation.input.submitted`、`conversation.interrupted`。
4. [ ] 补齐运维手册与排障条目（协议不兼容、question_id 缺失、重复提交）。
5. [ ] 同步 `docs/` 与本文件 `tasks.md` 的最终验收记录，准备合并主干。

Phase 10 验收：
1. [ ] 前端可实时展示 Claude 交互关键信号：文本、思考、工具调用、工具结果、输入请求。
2. [ ] `ask userquestion/request_input` 形成闭环：提问 -> 回答 -> 继续执行，全程可追踪。
3. [ ] `user.interrupt` 可稳定中断正在执行的会话回合，且状态一致。
4. [ ] 断线重连后消息可补发且无重复渲染，conversation 状态可恢复。
5. [ ] 后端协议与前端渲染统一为 v2，不保留兼容路径。
6. [ ] 质量门禁与 E2E 通过，关键路径无 P0/P1 缺陷。
7. [ ] 文档（技术方案、运行手册、验收报告）与 `tasks.md` 同步完成。

---

## 关键路径与并行建议

**关键路径**：`P10-A → P10-B → P10-C → P10-D → P10-E → P10-F`

**并行优先级**：
1. 优先保证协议映射与 `request_input` 闭环正确性。
2. 前端改造与后端执行器可并行推进。
3. 每个 Milestone 结束前必须执行一次"全链路冒烟"。

---

## 任务管理接口补充计划（待排期，不在本次实现）

背景：
1. 前端 `agents/table` 与 `agents/kanban` 已接入现有 `GET /api/v1/updates` 的 `files_changed`。
2. 当前后端尚无任务级 `diffAdd/diffDel` 聚合接口，前端无法展示真实代码增删行统计。

计划：
1. [ ] 新增任务变更详情接口：`GET /api/v1/tasks/{task_id}/changes`，返回 `files_changed`、`diff_add`、`diff_del`、`last_changed_at`。
2. [ ] 新增任务变更汇总接口：`GET /api/v1/tasks/changes/summary?project_id=...`，用于 `table/kanban` 批量渲染，避免 N+1 请求。
3. [ ] 前端任务视图切换到新接口后，移除当前基于 `updates` 的近实时聚合兼容逻辑。
