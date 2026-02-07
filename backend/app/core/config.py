from __future__ import annotations

import os
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field

Environment = Literal["development", "test", "production"]
LogFormat = Literal["json", "console"]


class Settings(BaseModel):
    app_name: str = Field(default="BeeBeeBrain Backend")
    app_env: Environment = Field(default="development")
    debug: bool = Field(default=True)
    host: str = Field(default="127.0.0.1")
    port: int = Field(default=8000)
    database_url: str = Field(default="sqlite:///./beebeebrain.db")
    testing: bool = Field(default=False)
    claude_settings_path: str | None = Field(default=None)
    claude_cli_path: str | None = Field(default=None)
    claude_default_max_turns: int = Field(default=8)
    tasks_md_sync_enabled: bool = Field(default=False)
    tasks_md_output_path: str = Field(default="../tasks.md")
    log_level: str = Field(default="INFO")
    log_format: LogFormat = Field(default="json")
    log_file: str | None = Field(default=None)
    log_db_enabled: bool = Field(default=False)
    log_db_min_level: str = Field(default="WARNING")


def _to_bool(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


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


def _normalize_log_format(value: str | None) -> LogFormat:
    if value is None:
        return "json"
    lowered = value.strip().lower()
    if lowered == "console":
        return "console"
    return "json"


def load_settings() -> Settings:
    app_env = _normalize_env(os.getenv("APP_ENV"))
    default_debug = app_env != "production"
    default_testing = app_env == "test"
    default_db = (
        "sqlite:///./beebeebrain_test.db" if app_env == "test" else "sqlite:///./beebeebrain.db"
    )

    return Settings(
        app_name=os.getenv("APP_NAME", "BeeBeeBrain Backend"),
        app_env=app_env,
        debug=_to_bool(os.getenv("DEBUG"), default=default_debug),
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
        database_url=os.getenv("DATABASE_URL", default_db),
        testing=_to_bool(os.getenv("TESTING"), default=default_testing),
        claude_settings_path=os.getenv("CLAUDE_SETTINGS_PATH"),
        claude_cli_path=os.getenv("CLAUDE_CLI_PATH"),
        claude_default_max_turns=int(os.getenv("CLAUDE_DEFAULT_MAX_TURNS", "8")),
        tasks_md_sync_enabled=_to_bool(os.getenv("TASKS_MD_SYNC_ENABLED"), default=False),
        tasks_md_output_path=os.getenv("TASKS_MD_OUTPUT_PATH", "../tasks.md"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        log_format=_normalize_log_format(os.getenv("LOG_FORMAT")),
        log_file=os.getenv("LOG_FILE"),
        log_db_enabled=_to_bool(os.getenv("LOG_DB_ENABLED"), default=False),
        log_db_min_level=os.getenv("LOG_DB_MIN_LEVEL", "WARNING"),
    )


@lru_cache
def get_settings() -> Settings:
    return load_settings()
