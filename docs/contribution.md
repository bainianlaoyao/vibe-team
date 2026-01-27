# 贡献指南

感谢你考虑为 BeeBeeBrain 做贡献!

---

## 🤝 如何贡献

### 报告 Bug

如果你发现了 Bug,请:

1. 检查 [Issues](https://github.com/your-repo/issues) 是否已有相同问题
2. 如果没有,创建新的 Issue,包含:
   - 清晰的标题
   - 复现步骤
   - 预期行为 vs 实际行为
   - 环境信息 (OS, Node.js 版本等)
   - 相关日志或截图

### 提交功能请求

1. 检查是否已有相同请求
2. 描述你想要的功能
3. 说明为什么这个功能有用
4. 如果可能,提供使用场景或示例

### 提交代码

#### 1. Fork 并克隆

```bash
git clone https://github.com/your-username/beebeebrain.git
cd beebeebrain
```

#### 2. 创建分支

```bash
git checkout -b feature/your-feature-name
# 或
git checkout -b fix/your-bug-fix
```

分支命名规范:
- `feature/` - 新功能
- `fix/` - Bug 修复
- `docs/` - 文档更新
- `refactor/` - 代码重构
- `test/` - 测试相关
- `chore/` - 构建/工具链

#### 3. 安装依赖

```bash
pnpm install
```

#### 4. 开发

启动开发服务器:

```bash
# 前端
cd frontend && pnpm dev

# 后端
cd backend && pnpm dev

# 或同时启动
pnpm dev
```

#### 5. 测试

```bash
# 运行所有测试
pnpm test

# 运行特定测试
pnpm test -- frontend

# 运行 E2E 测试
pnpm test:e2e
```

#### 6. 代码风格

我们使用 ESLint 和 Prettier:

```bash
# 检查代码风格
pnpm lint

# 自动修复
pnpm lint:fix

# 格式化代码
pnpm format
```

#### 7. 提交

使用 [Conventional Commits](https://www.conventionalcommits.org/) 规范:

```bash
git commit -m "feat: add user authentication feature"
git commit -m "fix: resolve memory leak in agent scheduler"
git commit -m "docs: update API documentation"
```

类型:
- `feat:` 新功能
- `fix:` Bug 修复
- `docs:` 文档更新
- `style:` 代码格式 (不影响功能)
- `refactor:` 代码重构
- `test:` 测试相关
- `chore:` 构建/工具链

#### 8. 推送并创建 PR

```bash
git push origin feature/your-feature-name
```

然后在 GitHub 上创建 Pull Request。

PR 标题格式:
```
feat: add user authentication feature
fix: resolve memory leak in agent scheduler
```

PR 描述模板:

```markdown
## 变更说明
简要描述你的改动

## 变更类型
- [ ] Bug 修复
- [ ] 新功能
- [ ] 代码重构
- [ ] 文档更新
- [ ] 性能优化

## 测试
描述你如何测试这些改动

- [ ] 单元测试通过
- [ ] E2E 测试通过
- [ ] 手动测试通过

## 截图 (如适用)
贴上相关截图

## Checklist
- [ ] 代码遵循项目规范
- [ ] 已添加必要的文档
- [ ] 已添加必要的测试
- [ ] 所有测试通过
```

---

## 📐 开发规范

### TypeScript

- 启用严格模式
- 避免使用 `any`
- 优先使用 `interface` 而不是 `type`
- 函数参数和返回值必须显式声明类型

```typescript
// ✅ 好
interface User {
  id: string
  name: string
}

async function getUser(id: string): Promise<User> {
  // ...
}

// ❌ 差
async function getUser(id) {  // 缺少类型
  // ...
}
```

### Vue 3

- 使用 Composition API
- 组件使用 `<script setup>` 语法
- Props 必须定义类型
- Emits 必须声明

```vue
<script setup lang="ts">
interface Props {
  title: string
  count?: number
}

const props = withDefaults(defineProps<Props>(), {
  count: 0
})

const emit = defineEmits<{
  update: [value: string]
  delete: []
}>()
</script>
```

### 命名规范

**文件命名:**
- 组件: PascalCase (e.g., `UserDashboard.vue`)
- 工具函数: camelCase (e.g., `formatDate.ts`)
- 常量: UPPER_SNAKE_CASE (e.g., `API_BASE_URL.ts`)
- 类型文件: `.types.ts` 后缀 (e.g., `user.types.ts`)

**变量命名:**
- 变量和函数: camelCase
- 类和接口: PascalCase
- 常量: UPPER_SNAKE_CASE
- 私有成员: 下划线前缀 `_privateMethod`

### 注释规范

```typescript
/**
 * 计算两个日期之间的天数差
 * @param date1 - 第一个日期
 * @param date2 - 第二个日期
 * @returns 天数差 (绝对值)
 */
function daysBetween(date1: Date, date2: Date): number {
  // ...
}
```

### Git 提交规范

完整格式:

```
<type>(<scope>): <subject>

<body>

<footer>
```

示例:

```
feat(scheduler): add parallel task execution

- Implement task dependency resolution
- Add parallel worktree management
- Optimize agent allocation algorithm

Closes #123
```

---

## 🏗️ 项目结构

```
beebeebrain/
├── frontend/           # Vue 3 前端
├── backend/            # Node.js 后端
├── shared/             # 共享代码
├── docs/               # 文档
└── scripts/            # 构建脚本
```

### 前端结构

```
frontend/
├── src/
│   ├── components/     # 通用组件
│   │   ├── Dashboard/
│   │   ├── Ticket/
│   │   └── LogStream/
│   ├── views/          # 页面组件
│   ├── stores/         # Pinia stores
│   ├── api/            # API 调用
│   ├── types/          # TypeScript 类型
│   ├── utils/          # 工具函数
│   └── styles/         # 全局样式
├── public/
└── tests/              # 测试文件
```

### 后端结构

```
backend/
├── src/
│   ├── engine/         # 并行执行引擎
│   ├── brain/          # 知识系统
│   ├── api/            # REST API 路由
│   ├── models/         # 数据模型
│   ├── utils/          # 工具函数
│   └── types/          # TypeScript 类型
├── prisma/             # Prisma schema
└── tests/              # 测试文件
```

---

## 🧪 测试

### 单元测试

使用 Vitest (前端) 和 Jest (后端):

```typescript
// frontend/tests/components/Dashboard.test.ts
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import Dashboard from '@/components/Dashboard/Dashboard.vue'

describe('Dashboard', () => {
  it('renders agent status', () => {
    const wrapper = mount(Dashboard, {
      props: {
        agents: [
          { id: 'agent-1', name: 'Agent 1', status: 'running' }
        ]
      }
    })

    expect(wrapper.text()).toContain('Agent 1')
    expect(wrapper.text()).toContain('running')
  })
})
```

### E2E 测试

使用 Playwright:

```typescript
// e2e/specs/workflow.spec.ts
import { test, expect } from '@playwright/test'

test('complete project creation workflow', async ({ page }) => {
  await page.goto('/')

  // 创建项目
  await page.click('[data-testid="create-project"]')
  await page.fill('[name="name"]', 'Test Project')
  await page.click('button[type="submit"]')

  // 等待项目初始化
  await page.waitForSelector('[data-testid="project-dashboard"]')

  // 验证项目创建成功
  expect(page.locator('h1')).toContainText('Test Project')
})
```

---

## 📝 文档

### 代码文档

- 公共 API 必须有 JSDoc 注释
- 复杂逻辑必须有解释性注释
- README 必须说明如何安装和使用

### API 文档

使用 OpenAPI 规范:

```yaml
# backend/openapi.yaml
openapi: 3.0.0
info:
  title: BeeBeeBrain API
  version: 1.0.0
paths:
  /api/projects:
    post:
      summary: Create a new project
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                name:
                  type: string
```

---

## 🔧 开发工具

### VS Code

推荐扩展:
- Vue - Official
- TypeScript Vue Plugin (Volar)
- ESLint
- Prettier
- GitLens

### VS Code 设置

`.vscode/settings.json`:

```json
{
  "typescript.tsdk": "node_modules/typescript/lib",
  "vite.devServer.port": 3000,
  "editor.formatOnSave": true,
  "editor.defaultFormatter": "esbenp.prettier-vscode",
  "editor.codeActionsOnSave": {
    "source.fixAll.eslint": true
  }
}
```

---

## 🚀 发布流程

### 版本号

遵循 [Semantic Versioning](https://semver.org/):
- `MAJOR.MINOR.PATCH`
- MAJOR: 不兼容的 API 变更
- MINOR: 向后兼容的新功能
- PATCH: 向后兼容的 Bug 修复

### 发布步骤

1. 更新版本号:
   ```bash
   pnpm version patch  # 或 minor, major
   ```

2. 生成 CHANGELOG:
   ```bash
   pnpm changelog
   ```

3. 提交并打标签:
   ```bash
   git add .
   git commit -m "chore: release v1.2.3"
   git tag v1.2.3
   git push && git push --tags
   ```

4. 构建:
   ```bash
   pnpm build
   ```

5. 发布到 npm (TBD)

---

## 💬 社区

- Discord: [链接]
- GitHub Discussions: [链接]
- 邮件: support@beebeebrain.dev

---

## 📄 许可证

通过贡献代码,你同意你的贡献将在 [MIT License](../LICENSE) 下发布。

---

## 🙏 致谢

感谢所有贡献者!

[如果你的 PR 被合并,你的名字将出现在这里]

---

再次感谢你的贡献! 🎉
