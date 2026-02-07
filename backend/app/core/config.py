from __future__ import annotations

import os
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field

Environment = Literal["development", "test", "production"]


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
    )


@lru_cache
def get_settings() -> Settings:
    return load_settings()
