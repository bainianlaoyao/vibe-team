# BeeBeeBrain - Surface Demo

> 从 "AI 结对编程" 转型为 **"AI 团队管理"**
>
> 面向超小型团队/PM开发者的 **AI 工程管理平台**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.0-blue)](https://www.typescriptlang.org/)
[![Vue 3](https://img.shields.io/badge/Vue-3.4-42b883)](https://vuejs.org/)
[![Node.js](https://img.shields.io/badge/Node.js-20+-green)](https://nodejs.org/)

---

## 🎯 核心理念

你不是在做一个更好的代码编辑器，你是在做一个 **"软件外包公司的自动化管理后台"**，用户是老板，AI 是不知疲倦的员工。

### 解决的问题

当前 AI 编程工具（Claude Code/Cursor）的痛点：

- ❌ **串行效率低** - 等待一个 Agent 一个字蹦出来
- ❌ **上下文污染** - 单一聊天窗口承载过多信息
- ❌ **人类负担重** - 需要像保姆一样盯着 AI 生成

### 核心价值

1. **并行感 (Parallelism)** - 从"等一个字一个字蹦"变成"看五个进度条同时跑"
2. **管理感 (Agency)** - 从"写 Prompt"变成"派 Ticket"
3. **确定性 (Determinism)** - 通过"黄金模板"和"核心宪法"保证生成的项目结构统一、可运行

---

## 🎨 Surface Demo - 四屏演示

这是一个高保真的前端演示，展示"AI 团队管理"的完整体验：

### Screen 1: The Genesis (启动页)
- ✨ 极简输入框，类似 Google Search
- 🌐 Architect Core 球体动画（AI 思考过程）
- 📋 自动生成项目宣言卡片
- 🚀 "Authorize Team & Start" 按钮

### Screen 2: Mission Control (任务指挥中心)
**核心主页 - 展示并行开发的爽快感**

- **左侧 - Tactical Radar (40%)**
  - 👥 Agent Squad 视图（实时状态 🟢🔵🟡🔴）
  - 🕸️ Dependency Graph 微缩图

- **右侧 - Context Stage (60%)**
  - 📺 Live Preview - 从 404 到 Full UI
  - 💻 Terminal - 实时日志流
  - 📝 Code Diff - 代码变更预览

- **顶部**: 项目名称 + 进度条 + Play/Pause/Reset
- **底部**: Broadcast Bar - 全局指令输入

### Screen 3: The Shoulder Tap (干预模式)
**展示管理者的"指挥权"**

- 🖱️ 点击任意 UI 元素触发干预
- 🎯 Directive Modal - 自然语言指令输入
- 🤖 Agent 实时响应并应用修改
- 📋 Directive Queue - 指令历史记录

### Screen 4: The Conflict (冲突解决)
**展示系统处理真实开发问题**

- 🚨 8 秒自动触发 Schema 冲突
- 🛡️ War Room - 三栏布局（Agent A vs AI Suggestion vs Agent B）
- ✅ 一键应用 AI 修复方案

---

## 🚀 快速开始

### 环境要求

- Node.js >= 20
- npm >= 9

### 安装与运行

```bash
# 克隆项目
git clone https://github.com/your-repo/beebeebrain.git
cd beebeebrain

# 安装依赖
npm install

# 启动开发服务器
npm run dev

# 访问 Demo
# http://localhost:5173
```

### 构建生产版本

```bash
npm run build
```

---

## 🎨 设计系统

### 色板 (Palette)
- `Deep Space` (#0F1117) - 深空灰背景，沉浸感
- `Glass Panel` (#1E232F) - 半透明磨砂玻璃，现代感
- `Electric Indigo` (#6366F1) - 主行动按钮
- `Neon Green` (#10B981) - 运行中/完成
- `Cyber Yellow` (#F59E0B) - 阻塞/等待
- `Signal Red` (#EF4444) - 错误/冲突
- `Holographic Blue` (#3B82F6) - 思考中/规划中

### 字体 (Typography)
- *Inter* - 标题和正文（干净、专业）
- *JetBrains Mono* - 代码、日志、终端

### 动效 (Motion)
- `pop-in` - 文件和列表项像爆米花一样弹出
- `pulse-glow` - Agent 头像呼吸灯效果
- `spin-slow` - 缓慢旋转动画
- `fade` - 模态框淡入淡出

---

## 🎮 Demo 演示流程

### 推荐演示顺序（5-10 分钟）

1. **Screen 1 - The Genesis** (1 分钟)
   - 输入："做一个面向独立开发者的 SaaS 收入看板"
   - 按 Enter，观看 Architect Core 动画
   - 展示自动生成的项目宣言
   - 点击 "Authorize Team & Start"

2. **Screen 2 - Mission Control** (2-3 分钟)
   - 观看 3 个 Agent 并行工作
   - 切换到 Terminal 标签查看日志
   - 注意依赖关系：Frontend 等待 Backend 完成 Schema
   - Watch Live Preview 从 Skeleton 变成 Full UI

3. **Screen 3 - The Shoulder Tap** (2-3 分钟)
   - 等待 UI 渲染完成
   - 点击任意 UI 元素（如 "Revenue Card"）
   - 输入指令："把这个卡片改成渐变背景"
   - 观看 Agent 立即响应并应用修改

4. **Screen 4 - The Conflict** (2-3 分钟)
   - 启动 Demo
   - 等待 8 秒左右触发冲突
   - 展示 War Room 模态框
   - 点击 "Approve AI Fix"
   - 观看系统自动修复并继续工作

### 演示要点（针对 PM/老板）

- **Screen 1 卖的是"简单"**：一句话生成完整项目结构
- **Screen 2 卖的是"爽"**：并行开发，进度可视化
- **Screen 3 卖的是"权"**：随时干预，不用自己写代码
- **Screen 4 卖的是"稳"**：自动处理冲突，保证系统稳定

---

## 📁 项目结构

```
src/
├── components/              # 可复用组件
│   ├── AgentCard.vue       # Agent 卡片
│   ├── LivePreview.vue     # 实时预览（基础版）
│   ├── InteractivePreview.vue # 可交互预览
│   ├── DirectiveModal.vue  # 指令浮窗
│   └── WarRoomModal.vue    # 冲突解决模态框
├── views/                   # 页面视图
│   ├── TheGenesis.vue      # Screen 1
│   ├── MissionControl.vue  # Screen 2
│   ├── TheShoulderTap.vue  # Screen 3
│   └── TheConflict.vue     # Screen 4
├── composables/             # Vue 组合式函数
│   └── useDemoEngine.ts    # Demo 播放引擎
├── data/                    # 数据文件
│   └── demo-script.ts      # Demo 剧本（JSON 事件流）
├── types/                   # TypeScript 类型
│   └── demo.ts             # 类型定义
├── App.vue                  # 根组件（含屏幕切换器）
├── main.ts                  # 入口文件
└── style.css                # 全局样式
```

---

## 📝 自定义 Demo 剧本

编辑 `src/data/demo-script.ts` 来创建自己的演示场景：

```typescript
export const demoScript: DemoEvent[] = [
  {
    time_ms: 0,
    event: 'init_dashboard',
    project_name: 'Your Project Name'
  },
  {
    time_ms: 1000,
    event: 'agent_start',
    agent_id: 'backend_01',
    role: 'Schema Architect',
    status: 'coding',
    log: 'Initializing Prisma Schema...'
  },
  {
    time_ms: 3500,
    event: 'file_created',
    path: '/prisma/schema.prisma',
    content_preview: 'model User { id String ... }',
    agent_id: 'backend_01'
  },
  {
    time_ms: 3800,
    event: 'agent_status_change',
    agent_id: 'backend_01',
    status: 'done',
    log: 'Schema complete ✓'
  },
  {
    time_ms: 6000,
    event: 'preview_update',
    view_state: 'skeleton_screen',
    description: 'Navigation bar appearing...'
  },
  // ... 更多事件
]
```

### 支持的事件类型

- `init_dashboard` - 初始化项目
- `agent_start` - Agent 开始工作
- `agent_status_change` - Agent 状态变更
- `file_created` - 文件创建
- `preview_update` - 预览更新
- `demo_complete` - Demo 完成

---

## 🏗️ 技术架构

### 核心技术

- **并行引擎:** 基于 `git worktree` 的隐形版本控制
- **冲突解决:** Git 自动合并 → AI 自修复 → 人工介入
- **知识系统:**
  - L1 核心宪法 (技术栈指纹、目录结构)
  - L2 技能库 (基于 AST 的代码索引)

### 技术栈

**前端 (当前 Demo):**
```
Vue 3 + TypeScript
├── Vite (构建)
├── TailwindCSS (UI)
└── Composition API (状态管理)
```

**计划中的后端:**
```
Node.js + TypeScript
├── Express / Fastify
├── Prisma (ORM)
├── BullMQ (任务队列)
└── Socket.IO (实时通信)
```

---

## 🔧 技术栈

- **Vue 3** - 渐进式 JavaScript 框架（Composition API）
- **TypeScript** - 类型安全
- **Vite** - 下一代前端构建工具
- **Tailwind CSS** - 实用优先的 CSS 框架

---

## 🎯 屏幕切换

Demo 右上角有屏幕切换器，可以：
1. 点击右上角的按钮切换
2. 在浏览器控制台使用：`switchScreen('shoulder-tap')`

---

## 🗺️ 开发路线图

### Phase 1: Surface Demo ✅
- [x] 四个完整屏幕实现
- [x] 设计系统和动画
- [x] Demo 事件引擎
- [x] 完整文档

### Phase 2: 原型开发
- [ ] 真实 Git Worktree 集成
- [ ] 基础 Agent 框架
- [ ] 简单的 LLM 接入
- [ ] 实时 WebSocket 通信

### Phase 3: 核心功能
- [ ] 任务自动分裂系统
- [ ] 依赖关系解析
- [ ] 冲突自动检测与解决
- [ ] 黄金模板系统

### Phase 4: 产品化
- [ ] 性能优化
- [ ] 用户认证和权限
- [ ] 多项目支持
- [ ] 部署和监控

---

## 🚀 下一步优化方向

如果需要继续完善，可以考虑：

1. **更多交互**
   - 拖拽 Agent 重新排序
   - 点击 Artifact 查看代码
   - 实时代码编辑器集成

2. **更真实的模拟**
   - 网络延迟模拟
   - Agent 失败重试
   - 分支策略展示

3. **更多场景**
   - Code Review 流程
   - 部署流程
   - 性能优化

---

## 🤝 贡献

欢迎贡献! 请查看 [贡献指南](docs/contribution.md)。

### 如何贡献

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'feat: add some amazing feature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 创建 Pull Request

---

## 📊 项目状态

**当前版本:** 0.1.0 (Surface Demo MVP)

**开发状态:** ✅ Surface Demo 完成

**下一步:** 实现真实 Git Worktree 管理和基础 Agent 框架

---

## 📄 许可证

[MIT License](LICENSE)

---

## 💬 联系方式

- GitHub: [your-repo](https://github.com/your-repo/beebeebrain)
- Email: support@beebeebrain.dev

---

**一句话总结:**

从 Copilot 到 Manager - 让 AI 成为你的虚拟开发团队 🚀
