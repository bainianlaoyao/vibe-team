
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
