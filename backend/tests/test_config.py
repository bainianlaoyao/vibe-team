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
    assert settings.database_url == "sqlite:///./beebeebrain_test.db"


def test_load_settings_for_production_env(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("DEBUG", raising=False)

    settings = load_settings()

    assert settings.app_env == "production"
    assert settings.debug is False


def test_load_settings_normalizes_log_format(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_FORMAT", "CONSOLE")
    settings = load_settings()
    assert settings.log_format == "console"

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
