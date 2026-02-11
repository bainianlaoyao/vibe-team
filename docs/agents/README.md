# Agent Persona Guide

## 概述

BeeBeeBrain 采用 **文件系统优先** 的策略管理 Agent Persona（角色设定/系统提示词）。
所有的 Agent Persona 不存储在数据库中，而是以 Markdown 文件的形式存储在项目根目录的 `docs/agents/` 目录下。

这种设计允许：
1. **版本控制**：Persona 文件可以随代码一起提交到 Git，享受版本管理、Code Review 和回滚能力。
2. **开发者体验**：开发者可以使用喜欢的编辑器直接编辑 `.md` 文件，获得语法高亮和更好的编辑体验。
3. **热更新**：修改文件后，下一次 Agent 运行时会自动加载最新的 Persona，无需重启服务或调用 API 更新。

## 目录结构

```text
project_root/
├── docs/
│   └── agents/
│       ├── frontend_agent.md    # Frontend Agent 的设定
│       ├── backend_agent.md     # Backend Agent 的设定
│       └── planning_agent.md    # Planning Agent 的设定
└── ...
```

## 文件命名规范

- 文件名由 Agent 名称自动生成：
  - 转小写
  - 空格替换为下划线
  - 移除特殊字符
  - 后缀为 `.md`
- 示例：`"Frontend Agent"` -> `docs/agents/frontend_agent.md`

## 管理 Persona

### 方式一：直接编辑文件（推荐）

直接在 `docs/agents/` 目录下新建或修改 Markdown 文件。

```markdown
# Frontend Agent

You are an expert Vue.js developer...
```

### 方式二：通过 API 管理

后端 API 会自动处理文件操作：

1. **创建 Agent** (`POST /api/v1/agents`)：
   - 如果提供了 `initial_persona_prompt`，会自动创建对应的 `.md` 文件。
   - 如果未提供，会创建包含默认内容的 `.md` 文件。

2. **更新 Agent** (`PATCH /api/v1/agents/{id}`)：
   - 如果更新了 `name`，会自动重命名对应的文件（旧文件会被删除）。
   - 如果更新了 `initial_persona_prompt`，会覆盖文件内容。

3. **直接读写 Persona**：
   - `GET /api/v1/agents/{id}/persona`：读取文件内容。
   - `PUT /api/v1/agents/{id}/persona`：直接写入文件内容。

4. **删除 Agent** (`DELETE /api/v1/agents/{id}`)：
   - 对应的 Persona 文件会被自动删除。

## 最佳实践

1. **结构化 Prompt**：建议在 Markdown 中使用清晰的标题结构，如 `## Role`、`## Capabilities`、`## Constraints`。
2. **提交代码**：修改 Persona 后，请务必执行 `git add docs/agents/*.md` 并提交。
3. **不要手动删除**：尽量避免手动删除数据库中存在的 Agent 对应的文件，否则 API 读取时会报错（虽然 `PersonaLoader` 会提示文件缺失）。
