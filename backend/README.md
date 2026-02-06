# BeeBeeBrain Backend

最小可运行后端骨架，基于 FastAPI + SQLModel。

## 目录结构

```text
backend/
  app/
    api/
    core/
    main.py
  scripts/
    start_dev.ps1
    start_dev.sh
  tests/
  pyproject.toml
```

## 初始化

```bash
cd backend
uv sync --dev
```

## 本地运行

```bash
cd backend
uv run uvicorn app.main:app --reload
```

或使用脚本：

```powershell
cd backend
.\scripts\start_dev.ps1
```

## 配置

通过环境变量控制运行参数：

- `APP_ENV`: `development` / `test` / `production`
- `APP_NAME`: 服务名称（默认 `BeeBeeBrain Backend`）
- `HOST`: 绑定地址（默认 `127.0.0.1`）
- `PORT`: 端口（默认 `8000`）
- `DATABASE_URL`: 数据库连接串（默认开发 `sqlite:///./beebeebrain.db`，测试 `sqlite:///./beebeebrain_test.db`）
- `DEBUG`: 调试开关（默认开发/测试 `true`，生产 `false`）
- `TESTING`: 测试模式开关（默认仅 `APP_ENV=test` 为 `true`）

## 数据库初始化与迁移

初始化数据库（创建 SQLite 文件目录、执行 Alembic 迁移、写入种子数据）：

```bash
cd backend
uv run python -m app.db.cli init
```

仅执行迁移：

```bash
cd backend
uv run python -m app.db.cli migrate
```

常用参数：

- `--database-url <url>`：覆盖默认 `DATABASE_URL`
- `--skip-seed`：初始化时跳过种子数据

也可直接使用 Alembic：

```bash
cd backend
uv run alembic upgrade head
```

## 探活接口

- `GET /healthz`
- `GET /readyz`

## 检查与测试

```bash
cd backend
uv run ruff check .
uv run black --check .
uv run mypy app tests
uv run pytest
```

## 统一命令入口（Makefile）

```bash
cd backend
make sync
make quality
```

常用目标：

- `make lint`
- `make format-check`
- `make type-check`
- `make test`
- `make quality`

## pre-commit

```bash
cd backend
uv run pre-commit install
uv run pre-commit run --all-files
```
