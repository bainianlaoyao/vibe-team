# 系统架构设计文档

## 概述

BeeBeeBrain 采用**微内核架构 (Microkernel Architecture)**, 将系统分为核心引擎和可插拔的 Agent。

---

## 核心架构图

```
┌─────────────────────────────────────────────────────────────┐
│                     User Interface (Vue 3)                   │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐             │
│  │  Dashboard │  │  Log Stream│  │File Preview│             │
│  └────────────┘  └────────────┘  └────────────┘             │
└─────────────────────────────────────────────────────────────┘
                            │ WebSocket / REST
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                    Core Engine (Node.js)                     │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              Agent Scheduler (调度器)                  │  │
│  │  - Task Distribution                                  │  │
│  │  - Dependency Resolution                              │  │
│  │  - Lifecycle Management                               │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │           Knowledge System (知识系统)                  │  │
│  │  - Constitution (L1)                                  │  │
│  │  - Skills Library (L2)                                │  │
│  │  - AST Indexer                                        │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │         Worktree Manager (Git 工作区管理)              │  │
│  │  - Branch Isolation                                   │  │
│  │  - Conflict Detection                                 │  │
│  │  - Merge Orchestrator                                 │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            │
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                   Execution Layer                            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │ Agent A  │  │ Agent B  │  │ Agent C  │  │ Agent D  │    │
│  │(Frontend)│  │(Backend) │  │(Design)  │  │(Test)    │    │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘    │
│        │             │             │             │          │
│        └─────────────┴─────────────┴─────────────┘          │
│                      Git Worktrees                          │
└─────────────────────────────────────────────────────────────┘
```

---

## 模块详解

### 1. Agent Scheduler (调度器)

**职责:**
- 管理任务队列
- 分配任务给合适的 Agent
- 处理任务依赖关系
- 监控任务执行状态

**核心算法:**

```typescript
interface Task {
  id: string
  dependencies: string[]
  requiredSkills: string[]
  priority: number
  status: 'pending' | 'running' | 'completed' | 'failed'
}

class AgentScheduler {
  async schedule(tasks: Task[]): Promise<Map<Agent, Task[]>> {
    // 1. 构建依赖图
    const depGraph = this.buildDependencyGraph(tasks)

    // 2. 拓扑排序,找出可并行执行的任务
    const parallelTasks = this.topologicalSort(depGraph)

    // 3. 根据技能和负载分配任务
    const assignments = this.assignToAgents(parallelTasks)

    return assignments
  }
}
```

**依赖解析示例:**

```
Task A (无依赖)
Task B (依赖 A)
Task C (依赖 A)
Task D (依赖 B, C)

执行顺序:
Round 1: [A]
Round 2: [B, C]  # 并行!
Round 3: [D]
```

---

### 2. Worktree Manager (工作区管理)

**核心概念:**

Git Worktree 允许多个分支同时检出,共享同一个 Git 仓库:

```bash
# 主仓库
/path/to/main-clone/
  ├─ .git/
  └─ (main branch files)

# Agent 工作区 (轻量级, 共享 .git 对象)
/path/to/worktrees/
  ├─ agent-a/  -> frontend-branch
  ├─ agent-b/  -> backend-branch
  └─ agent-c/  -> design-branch
```

**实现细节:**

```typescript
class WorktreeManager {
  private basePath: string
  private mainRepoPath: string

  async createWorktree(agentId: string, branchName: string): Promise<string> {
    const worktreePath = path.join(this.basePath, agentId)

    // 使用 git worktree create
    await execGit([
      'worktree',
      'add',
      worktreePath,
      '-b',
      branchName
    ])

    return worktreePath
  }

  async mergeIntoMain(sourceBranch: string): Promise<MergeResult> {
    // 1. 尝试自动合并
    const result = await execGit(['merge', sourceBranch, '--no-commit'])

    if (result.conflicts.length === 0) {
      // 无冲突,直接合并
      await execGit(['commit', '-m', `Merge ${sourceBranch}`])
      return { success: true }
    }

    // 2. 有冲突,返回冲突信息
    return {
      success: false,
      conflicts: result.conflicts
    }
  }
}
```

**冲突检测与解决:**

```typescript
interface Conflict {
  file: string
  ours: string  // main 分支的内容
  theirs: string // agent 分支的内容
  base: string  // 共同祖先
}

class ConflictResolver {
  async resolve(conflict: Conflict): Promise<Resolution> {
    // 策略 1: AI 自动合并
    const aiResult = await this.aiMerge(conflict)
    if (aiResult.confidence > 0.9) {
      return aiResult.resolution
    }

    // 策略 2: 人工介入
    return await this.promptUser(conflict)
  }
}
```

---

### 3. Knowledge System (知识系统)

**两层架构:**

#### L1: Constitution (核心宪法)

定义不可违背的规则:

```typescript
const constitution = {
  techStack: {
    framework: 'Next.js',
    language: 'TypeScript',
    styling: 'TailwindCSS',
    orm: 'Prisma'
  },

  structure: {
    components: 'src/components',
    pages: 'src/app', // App Router
    api: 'src/app/api',
    lib: 'src/lib',
    types: 'src/types'
  },

  rules: [
    '所有组件必须使用 TypeScript',
    'API 路由必须定义 Zod schema',
    '数据库变更必须通过 migration',
    '组件样式必须使用 TailwindCSS,禁止 inline style'
  ]
}

function generateSystemPrompt(userRequest: string): string {
  return `
You are an expert ${constitution.techStack.framework} developer.

TECH STACK:
${JSON.stringify(constitution.techStack, null, 2)}

DIRECTORY STRUCTURE:
${JSON.stringify(constitution.structure, null, 2)}

NON-NEGOTIABLE RULES:
${constitution.rules.map((r, i) => `${i + 1}. ${r}`).join('\n')}

USER REQUEST:
${userRequest}

Always follow these rules. Never deviate from the specified tech stack.
  `.trim()
}
```

#### L2: Skills Library (技能库)

基于 AST 的代码索引和查询:

```typescript
class SkillsLibrary {
  private astIndex: Map<string, ASTNode>

  async indexRepository(repoPath: string): Promise<void> {
    // 遍历所有 .ts, .tsx 文件
    const files = await glob('**/*.{ts,tsx}', { cwd: repoPath })

    for (const file of files) {
      const ast = this.parseFile(file)
      this.astIndex.set(file, ast)
    }
  }

  // 查找现有组件,避免重复创建
  findComponent(componentName: string): ComponentDefinition | null {
    for (const [file, ast] of this.astIndex) {
      const component = this.searchAST(ast, componentName)
      if (component) {
        return { file, definition: component }
      }
    }
    return null
  }

  // 查找数据模型
  findModel(modelName: string): PrismaModel | null {
    const schemaFile = this.astIndex.get('prisma/schema.prisma')
    if (!schemaFile) return null

    return this.searchModel(schemaFile, modelName)
  }

  // 查找 API 端点
  findEndpoint(path: string): APIEndpoint | null {
    const appDir = this.astIndex.get('src/app')
    if (!appDir) return null

    return this.searchRoute(appDir, path)
  }
}
```

**使用示例:**

```typescript
// Agent 执行任务前,先查询技能库
const skills = new SkillsLibrary()
await skills.indexRepository('/path/to/repo')

// 用户要求: "创建用户个人资料页面"
const existingComponent = skills.findComponent('UserProfile')
if (existingComponent) {
  // 组件已存在,建议修改而不是创建
  return {
    action: 'modify',
    target: existingComponent.file,
    reason: 'Component already exists'
  }
}

const userModel = skills.findModel('User')
if (!userModel) {
  // 数据模型不存在,需要先创建
  return {
    action: 'create-model-first',
    model: 'User',
    fields: ['id', 'email', 'name', 'avatar']
  }
}
```

---

## 数据流

### 典型工作流

```
1. 用户输入需求
   ↓
2. 需求分析 → 拆解为 Tasks
   ↓
3. 构建依赖图 → 识别可并行任务
   ↓
4. 为每个任务创建 Worktree
   ↓
5. 加载 Constitution + Skills → 生成 Prompt
   ↓
6. 分配给 Agent 执行
   ↓
7. Agent 生成代码 → 提交到 Worktree
   ↓
8. 检测冲突 → 自动/手动解决
   ↓
9. 合并到 Main 分支
   ↓
10. 更新 UI → 实时预览
```

### 实时通信 (WebSocket)

```typescript
// 前端订阅事件
socket.on('agent:start', (data: AgentStartEvent) => {
  dashboard.updateAgentStatus(data.agentId, 'running')
})

socket.on('agent:output', (data: AgentOutputEvent) => {
  logStream.append(data.output)
})

socket.on('file:created', (data: FileCreatedEvent) => {
  fileTree.addFile(data.path)
  preview.update(data.path, data.content)
})

socket.on('task:complete', (data: TaskCompleteEvent) => {
  dashboard.moveTicket(data.taskId, 'completed')
  dashboard.updateAgentStatus(data.agentId, 'idle')
})
```

---

## 扩展性设计

### 插件化 Agent

```typescript
interface AgentPlugin {
  name: string
  skills: string[]
  execute(task: Task, context: Context): Promise<Result>
}

class AgentRegistry {
  private plugins: Map<string, AgentPlugin> = new Map()

  register(plugin: AgentPlugin): void {
    this.plugins.set(plugin.name, plugin)
  }

  getAgentsForTask(task: Task): AgentPlugin[] {
    return Array.from(this.plugins.values()).filter(agent =>
      task.requiredSkills.some(skill => agent.skills.includes(skill))
    )
  }
}

// 使用示例
registry.register({
  name: 'frontend-expert',
  skills: ['vue-component', 'typescript', 'tailwind'],
  execute: async (task, ctx) => {
    // 执行前端任务
  }
})
```

### 自定义 Constitution

用户可以覆盖默认规则:

```typescript
const userConstitution = {
  overrides: {
    framework: 'Nuxt.js', // 覆盖默认的 Next.js
    language: 'JavaScript' // 覆盖默认的 TypeScript
  },

  customRules: [
    '使用 Composition API',
    '组件必须 <script setup> 语法'
  ]
}
```

---

## 性能优化

### 1. Worktree 复用

```typescript
class WorktreePool {
  private pool: Map<string, string> = new Map()

  async acquire(agentId: string): Promise<string> {
    if (this.pool.has(agentId)) {
      // 复用现有 worktree
      return this.resetWorktree(this.pool.get(agentId)!)
    }

    // 创建新的 worktree
    const path = await this.createWorktree(agentId)
    this.pool.set(agentId, path)
    return path
  }
}
```

### 2. 增量索引

```typescript
class IncrementalIndexer {
  private lastCommit: string

  async updateIndex(): Promise<void> {
    const currentCommit = await execGit('rev-parse HEAD')

    if (currentCommit === this.lastCommit) {
      return // 没有变化,跳过索引
    }

    const changedFiles = await execGit(
      `diff --name-only ${this.lastCommit} ${currentCommit}`
    )

    // 只索引变更的文件
    for (const file of changedFiles) {
      this.astIndex.delete(file)
      const ast = this.parseFile(file)
      this.astIndex.set(file, ast)
    }

    this.lastCommit = currentCommit
  }
}
```

---

## 安全考虑

### 1. Agent 沙箱

```typescript
class AgentSandbox {
  private allowedPaths: string[]

  async execute(agentId: string, command: string): Promise<void> {
    const worktreePath = this.getWorktreePath(agentId)

    // 验证路径在允许范围内
    if (!this.isPathSafe(command, worktreePath)) {
      throw new Error('Unsafe command detected')
    }

    // 在隔离环境中执行
    await this.execInSandbox(command, {
      cwd: worktreePath,
      env: { AGENT_ID: agentId }
    })
  }

  private isPathSafe(command: string, allowedPath: string): boolean {
    // 检查命令是否试图访问 allowedPath 之外的路径
    const parsed = this.parseCommand(command)
    return parsed.paths.every(p =>
      path.resolve(p).startsWith(path.resolve(allowedPath))
    )
  }
}
```

### 2. Prompt 注入防护

```typescript
function sanitizeUserInput(input: string): string {
  // 移除潜在的 prompt 注入
  return input
    .replace(/ignore\s+previous\s+instructions/gi, '')
    .replace(/disregard\s+above/gi, '')
    .replace(/system:\s*;/gi, '')
}
```

---

## 监控与调试

### 日志系统

```typescript
class Logger {
  private levels = ['debug', 'info', 'warn', 'error']

  log(level: string, agentId: string, message: string, meta?: any) {
    const entry = {
      timestamp: new Date().toISOString(),
      level,
      agentId,
      message,
      meta
    }

    // 输出到控制台
    console.log(JSON.stringify(entry))

    // 发送到前端
    socket.emit('log', entry)

    // 持久化到数据库
    await db.logs.create({ data: entry })
  }
}
```

### 性能指标

```typescript
class MetricsCollector {
  private metrics = new Map<string, number[]>()

  record(agentId: string, duration: number): void {
    if (!this.metrics.has(agentId)) {
      this.metrics.set(agentId, [])
    }
    this.metrics.get(agentId)!.push(duration)
  }

  getStats(agentId: string) {
    const durations = this.metrics.get(agentId) || []
    return {
      count: durations.length,
      avg: durations.reduce((a, b) => a + b, 0) / durations.length,
      min: Math.min(...durations),
      max: Math.max(...durations)
    }
  }
}
```

---

## 总结

BeeBeeBrain 的架构设计遵循以下原则:

1. **模块化** - 每个模块职责单一,易于维护和扩展
2. **可并行** - 通过 Worktree 实现真正的物理隔离
3. **可观测** - 完善的日志和指标系统
4. **安全性** - 沙箱隔离和输入验证
5. **可扩展** - 插件化的 Agent 系统
