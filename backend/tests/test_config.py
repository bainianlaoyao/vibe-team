from pytest import MonkeyPatch

from app.core.config import load_settings


def test_load_settings_for_test_env(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.delenv("DEBUG", raising=False)
    monkeypatch.delenv("TESTING", raising=False)

    settings = load_settings()

    assert settings.app_env == "test"
    assert settings.testing is True
    assert settings.debug is True
    # database_url 现在从 PROJECT_ROOT 推导
    assert ".beebeebrain" in settings.database_url
    assert "beebeebrain.db" in settings.database_url
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
