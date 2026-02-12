# BeeBeeBrain Agent Instructions

## 项目级指令

1. Python 后端环境与依赖统一使用 `uv` 管理，不使用 `pip install` 直接改环境。
2. 后端工作目录默认为 `backend/`，执行 Python 命令统一使用 `uv run`。
3. 新增依赖使用 `uv add <pkg>`，开发依赖使用 `uv add --dev <pkg>`。
4. 拉取代码后先执行 `uv sync --dev`，保证本地环境与锁文件一致。
5. 后端代码需包含类型标注，遵循 FastAPI + Pydantic/SQLModel 约定，避免无类型 `dict` 透传。
6. 后端提交前必须通过：`uv run ruff check .`、`uv run black --check .`、`uv run mypy app tests`、`uv run pytest`（或 `make quality`）。
7. 前端保持 TypeScript strict，Vue 组件使用 Composition API（`<script setup lang="ts">`）。
8. 前端优先沿用现有包管理器与锁文件，不混用多套锁文件。
9. 提交信息使用 Conventional Commits（如 `feat: ...`、`fix: ...`、`refactor: ...`）。
10. 涉及架构、接口或任务分期变更时，同步更新 `docs/` 与根目录 `tasks.md`。
11. 开始搜索或分析前，先查阅 `docs/backend_mvp_tech.md` 的“项目现有知识与关键概念”章节，避免重复搜索与结论偏差。
12. 并行开发默认使用 `git worktree`：每个并行任务或可验收子任务使用独立分支与独立工作目录。
13. 开发策略采用 trunk-based：每个可验收子任务完成后尽快合并到 `main`，避免长生命周期分支累计冲突。
14. 分支生命周期目标为 `1-2 天`；开发期间至少每日同步一次 `main`（团队统一使用 rebase 或 merge）。
15. 合并门槛：CI 通过且满足第 6 条质量检查，并完成相关 `docs/` 与 `tasks.md` 同步更新。
16. 未完全完成的能力使用 feature flag（默认关闭）后再合并，不通过长期分支等待“大版本完成”。
17. 涉及数据库迁移时采用向后兼容的 expand/contract 策略，避免破坏性迁移直接进入 `main`。
18. 每个 worktree 运行时使用独立本地配置（如 `PORT`、`DATABASE_URL`、临时目录），避免并行开发时互相干扰。
19. 每次总结最后加"喵

## 推荐命令（后端）

```bash
# 初始化
cd backend
uv venv
uv sync --dev

# 运行
uv run uvicorn app.main:app --reload

# 测试与检查
uv run ruff check .
uv run black --check .
uv run mypy app tests
uv run pytest

# 统一入口
make quality
```

## Git Worktree 工作流规范

### 正确流程

使用 worktree 进行隔离开发时，必须严格遵守以下流程：

```bash
# 1. 创建 worktree（在主仓库执行）
git worktree add ../<worktree-name> <branch-name>

# 2. 进入 worktree 目录（关键步骤！）
cd ../<worktree-name>

# 3. 在 worktree 中进行所有开发工作
# - 修改代码
# - 运行测试
# - 提交更改
git add .
git commit -m "..."

# 4. 回到主仓库进行合并
cd ../<main-repo>
git merge <branch-name>
```

### 常见错误

❌ **错误**：创建 worktree 后未切换目录，仍在主仓库中提交

```bash
git worktree add ../work refactor/feature
git add .        # ❌ 在主仓库执行
git commit       # ❌ 提交到了主仓库
```

✅ **正确**：进入 worktree 目录后再进行所有操作

```bash
git worktree add ../work refactor/feature
cd ../work       # ✅ 切换到 worktree
git add .        # ✅ 在 worktree 中执行
git commit       # ✅ 提交到 worktree 分支
```

### 验证方法

执行任何 git 操作前，先确认当前目录：

```bash
pwd                    # 应该显示 worktree 路径
git branch --show-current  # 应该显示工作分支
```
