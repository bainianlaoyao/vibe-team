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

**核心概念: Task 作为 Agent DAG**

一个 Task 不是单一 Agent 的原子任务,而是**多个 Agent 协作的有向无环图 (DAG)**:

```typescript
interface AgentNode {
  id: string
  agentType: 'frontend' | 'backend' | 'design' | 'test'
  prompt: string
  // 该 Agent 节点需要的前置 Agent 节点
  dependsOn: string[]
}

interface AgentEdge {
  from: string  // AgentNode.id
  to: string    // AgentNode.id
  // 数据传递规则
  dataFlow?: {
    artifacts: string[]  // 传递哪些文件/结果
  }
}

interface Task {
  id: string
  title: string
  description: string

  // Task 间的依赖
  dependencies: string[]

  // ⭐ Task 内部的 Agent 执行图
  agentGraph: {
    nodes: AgentNode[]
    edges: AgentEdge[]
  }

  priority: number
  status: 'pending' | 'running' | 'completed' | 'failed'
}
```

**调度算法:**

```typescript
class AgentScheduler {
  // ⭐ 核心: 支持 Task 内部的 Agent 图调度
  async scheduleAgentGraph(
    task: Task,
    availableAgents: Agent[]
  ): Promise<ExecutionPlan> {
    // 1. 解析 agentGraph 的依赖关系
    const dag = this.buildAgentDAG(task.agentGraph)

    // 2. 拓扑排序,找出可并行的 Agent 层级
    const layers = this.topologicalSort(dag)

    // 3. 为每个 Agent 分配 Worktree
    const plan = this.allocateWorktrees(layers, availableAgents)

    return plan
  }

  // 当某个 Agent 完成时,触发依赖它的 Agent
  async onAgentComplete(
    agentId: string,
    task: Task
  ): Promise<void> {
    const blockedAgents = this.findDependentAgents(agentId, task)
    for (const agent of blockedAgents) {
      await this.injectArtifacts(agentId, agent)  // 注入产物
      await this.startAgent(agent)
    }
  }
}
```

**依赖解析示例:**

### Task 间依赖
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

### Task 内部的 Agent 依赖
```
Task: "创建电商产品页面"

Agent Graph:
├─ [Layer 1] 并行
│   ├─ Agent A (Design)  → 设计 UI 原型
│   └─ Agent B (Backend) → 创建 Product API
│
├─ [Layer 2] 等待 Layer 1
│   └─ Agent C (Frontend) → [接收 A, B 产物] → 实现页面
│
└─ [Layer 3] 验收
    └─ Agent D (Test) → 测试完整流程

执行时间线:
T=0s:   启动 Agent A, Agent B
T=30s:  Agent A 完成, Agent B 仍在运行
T=45s:  Agent B 完成 → 启动 Agent C (注入 A、B 的产物)
T=80s:  Agent C 完成 → 启动 Agent D
T=95s:  Agent D 完成 → Task 完成
```

---

### Task 生命周期

一个 Task 从创建到完成经历以下阶段:

#### 1. Planning (规划)

```typescript
class TaskPlanner {
  async plan(userRequest: string): Promise<Task> {
    // 使用 LLM 分析需求,生成 Agent 执行图
    const analysis = await this.analyzeRequest(userRequest)

    return {
      id: generateId(),
      title: analysis.title,
      description: userRequest,

      agentGraph: {
        nodes: analysis.requiredAgents,
        edges: analysis.dependencies
      },

      status: 'pending'
    }
  }
}
```

**示例:**
```
用户输入: "实现用户注册登录功能"

LLM 分析结果:
{
  "title": "实现用户认证系统",
  "requiredAgents": [
    { "id": "agent-backend", "agentType": "backend", "prompt": "...", "dependsOn": [] },
    { "id": "agent-design", "agentType": "design", "prompt": "...", "dependsOn": [] },
    { "id": "agent-frontend", "agentType": "frontend", "prompt": "...", "dependsOn": ["agent-backend", "agent-design"] },
    { "id": "agent-test", "agentType": "test", "prompt": "...", "dependsOn": ["agent-frontend"] }
  ],
  "dependencies": [
    { "from": "agent-backend", "to": "agent-frontend", "dataFlow": { "artifacts": ["api/auth.ts"] } },
    { "from": "agent-design", "to": "agent-frontend", "dataFlow": { "artifacts": ["design/login.fig"] } }
  ]
}
```

#### 2. Scheduling (调度)

```typescript
class TaskScheduler {
  async scheduleTask(task: Task): Promise<void> {
    // 为 Task 创建专属的 Task Worktree
    const taskWorktree = await this.worktreeManager.create(
      `task-${task.id}`,
      `shadow/task-${task.id}`
    )

    // 解析 Agent 图的层级
    const layers = await this.scheduler.buildAgentDAG(task.agentGraph)

    // 按层级启动 Agent
    for (const layer of layers) {
      // 同一层级的 Agent 并行启动
      await Promise.all(
        layer.map(agent => this.startAgent(agent, taskWorktree))
      )

      // 等待当前层级所有 Agent 完成
      await this.waitForLayer(layer)
    }
  }
}
```

#### 3. Execution (执行)

每个 Agent 在独立的 Worktree 中工作:

```typescript
class AgentExecutor {
  async executeAgent(
    agentNode: AgentNode,
    task: Task,
    worktreePath: string
  ): Promise<AgentResult> {
    // 1. 收集前置 Agent 的产物
    const artifacts = await this.collectArtifacts(agentNode, task)

    // 2. 生成 System Prompt (注入 Constitution + Skills)
    const systemPrompt = await this.generatePrompt(
      agentNode,
      artifacts
    )

    // 3. 调用 LLM
    const result = await this.callLLM(systemPrompt)

    // 4. 将生成的文件写入 Worktree
    await this.writeFiles(worktreePath, result.files)

    // 5. 提交到 Agent 分支
    await this.commitToBranch(worktreePath, agentNode.id)

    return result
  }

  async collectArtifacts(
    agentNode: AgentNode,
    task: Task
  ): Promise<Map<string, string>> {
    const artifacts = new Map()

    // 查找依赖此 Agent 的边
    const incomingEdges = task.agentGraph.edges.filter(
      e => e.to === agentNode.id
    )

    // 收集所有前置 Agent 的产物
    for (const edge of incomingEdges) {
      const sourceAgent = task.findAgent(edge.from)
      const sourceResult = await this.getAgentResult(sourceAgent.id)

      for (const artifact of edge.dataFlow.artifacts) {
        artifacts.set(
          artifact,
          sourceResult.files[artifact]
        )
      }
    }

    return artifacts
  }
}
```

#### 4. Validation (验收)

```typescript
class TaskValidator {
  async validate(task: Task): Promise<ValidationResult> {
    // 1. 运行测试 Agent (如果存在)
    const testAgent = task.agentGraph.nodes.find(
      n => n.agentType === 'test'
    )

    if (testAgent) {
      const testResult = await this.runTest(testAgent, task)
      if (!testResult.passed) {
        return { valid: false, errors: testResult.errors }
      }
    }

    // 2. 代码审查 Agent 检查质量
    const reviewResult = await this.codeReview(task)

    // 3. 构建检查
    const buildResult = await this.buildTask(task)

    return {
      valid: reviewResult.success && buildResult.success,
      errors: [
        ...reviewResult.errors,
        ...buildResult.errors
      ]
    }
  }
}
```

#### 5. Merging (合并)

```typescript
class TaskMerger {
  async merge(task: Task): Promise<MergeResult> {
    const taskBranch = `shadow/task-${task.id}`

    // 1. 尝试自动合并到 mainline
    const result = await this.worktreeManager.mergeIntoMain(
      taskBranch
    )

    if (result.success) {
      // 合并成功,清理 Worktree
      await this.worktreeManager.remove(
        this.getWorktreePath(task.id)
      )
      return result
    }

    // 2. 有冲突,尝试 AI 自动修复
    const aiFix = await this.aiResolveConflicts(result.conflicts)

    if (aiFix.success) {
      await this.worktreeManager.commit('AI resolved conflicts')
      return { success: true }
    }

    // 3. 需要人工介入
    return {
      success: false,
      conflicts: result.conflicts,
      requiresHuman: true
    }
  }
}
```

#### 完整流程图

```
┌─────────────────────────────────────────────────────────┐
│  1. Planning                                            │
│     用户输入 → LLM 分析 → 生成 Agent 图                  │
└─────────────────────────────────────────────────────────┘
                       │
                       ↓
┌─────────────────────────────────────────────────────────┐
│  2. Scheduling                                          │
│     创建 Task Worktree → 解析层级 → 准备启动             │
└─────────────────────────────────────────────────────────┘
                       │
                       ↓
┌─────────────────────────────────────────────────────────┐
│  3. Execution (Layer by Layer)                          │
│  ┌─────────────────────────────────────────────────┐   │
│  │ Layer 1: [Agent A, Agent B] 并行执行             │   │
│  │    ↓ 完成                                        │   │
│  │ Layer 2: [Agent C] 接收 A、B 产物 → 执行          │   │
│  │    ↓ 完成                                        │   │
│  │ Layer 3: [Agent D] 验收                          │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
                       │
                       ↓
┌─────────────────────────────────────────────────────────┐
│  4. Validation                                          │
│     运行测试 → 代码审查 → 构建检查                       │
└─────────────────────────────────────────────────────────┘
                       │
                       ↓
┌─────────────────────────────────────────────────────────┐
│  5. Merging                                             │
│     合并到 mainline → 冲突解决 → 清理 Worktree           │
└─────────────────────────────────────────────────────────┘
```

**关键特性:**

1. **层级并行**: 同一层级的 Agent 真正并行执行,充分利用资源
2. **自动产物注入**: Agent 间自动传递文件和代码,无需手动管理
3. **容错机制**: 某个 Agent 失败时,可以只重试该 Agent 而非整个 Task
4. **可观测性**: 每个层级完成后更新 UI,用户可见实时进度

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
