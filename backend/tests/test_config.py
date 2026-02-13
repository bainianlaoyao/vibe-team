from pathlib import Path

import pytest
from pytest import MonkeyPatch

from app.core.config import load_settings


def _to_sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


@pytest.fixture(autouse=True)
def _reset_required_env(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("PROJECT_ROOT", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", _to_sqlite_url(tmp_path / "config-test.db"))


def test_load_settings_for_test_env(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.delenv("DEBUG", raising=False)
    monkeypatch.delenv("TESTING", raising=False)
    db_url = _to_sqlite_url(tmp_path / "test-env.db")
    monkeypatch.setenv("DATABASE_URL", db_url)

    settings = load_settings()

    assert settings.app_env == "test"
    assert settings.testing is True
    assert settings.debug is True
    assert settings.database_url == db_url
    assert settings.db_auto_init is False
    assert settings.db_auto_seed is False


def test_load_settings_for_production_env(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("DEBUG", raising=False)

    settings = load_settings()

    assert settings.app_env == "production"
    assert settings.debug is False
    assert settings.db_auto_init is False
    assert settings.db_auto_seed is False


def test_load_settings_supports_project_root_based_database_path(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "workspace"
    project_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("PROJECT_ROOT", str(project_root))

    settings = load_settings()

    assert settings.project_root == project_root
    assert settings.database_url == _to_sqlite_url(project_root / ".beebeebrain" / "beebeebrain.db")


def test_load_settings_rejects_mutually_exclusive_database_settings(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "workspace"
    project_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("PROJECT_ROOT", str(project_root))
    monkeypatch.setenv("DATABASE_URL", _to_sqlite_url(tmp_path / "override.db"))

    with pytest.raises(ValueError, match="mutually exclusive"):
        load_settings()


def test_load_settings_requires_database_source(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.delenv("PROJECT_ROOT", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(ValueError, match="Either PROJECT_ROOT or DATABASE_URL"):
        load_settings()


def test_load_settings_for_development_env_db_auto_init_defaults(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("DB_AUTO_INIT", raising=False)
    monkeypatch.delenv("DB_AUTO_SEED", raising=False)

    settings = load_settings()

    assert settings.app_env == "development"
    assert settings.db_auto_init is True
    assert settings.db_auto_seed is True


def test_load_settings_supports_db_auto_init_overrides(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("DB_AUTO_INIT", "false")
    monkeypatch.setenv("DB_AUTO_SEED", "false")

    settings = load_settings()

    assert settings.db_auto_init is False
    assert settings.db_auto_seed is False


def test_load_settings_normalizes_log_format(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_FORMAT", "CONSOLE")
    settings = load_settings()
    assert settings.log_format == "console"

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("LOG_FORMAT", "unsupported")
    settings = load_settings()
    assert settings.log_format == "json"


def test_load_settings_parses_cost_alert_threshold(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("COST_ALERT_THRESHOLD_USD", "12.3456")
    settings = load_settings()
    assert str(settings.cost_alert_threshold_usd) == "12.3456"

    monkeypatch.setenv("COST_ALERT_THRESHOLD_USD", "invalid")
    settings = load_settings()
    assert str(settings.cost_alert_threshold_usd) == "0"


def test_load_settings_parses_stuck_detector_thresholds(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("STUCK_IDLE_TIMEOUT_S", "120")
    monkeypatch.setenv("STUCK_REPEAT_THRESHOLD", "0.75")
    monkeypatch.setenv("STUCK_ERROR_RATE_THRESHOLD", "0.66")
    monkeypatch.setenv("STUCK_SCAN_INTERVAL_S", "30")

    settings = load_settings()
    assert settings.stuck_idle_timeout_s == 120
    assert settings.stuck_repeat_threshold == 0.75
    assert settings.stuck_error_rate_threshold == 0.66
    assert settings.stuck_scan_interval_s == 30


def test_load_settings_reads_local_api_key(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("LOCAL_API_KEY", "probe-key")
    settings = load_settings()
    assert settings.local_api_key == "probe-key"


def test_load_settings_parses_chat_protocol_v2_flags(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("CHAT_PROTOCOL_V2_ENABLED", "true")
    monkeypatch.setenv("CHAT_INPUT_TIMEOUT_S", "321")

    settings = load_settings()

    assert settings.chat_protocol_v2_enabled is True
    assert settings.chat_input_timeout_s == 321
