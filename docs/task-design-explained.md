# Task 设计说明: 为什么 Task 是 Agent 树?

## 核心概念

在 BeeBeeBrain 中,**一个 Task 不是单个 Agent 的原子任务,而是多个 Agent 协作的有向无环图 (DAG)**。

---

## 为什么需要这样的设计?

### 1. **真实场景的复杂性**

现实中的开发任务往往需要多个角色协作:

```
❌ 错误假设: Task = 单一 Agent
Task "创建用户认证" → 只能分配给一个 Agent → 该 Agent 需要前后端全栈
→ 负担过重,能力受限

✅ 正确设计: Task = Agent 团队
Task "创建用户认证" → Backend Agent + Frontend Agent + Test Agent 并行协作
→ 专业分工,效率最大化
```

### 2. **并行效率的极致追求**

```typescript
// 场景: 创建一个 CRUD 功能

// ❌ 串行执行 (单 Agent)
Agent A (全栈) → 设计 DB → 写 API → 写前端 → 测试
总耗时: 120s

// ✅ 并行执行 (Agent 树)
Layer 1: Agent A (Backend) + Agent B (Design) 并行
Layer 2: Agent C (Frontend) [等待 A、B]
Layer 3: Agent D (Test) [等待 C]
总耗时: 45s  (节省 62%!)
```

### 3. **符合人类团队协作的隐喻**

```
用户: PM/老板
Task: 项目经理分配的子项目
Agent Tree: 执行该子项目的虚拟团队

示例:
Task: "实现支付功能"
├─ Backend Dev  (设计 API + 数据模型)
├─ Frontend Dev (实现支付页面 UI)
├─ QA Engineer  (编写测试用例)
└─ Code Reviewer (审查代码质量)
```

---

## 数据结构设计

### 核心接口

```typescript
interface AgentNode {
  id: string                // 唯一标识
  agentType: AgentType      // 角色类型
  prompt: string            // 任务描述
  dependsOn: string[]       // 依赖的 Agent ID 列表
}

interface AgentEdge {
  from: string              // 源 Agent ID
  to: string                // 目标 Agent ID
  dataFlow?: {
    artifacts: string[]     // 传递的产物 (文件/代码)
  }
}

interface Task {
  id: string
  title: string
  description: string

  // Task 间的依赖 (跨 Task)
  dependencies: string[]

  // ⭐ 核心: Task 内部的 Agent 执行图
  agentGraph: {
    nodes: AgentNode[]
    edges: AgentEdge[]
  }

  status: TaskStatus
}
```

### 示例: "创建博客文章功能"

```json
{
  "id": "TASK-1",
  "title": "实现博客文章 CRUD",
  "agentGraph": {
    "nodes": [
      {
        "id": "agent-db",
        "agentType": "backend",
        "prompt": "设计 Post schema 和 Prisma 模型",
        "dependsOn": []
      },
      {
        "id": "agent-api",
        "agentType": "backend",
        "prompt": "创建 /api/posts 端点 (GET, POST, PUT, DELETE)",
        "dependsOn": ["agent-db"]
      },
      {
        "id": "agent-ui",
        "agentType": "frontend",
        "prompt": "创建文章列表页和编辑页",
        "dependsOn": ["agent-api"]
      },
      {
        "id": "agent-test",
        "agentType": "test",
        "prompt": "编写 API 集成测试",
        "dependsOn": ["agent-api"]
      }
    ],
    "edges": [
      {
        "from": "agent-db",
        "to": "agent-api",
        "dataFlow": {
          "artifacts": ["prisma/schema.prisma"]
        }
      },
      {
        "from": "agent-api",
        "to": "agent-ui",
        "dataFlow": {
          "artifacts": ["api/posts/route.ts", "types/post.ts"]
        }
      }
    ]
  }
}
```

---

## 执行流程

### 层级调度算法

```typescript
class TaskScheduler {
  async executeTask(task: Task): Promise<void> {
    // 1. 构建依赖图
    const dag = this.buildDAG(task.agentGraph)

    // 2. 拓扑排序,生成可并行执行的层级
    const layers = this.topologicalSort(dag)

    // 示例输出:
    // Layer 0: [agent-db]              // 无依赖,最先执行
    // Layer 1: [agent-api]             // 等待 agent-db
    // Layer 2: [agent-ui, agent-test]  // 等待 agent-api,可并行

    // 3. 按层级执行
    for (const layer of layers) {
      // 同一层级的 Agent 并行启动
      await Promise.all(
        layer.map(agent => this.startAgent(agent, task))
      )

      // 等待当前层级所有 Agent 完成
      await this.waitForLayerComplete(layer)

      // 收集本层级的产物,注入到下一层
      await this.propagateArtifacts(layer, task)
    }
  }

  buildDAG(graph: AgentGraph): DAG {
    // 解析 nodes 和 edges,构建邻接表
    const adjacency = new Map<string, string[]>()

    for (const node of graph.nodes) {
      adjacency.set(node.id, node.dependsOn)
    }

    return adjacency
  }

  topologicalSort(dag: DAG): Layer[] {
    const inDegree = new Map<string, number>()
    const layers: Layer[] = []
    const currentLayer: string[] = []

    // 计算入度
    for (const [node, deps] of dag) {
      inDegree.set(node, deps.length)
      if (deps.length === 0) {
        currentLayer.push(node)  // 入度为 0 的节点加入第一层
      }
    }

    // Kahn 算法
    let layerIndex = 0
    layers.push(currentLayer)

    while (currentLayer.length > 0) {
      const nextLayer: string[] = []

      for (const node of currentLayer) {
        // 找到所有依赖当前节点的节点
        const dependents = this.findDependents(node, dag)

        for (const dependent of dependents) {
          inDegree.set(dependent, inDegree.get(dependent)! - 1)

          // 入度变为 0,加入下一层
          if (inDegree.get(dependent) === 0) {
            nextLayer.push(dependent)
          }
        }
      }

      layers.push(nextLayer)
      currentLayer = nextLayer
      layerIndex++
    }

    return layers
  }
}
```

### 产物传递机制

```typescript
class ArtifactManager {
  private artifacts = new Map<string, AgentResult>()

  async onAgentComplete(agentId: string, result: AgentResult): Promise<void> {
    // 1. 存储 Agent 的产物
    this.artifacts.set(agentId, result)

    // 2. 找到依赖此 Agent 的所有 Agent
    const dependents = this.findDependents(agentId)

    // 3. 检查依赖是否全部满足
    for (const dependent of dependents) {
      if (this.areDependenciesSatisfied(dependent)) {
        // 4. 注入产物到 Agent 的上下文
        await this.injectArtifacts(dependent, agentId)

        // 5. 启动该 Agent
        await this.startAgent(dependent)
      }
    }
  }

  async injectArtifacts(
    targetAgent: string,
    sourceAgent: string
  ): Promise<void> {
    const sourceResult = this.artifacts.get(sourceAgent)!
    const targetContext = this.getContext(targetAgent)

    // 根据定义的 dataFlow 规则传递产物
    const edge = this.findEdge(sourceAgent, targetAgent)

    for (const artifact of edge.dataFlow.artifacts) {
      const content = sourceResult.files[artifact]

      // 将产物添加到目标 Agent 的上下文中
      targetContext.files[artifact] = content
    }

    // 更新 System Prompt,告知 Agent 有哪些前置产物可用
    targetContext.systemPrompt = this.generatePromptWithContext(
      targetAgent,
      targetContext.files
    )
  }
}
```

---

## 可视化示例

### Dashboard 展示

```
┌─────────────────────────────────────────────────────────────┐
│  📋 Task: 创建用户认证系统                                    │
├─────────────────────────────────────────────────────────────┤
│  🎯 执行进度 (3/4 Agents 完成)                                │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Layer 1 (已完成)                                    │   │
│  │   ✅ Agent A (Backend)  → api/auth.ts               │   │
│  │   ✅ Agent B (Design)   → designs/login.fig         │   │
│  │                                                     │   │
│  │ Layer 2 (进行中)                                    │   │
│  │   🔄 Agent C (Frontend) → [接收 A、B 产物]          │   │
│  │      进度: [████████░░] 80%                         │   │
│  │                                                     │   │
│  │ Layer 3 (等待中)                                    │   │
│  │   ⏳ Agent D (Test)     → 等待 Agent C 完成         │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### 依赖链可视化

```
Task: 实现电商购物车

Agent DAG:
┌─────────────┐
│  Agent A    │  (Backend - 设计 Cart schema)
│  [已完成]    │
└──────┬──────┘
       │ 产物: prisma/schema.prisma
       ↓
┌─────────────┐
│  Agent B    │  (Backend - Cart API endpoints)
│  [已完成]    │
└──────┬──────┘
       │ 产物: api/cart/route.ts
       ↓
┌─────────────┐
│  Agent C    │  (Frontend - 购物车页面)
│  [进行中]    │
└──────┬──────┘
       │ 产物: components/Cart.vue
       ↓
┌─────────────┐
│  Agent D    │  (Test - 集成测试)
│  [等待中]    │
└─────────────┘
```

---

## 关键优势

### 1. **最大化并行度**

```
传统模型: 串行等待
A (30s) → B (45s) → C (30s) = 105s

Agent DAG: 并行执行
[A (30s), B (20s)] → C (25s) = 75s  (节省 28%)
```

### 2. **专业化分工**

```typescript
// 每个 Agent 专注自己的领域
const agents = {
  backend: {
    skills: ['prisma', 'express', 'postgresql'],
    systemPrompt: 'You are a backend expert...'
  },
  frontend: {
    skills: ['vue', 'tailwind', 'typescript'],
    systemPrompt: 'You are a frontend expert...'
  },
  design: {
    skills: ['figma', 'ui-design', 'ux-principles'],
    systemPrompt: 'You are a UI/UX designer...'
  }
}
```

### 3. **容错和重试**

```typescript
// 如果某个 Agent 失败,只需重试该 Agent
try {
  await executeAgent(agentC)
} catch (error) {
  // Agent C 失败,但 A、B 的产物已保存
  // 可以直接重试 C,无需重新执行 A、B
  await retryAgent(agentC)
}
```

### 4. **可观测性**

```typescript
// 用户可以看到实时的层级进度
socket.emit('layer:complete', {
  layer: 1,
  agents: ['agent-a', 'agent-b'],
  duration: '30s',
  nextLayer: ['agent-c']
})
```

---

## 与传统模型的对比

| 维度 | 传统模型 (单 Agent) | BeeBeeBrain (Agent DAG) |
|------|-------------------|------------------------|
| **并行度** | 串行执行 | 层级并行 |
| **专业度** | 全栈 Agent (泛而不精) | 专业 Agent (精而专) |
| **容错性** | 一个失败,全部重来 | 单点重试 |
| **可观测** | 只看到一个进度条 | 看到团队协作 |
| **符合直觉** | 像在和一个工人对话 | 像在管理一个团队 |

---

## 实现注意事项

### 1. **避免循环依赖**

```typescript
function validateDAG(graph: AgentGraph): boolean {
  // 使用 DFS 检测环
  const visited = new Set<string>()
  const recursionStack = new Set<string>()

  for (const node of graph.nodes) {
    if (this.hasCycle(node, visited, recursionStack)) {
      throw new Error(`Circular dependency detected involving ${node.id}`)
    }
  }

  return true
}
```

### 2. **产物版本管理**

```typescript
// 当 Agent 重试时,需要清理旧产物
class ArtifactManager {
  async retryAgent(agentId: string): Promise<void> {
    // 1. 清理旧产物
    await this.cleanupArtifacts(agentId)

    // 2. 重置 Agent 状态
    await this.resetAgent(agentId)

    // 3. 重新执行
    await this.executeAgent(agentId)
  }
}
```

### 3. **超时处理**

```typescript
// 设置 Agent 超时,防止无限等待
class TimeoutGuard {
  async executeWithTimeout(
    agent: AgentNode,
    timeout: number
  ): Promise<AgentResult> {
    return Promise.race([
      this.executeAgent(agent),
      new Promise((_, reject) =>
        setTimeout(() => reject(new Error('Agent timeout')), timeout)
      )
    ])
  }
}
```

---

## 总结

**Task = Agent DAG** 的设计使 BeeBeeBrain 能够:

1. ✅ **模拟真实团队**: 多个专业 Agent 协作完成复杂任务
2. ✅ **最大化效率**: 通过层级并行,大幅缩短总耗时
3. ✅ **提升质量**: 专业 Agent 在自己擅长的领域工作
4. ✅ **增强可观测性**: 用户可以清楚地看到"团队"如何协作
5. ✅ **改善容错性**: 单点失败不影响全局,易于重试

这不是一个简单的代码生成工具,而是一个**虚拟软件开发团队的自动化管理系统**。
