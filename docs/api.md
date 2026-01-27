# API 设计文档

## 概述

BeeBeeBrain 提供 REST API 和 WebSocket 接口,支持前端实时监听和交互。

---

## REST API

### 基础信息

- **Base URL:** `http://localhost:3000/api`
- **Content-Type:** `application/json`
- **认证方式:** API Token (TBD)

---

## 端点列表

### 1. 项目管理

#### 创建项目

```http
POST /api/projects
```

**请求体:**
```json
{
  "name": "My Awesome App",
  "description": "A task management app",
  "techStack": "nextjs"  // 可选: nextjs, vue, react (默认: nextjs)
}
```

**响应:**
```json
{
  "id": "proj_1234567890",
  "name": "My Awesome App",
  "status": "initializing",
  "createdAt": "2024-01-27T10:00:00Z",
  "repository": {
    "url": "file:///path/to/worktrees/proj_1234567890",
    "branch": "main"
  }
}
```

#### 获取项目详情

```http
GET /api/projects/:projectId
```

**响应:**
```json
{
  "id": "proj_1234567890",
  "name": "My Awesome App",
  "description": "A task management app",
  "status": "running",
  "createdAt": "2024-01-27T10:00:00Z",
  "techStack": {
    "framework": "Next.js",
    "language": "TypeScript",
    "styling": "TailwindCSS",
    "orm": "Prisma"
  },
  "agents": [
    {
      "id": "agent_fe_1",
      "role": "frontend",
      "status": "idle",
      "currentTask": null
    },
    {
      "id": "agent_be_1",
      "role": "backend",
      "status": "running",
      "currentTask": {
        "id": "task_001",
        "title": "Create user API",
        "progress": 0.6
      }
    }
  ],
  "statistics": {
    "totalTasks": 10,
    "completedTasks": 3,
    "runningTasks": 2,
    "pendingTasks": 5
  }
}
```

#### 列出所有项目

```http
GET /api/projects
```

**查询参数:**
- `status`: `initializing` | `running` | `completed` | `failed`
- `page`: 页码 (默认: 1)
- `limit`: 每页数量 (默认: 20)

**响应:**
```json
{
  "projects": [
    {
      "id": "proj_1234567890",
      "name": "My Awesome App",
      "status": "running",
      "createdAt": "2024-01-27T10:00:00Z"
    }
  ],
  "total": 1,
  "page": 1,
  "limit": 20
}
```

---

### 2. 任务管理

#### 提交需求

```http
POST /api/projects/:projectId/requests
```

**请求体:**
```json
{
  "prompt": "Create a task management app with user authentication",
  "priority": "high"  // low | medium | high
}
```

**响应:**
```json
{
  "requestId": "req_001",
  "status": "analyzing",
  "estimatedTasks": 12,
  "estimatedDuration": "15-20 minutes"
}
```

#### 获取任务列表

```http
GET /api/projects/:projectId/tasks
```

**查询参数:**
- `status`: `pending` | `running` | `completed` | `failed`
- `agentId`: 筛选特定 Agent 的任务

**响应:**
```json
{
  "tasks": [
    {
      "id": "task_001",
      "title": "Setup Next.js project",
      "description": "Initialize Next.js with TypeScript and TailwindCSS",
      "status": "completed",
      "agentId": "agent_fe_1",
      "dependencies": [],
      "priority": 1,
      "startedAt": "2024-01-27T10:05:00Z",
      "completedAt": "2024-01-27T10:07:30Z",
      "duration": 150,  // 秒
      "outputs": [
        {
          "type": "file",
          "path": "package.json",
          "action": "created"
        },
        {
          "type": "file",
          "path": "tsconfig.json",
          "action": "created"
        }
      ]
    },
    {
      "id": "task_002",
      "title": "Create user model",
      "description": "Define User schema in Prisma",
      "status": "running",
      "agentId": "agent_be_1",
      "dependencies": ["task_001"],
      "priority": 2,
      "startedAt": "2024-01-27T10:08:00Z",
      "progress": 0.4,
      "logs": [
        {
          "timestamp": "2024-01-27T10:08:05Z",
          "level": "info",
          "message": "Analyzing user requirements..."
        },
        {
          "timestamp": "2024-01-27T10:08:10Z",
          "level": "info",
          "message": "Generating Prisma schema..."
        }
      ]
    },
    {
      "id": "task_003",
      "title": "Create login page",
      "description": "Build login form with validation",
      "status": "pending",
      "agentId": null,  // 尚未分配
      "dependencies": ["task_002"],
      "priority": 3,
      "estimatedStart": "2024-01-27T10:15:00Z"
    }
  ],
  "total": 12,
  "byStatus": {
    "pending": 5,
    "running": 2,
    "completed": 3,
    "failed": 0
  }
}
```

#### 获取任务详情

```http
GET /api/projects/:projectId/tasks/:taskId
```

**响应:**
```json
{
  "id": "task_002",
  "title": "Create user model",
  "description": "Define User schema in Prisma",
  "status": "running",
  "agentId": "agent_be_1",
  "dependencies": ["task_001"],
  "dependents": ["task_003", "task_004"],  // 依赖此任务的任务
  "priority": 2,
  "startedAt": "2024-01-27T10:08:00Z",
  "progress": 0.4,
  "logs": [
    {
      "timestamp": "2024-01-27T10:08:05Z",
      "level": "info",
      "message": "Analyzing user requirements..."
    }
  ],
  "files": [
    {
      "path": "prisma/schema.prisma",
      "status": "modified",
      "diff": "@@ -1,5 +1,10 @@\n+model User {\n+  id    Int @id @default(autoincrement())\n+  email String @unique\n+}"
    }
  ]
}
```

#### 取消任务

```http
POST /api/projects/:projectId/tasks/:taskId/cancel
```

**响应:**
```json
{
  "id": "task_002",
  "status": "cancelled",
  "cancelledAt": "2024-01-27T10:10:00Z"
}
```

#### 重试失败任务

```http
POST /api/projects/:projectId/tasks/:taskId/retry
```

**响应:**
```json
{
  "id": "task_002",
  "status": "pending",
  "retryCount": 1
}
```

---

### 3. Agent 管理

#### 列出所有 Agents

```http
GET /api/agents
```

**响应:**
```json
{
  "agents": [
    {
      "id": "agent_fe_1",
      "name": "Frontend Expert",
      "role": "frontend",
      "skills": ["vue", "react", "typescript", "tailwind"],
      "status": "idle",
      "currentProject": "proj_1234567890",
      "statistics": {
        "totalTasks": 45,
        "completedTasks": 42,
        "averageDuration": 180
      }
    },
    {
      "id": "agent_be_1",
      "name": "Backend Expert",
      "role": "backend",
      "skills": ["nodejs", "express", "prisma", "postgresql"],
      "status": "running",
      "currentProject": "proj_1234567890",
      "currentTask": "task_002",
      "statistics": {
        "totalTasks": 38,
        "completedTasks": 35,
        "averageDuration": 200
      }
    }
  ]
}
```

#### 获取 Agent 详情

```http
GET /api/agents/:agentId
```

**响应:**
```json
{
  "id": "agent_fe_1",
  "name": "Frontend Expert",
  "role": "frontend",
  "skills": ["vue", "react", "typescript", "tailwind"],
  "status": "running",
  "currentProject": "proj_1234567890",
  "currentTask": {
    "id": "task_005",
    "title": "Create dashboard layout",
    "progress": 0.6
  },
  "worktree": {
    "path": "/path/to/worktrees/agent_fe_1",
    "branch": "shadow/agent-fe-1/task-005"
  },
  "recentActivity": [
    {
      "taskId": "task_004",
      "title": "Create button component",
      "completedAt": "2024-01-27T09:50:00Z",
      "duration": 120
    }
  ],
  "statistics": {
    "totalTasks": 45,
    "completedTasks": 42,
    "failedTasks": 1,
    "averageDuration": 180
  }
}
```

---

### 4. 文件管理

#### 获取文件内容

```http
GET /api/projects/:projectId/files/*
```

**示例:** `GET /api/projects/proj_001/files/src/components/Button.tsx`

**查询参数:**
- `ref`: 分支或 commit (默认: main)

**响应:**
```json
{
  "path": "src/components/Button.tsx",
  "content": "export function Button() {\n  return <button>Click me</button>\n}",
  "language": "typescript",
  "size": 68,
  "lastModified": "2024-01-27T10:05:00Z"
}
```

#### 更新文件内容

```http
PUT /api/projects/:projectId/files/*
```

**请求体:**
```json
{
  "content": "export function Button({ children }) {\n  return <button>{children}</button>\n}",
  "message": "Add children prop to Button"
}
```

**响应:**
```json
{
  "success": true,
  "commit": "abc123",
  "file": {
    "path": "src/components/Button.tsx",
    "size": 95
  }
}
```

#### 获取文件树

```http
GET /api/projects/:projectId/filetree
```

**查询参数:**
- `path`: 根路径 (默认: /)
- `ref`: 分支 (默认: main)

**响应:**
```json
{
  "path": "/",
  "type": "directory",
  "children": [
    {
      "name": "src",
      "type": "directory",
      "path": "src",
      "children": [
        {
          "name": "components",
          "type": "directory",
          "path": "src/components"
        },
        {
          "name": "App.tsx",
          "type": "file",
          "path": "src/App.tsx",
          "language": "typescript"
        }
      ]
    },
    {
      "name": "package.json",
      "type": "file",
      "path": "package.json",
      "language": "json"
    }
  ]
}
```

---

### 5. Git 操作

#### 获取提交历史

```http
GET /api/projects/:projectId/commits
```

**查询参数:**
- `branch`: 分支名 (默认: main)
- `limit`: 数量 (默认: 20)

**响应:**
```json
{
  "commits": [
    {
      "hash": "abc123",
      "author": "agent_fe_1",
      "message": "Create Button component",
      "timestamp": "2024-01-27T10:05:00Z",
      "branch": "shadow/agent-fe-1/task-004"
    }
  ]
}
```

#### 合并分支

```http
POST /api/projects/:projectId/merge
```

**请求体:**
```json
{
  "source": "shadow/agent-fe-1/task-004",
  "target": "main"
}
```

**响应:**
```json
{
  "success": true,
  "conflicts": [],
  "commit": "def456"
}
```

**有冲突时:**
```json
{
  "success": false,
  "conflicts": [
    {
      "file": "src/App.tsx",
      "reason": "Both sides modified",
      "ours": "src/App.tsx (main)",
      "theirs": "src/App.tsx (shadow/agent-fe-1/task-004)"
    }
  ]
}
```

---

## WebSocket API

### 连接

```javascript
const socket = new WebSocket('ws://localhost:3000/ws')
```

### 认证

连接后发送认证消息:

```json
{
  "type": "auth",
  "token": "your-api-token"
}
```

### 订阅事件

```json
{
  "type": "subscribe",
  "events": ["agent:start", "agent:output", "file:created"],
  "projectId": "proj_1234567890"
}
```

---

### 事件类型

#### 1. Agent 启动

```json
{
  "type": "agent:start",
  "data": {
    "agentId": "agent_fe_1",
    "taskId": "task_005",
    "title": "Create dashboard layout",
    "timestamp": "2024-01-27T10:00:00Z"
  }
}
```

#### 2. Agent 输出

```json
{
  "type": "agent:output",
  "data": {
    "agentId": "agent_fe_1",
    "taskId": "task_005",
    "output": "Creating component structure...",
    "level": "info",  // debug | info | warn | error
    "timestamp": "2024-01-27T10:00:05Z"
  }
}
```

#### 3. 任务进度更新

```json
{
  "type": "task:progress",
  "data": {
    "taskId": "task_005",
    "progress": 0.5,
    "timestamp": "2024-01-27T10:00:10Z"
  }
}
```

#### 4. 文件创建

```json
{
  "type": "file:created",
  "data": {
    "taskId": "task_005",
    "path": "src/components/Dashboard.tsx",
    "content": "export function Dashboard() { ... }",
    "language": "typescript",
    "timestamp": "2024-01-27T10:00:15Z"
  }
}
```

#### 5. 文件修改

```json
{
  "type": "file:modified",
  "data": {
    "taskId": "task_005",
    "path": "src/components/Dashboard.tsx",
    "diff": "@@ -1,3 +1,5 @@\n export function Dashboard() {\n+  return <div>Dashboard</div>\n }",
    "timestamp": "2024-01-27T10:00:20Z"
  }
}
```

#### 6. 任务完成

```json
{
  "type": "task:complete",
  "data": {
    "taskId": "task_005",
    "agentId": "agent_fe_1",
    "status": "completed",
    "duration": 180,
    "files": [
      {
        "path": "src/components/Dashboard.tsx",
        "action": "created"
      }
    ],
    "timestamp": "2024-01-27T10:03:00Z"
  }
}
```

#### 7. 任务失败

```json
{
  "type": "task:failed",
  "data": {
    "taskId": "task_005",
    "agentId": "agent_fe_1",
    "error": "Type compilation failed",
    "logs": ["error TS2345: Argument of type 'string' is not assignable to type 'number'"],
    "timestamp": "2024-01-27T10:03:00Z"
  }
}
```

#### 8. 冲突检测

```json
{
  "type": "conflict:detected",
  "data": {
    "sourceBranch": "shadow/agent-fe-1/task-005",
    "targetBranch": "main",
    "conflicts": [
      {
        "file": "src/App.tsx",
        "reason": "Both sides modified"
      }
    ],
    "timestamp": "2024-01-27T10:05:00Z"
  }
}
```

#### 9. Agent 状态变化

```json
{
  "type": "agent:status",
  "data": {
    "agentId": "agent_fe_1",
    "oldStatus": "running",
    "newStatus": "idle",
    "timestamp": "2024-01-27T10:05:00Z"
  }
}
```

---

## 错误响应

所有 API 在出错时返回统一格式:

```json
{
  "error": {
    "code": "TASK_NOT_FOUND",
    "message": "Task with ID 'task_999' not found",
    "details": {
      "taskId": "task_999",
      "projectId": "proj_123"
    }
  }
}
```

### 常见错误码

| 错误码 | HTTP 状态 | 说明 |
|--------|----------|------|
| `UNAUTHORIZED` | 401 | 未授权或 token 无效 |
| `PROJECT_NOT_FOUND` | 404 | 项目不存在 |
| `TASK_NOT_FOUND` | 404 | 任务不存在 |
| `AGENT_NOT_FOUND` | 404 | Agent 不存在 |
| `INVALID_INPUT` | 400 | 请求参数无效 |
| `CONFLICT unresolved` | 409 | 存在未解决的合并冲突 |
| `INTERNAL_ERROR` | 500 | 服务器内部错误 |

---

## 速率限制

- **未认证:** 10 requests/minute
- **已认证:** 100 requests/minute
- **WebSocket:** 无限制

响应头:
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1706367600
```

---

## 版本控制

API 版本通过 URL 路径指定:

```
/api/v1/projects
/api/v2/projects  # 未来版本
```

当前版本: `v1`
