from __future__ import annotations

import os
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel, Field


class ConfigurationError(Exception):
    """配置错误"""
    pass


def _get_project_root() -> Path:
    """获取项目根目录，失败则报错"""
    # 1. 优先从环境变量读取
    if project_root := os.getenv("PROJECT_ROOT"):
        path = Path(project_root)
        if path.exists() and path.is_dir():
            return path
        raise ConfigurationError(
            f"PROJECT_ROOT 指向的目录不存在: {project_root}"
        )
    
    # 2. 尝试从当前工作目录推导
    cwd = Path.cwd()
    if (cwd / ".beebeebrain").exists():
        return cwd
    
    # 3. 尝试默认的 play_ground 位置（在 beebebrain 目录）
    # config.py -> app/core -> app -> backend -> beebeebrain/play_ground
    default = Path(__file__).resolve().parent.parent.parent.parent / "play_ground"
    if default.exists():
        return default
    
    raise ConfigurationError(
        "无法确定项目根目录。请设置 PROJECT_ROOT 环境变量，"
        "或在项目目录运行（包含 .beebeebrain 目录）。"
    )


def _load_env_file(project_root: Path) -> None:
    """加载项目级 .env 文件，不存在则报错"""
    env_file = project_root / ".env"
    
    if not env_file.exists():
        raise ConfigurationError(
            f"项目配置文件不存在: {env_file}\n"
            f"请在项目目录创建 .env 文件:\n"
            f"  cd {project_root}\n"
            f"  cp .env.example .env\n"
            f"  # 编辑 .env 文件"
        )
    
    load_dotenv(env_file, override=True)


# 获取项目根目录
PROJECT_ROOT = _get_project_root()

# 加载项目级配置（必须存在）
_load_env_file(PROJECT_ROOT)

Environment = Literal["development", "test", "production"]
LogFormat = Literal["json", "console"]


class Settings(BaseModel):
    app_name: str = Field(default="BeeBeeBrain Backend")
    app_env: Environment = Field(default="development")
    debug: bool = Field(default=True)
    host: str = Field(default="127.0.0.1")
    port: int = Field(default=8000)
    project_root: Path | None = Field(default=None)
    database_url: str = Field(default="sqlite:///./beebeebrain.db")
    testing: bool = Field(default=False)
    claude_settings_path: str | None = Field(default=None)
    claude_cli_path: str | None = Field(default=None)
    claude_default_max_turns: int = Field(default=8)
    chat_protocol_v2_enabled: bool = Field(default=False)
    chat_input_timeout_s: int = Field(default=600, ge=1)
    tasks_md_sync_enabled: bool = Field(default=False)
    tasks_md_output_path: str = Field(default="../tasks.md")
    log_level: str = Field(default="INFO")
    log_format: LogFormat = Field(default="json")
    log_file: str | None = Field(default=None)
    log_db_enabled: bool = Field(default=False)
    log_db_min_level: str = Field(default="WARNING")
    sqlalchemy_echo: bool | None = Field(default=None)  # None = auto (debug mode)
    local_api_key: str | None = Field(default=None)
    db_auto_init: bool = Field(default=True)
    db_auto_seed: bool = Field(default=True)
    cost_alert_threshold_usd: Decimal = Field(default=Decimal("0"))
    stuck_idle_timeout_s: int = Field(default=600, ge=1)
    stuck_repeat_threshold: float = Field(default=0.8, ge=0, le=1)
    stuck_error_rate_threshold: float = Field(default=0.6, ge=0, le=1)
    stuck_scan_interval_s: int = Field(default=60, ge=1)
    cors_allow_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:5174",
            "http://127.0.0.1:5174",
            "http://localhost:5175",
            "http://127.0.0.1:5175",
        ]
    )
    cors_allow_credentials: bool = Field(default=True)


def _to_bool(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _to_bool_or_none(value: str | None) -> bool | None:
    """Parse boolean from env var, return None if not set (for auto behavior)."""
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return None


def _normalize_env(value: str | None) -> Environment:
    if value is None:
        return "development"
    lowered = value.strip().lower()
    if lowered == "development":
        return "development"
    if lowered == "test":
        return "test"
    if lowered == "production":
        return "production"
    return "development"


def _normalize_log_format(value: str | None, app_env: Environment) -> LogFormat:
    if value is not None:
        lowered = value.strip().lower()
        if lowered == "console":
            return "console"
        if lowered == "json":
            return "json"
    # 默认策略：开发环境用 console，其他环境用 json
    return "console" if app_env == "development" else "json"


def _to_decimal(value: str | None, *, default: Decimal) -> Decimal:
    if value is None:
        return default
    try:
        return Decimal(value.strip())
    except Exception:
        return default


def _parse_csv_list(value: str | None, *, default: list[str]) -> list[str]:
    if value is None:
        return list(default)
    items = [part.strip() for part in value.split(",")]
    normalized = [item for item in items if item]
    return normalized or list(default)


def load_settings() -> Settings:
    app_env = _normalize_env(os.getenv("APP_ENV"))
    default_debug = app_env != "production"
    default_testing = app_env == "test"
    default_db_auto_init = app_env == "development"
    default_db_auto_seed = app_env == "development"

    # 使用全局 PROJECT_ROOT（已在模块加载时确定）
    project_root: Path | None = PROJECT_ROOT
    
    # 验证 PROJECT_ROOT 有效
    if not project_root.exists():
        raise ValueError(f"PROJECT_ROOT directory does not exist: {project_root}")
    if not project_root.is_dir():
        raise ValueError(f"PROJECT_ROOT is not a directory: {project_root}")

    # 确定数据库 URL
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        # 如果显式设置了 DATABASE_URL，优先使用它（但打印警告）
        if project_root:
            import warnings

            warnings.warn(
                "Both DATABASE_URL and PROJECT_ROOT are set. "
                f"Using DATABASE_URL: {database_url}",
                UserWarning,
                stacklevel=2,
            )
    elif project_root:
        # 从 PROJECT_ROOT 推导数据库路径
        db_path = project_root / ".beebeebrain" / "beebeebrain.db"
        database_url = f"sqlite:///{db_path}"
    else:
        # 测试模式下的默认路径
        database_url = (
            "sqlite:///./beebeebrain_test.db" if app_env == "test" else "sqlite:///./beebeebrain.db"
        )

    return Settings(
        app_name=os.getenv("APP_NAME", "BeeBeeBrain Backend"),
        app_env=app_env,
        debug=_to_bool(os.getenv("DEBUG"), default=default_debug),
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
        project_root=project_root,
        database_url=database_url,
        testing=_to_bool(os.getenv("TESTING"), default=default_testing),
        claude_settings_path=os.getenv("CLAUDE_SETTINGS_PATH"),
        claude_cli_path=os.getenv("CLAUDE_CLI_PATH"),
        claude_default_max_turns=int(os.getenv("CLAUDE_DEFAULT_MAX_TURNS", "8")),
        chat_protocol_v2_enabled=_to_bool(
            os.getenv("CHAT_PROTOCOL_V2_ENABLED"),
            default=False,
        ),
        chat_input_timeout_s=int(os.getenv("CHAT_INPUT_TIMEOUT_S", "600")),
        tasks_md_sync_enabled=_to_bool(os.getenv("TASKS_MD_SYNC_ENABLED"), default=False),
        tasks_md_output_path=os.getenv("TASKS_MD_OUTPUT_PATH", "../tasks.md"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        log_format=_normalize_log_format(os.getenv("LOG_FORMAT"), app_env),
        log_file=os.getenv("LOG_FILE"),
        log_db_enabled=_to_bool(os.getenv("LOG_DB_ENABLED"), default=False),
        log_db_min_level=os.getenv("LOG_DB_MIN_LEVEL", "WARNING"),
        sqlalchemy_echo=_to_bool_or_none(os.getenv("SQLALCHEMY_ECHO")),
        local_api_key=os.getenv("LOCAL_API_KEY"),
        db_auto_init=_to_bool(os.getenv("DB_AUTO_INIT"), default=default_db_auto_init),
        db_auto_seed=_to_bool(os.getenv("DB_AUTO_SEED"), default=default_db_auto_seed),
        cost_alert_threshold_usd=_to_decimal(
            os.getenv("COST_ALERT_THRESHOLD_USD"),
            default=Decimal("0"),
        ),
        stuck_idle_timeout_s=int(os.getenv("STUCK_IDLE_TIMEOUT_S", "600")),
        stuck_repeat_threshold=float(os.getenv("STUCK_REPEAT_THRESHOLD", "0.8")),
        stuck_error_rate_threshold=float(os.getenv("STUCK_ERROR_RATE_THRESHOLD", "0.6")),
        stuck_scan_interval_s=int(os.getenv("STUCK_SCAN_INTERVAL_S", "60")),
        cors_allow_origins=_parse_csv_list(
            os.getenv("CORS_ALLOW_ORIGINS"),
            default=[
                "http://localhost:5173",
                "http://127.0.0.1:5173",
                "http://localhost:5174",
                "http://127.0.0.1:5174",
                "http://localhost:5175",
                "http://127.0.0.1:5175",
            ],
        ),
        cors_allow_credentials=_to_bool(
            os.getenv("CORS_ALLOW_CREDENTIALS"),
            default=True,
        ),
    )


@lru_cache
def get_settings() -> Settings:
    return load_settings()
