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
