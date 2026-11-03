import pytest

import config
from app import create_app


def test_database_config_uses_environment_values(monkeypatch):
    monkeypatch.setenv("DB_HOST", "mysql.internal")
    monkeypatch.setenv("DB_PORT", "3307")
    monkeypatch.setenv("DB_USER", "dashboard_user")
    monkeypatch.setenv("DB_PASSWORD", "test-only-password")
    monkeypatch.setenv("DB_NAME", "dashboard_test")

    assert config.get_database_config() == {
        "host": "mysql.internal",
        "port": 3307,
        "user": "dashboard_user",
        "password": "test-only-password",
        "database": "dashboard_test",
    }


def test_database_config_requires_a_user(monkeypatch):
    monkeypatch.delenv("DB_USER", raising=False)

    with pytest.raises(config.DatabaseConfigurationError, match="DB_USER"):
        config.get_database_config()


def test_flask_app_requires_environment_session_key(monkeypatch):
    monkeypatch.delenv("FLASK_SECRET_KEY", raising=False)

    with pytest.raises(RuntimeError, match="FLASK_SECRET_KEY"):
        create_app()
