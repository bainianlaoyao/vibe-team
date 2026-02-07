from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

AUTH_ENV_KEYS: tuple[str, ...] = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_BASE_URL",
    "CLAUDE_CODE_USE_BEDROCK",
    "CLAUDE_CODE_USE_VERTEX",
    "CLAUDE_CODE_USE_FOUNDRY",
)


@dataclass(frozen=True, slots=True)
class ClaudeSettingsAuth:
    settings_path: Path | None
    env: dict[str, str]


def resolve_claude_settings_path(path_override: str | Path | None = None) -> Path | None:
    if path_override is not None:
        resolved = Path(path_override).expanduser().resolve()
        if resolved.exists() and resolved.is_file():
            return resolved
        return None

    default_path = Path.home() / ".claude" / "settings.json"
    if default_path.exists() and default_path.is_file():
        return default_path.resolve()
    return None


def _load_settings_env(settings_path: Path | None) -> dict[str, str]:
    if settings_path is None:
        return {}

    try:
        payload = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    if not isinstance(payload, dict):
        return {}

    raw_env = payload.get("env")
    if not isinstance(raw_env, dict):
        return {}

    env: dict[str, str] = {}
    for key, value in raw_env.items():
        if isinstance(key, str) and isinstance(value, str):
            env[key] = value
    return env


def resolve_claude_auth(
    *,
    settings_path_override: str | Path | None = None,
) -> ClaudeSettingsAuth:
    settings_path = resolve_claude_settings_path(settings_path_override)
    env = _load_settings_env(settings_path)

    for key in AUTH_ENV_KEYS:
        value = os.getenv(key)
        if value:
            env[key] = value

    legacy_api_key = os.getenv("CLAUDE_API_KEY")
    if legacy_api_key and "ANTHROPIC_API_KEY" not in env:
        env["ANTHROPIC_API_KEY"] = legacy_api_key

    return ClaudeSettingsAuth(settings_path=settings_path, env=env)
