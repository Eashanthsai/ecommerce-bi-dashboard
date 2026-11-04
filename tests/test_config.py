import os

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


def test_flask_app_generates_a_local_session_key_when_missing(monkeypatch):
    monkeypatch.delenv("FLASK_SECRET_KEY", raising=False)

    app = create_app()

    assert app.secret_key
    assert len(app.secret_key) >= 64
    assert "FLASK_SECRET_KEY" not in os.environ


@pytest.mark.parametrize("environment_name", ["VERCEL_ENV", "FLASK_ENV", "ENVIRONMENT"])
def test_flask_app_requires_a_session_key_in_production(monkeypatch, environment_name):
    monkeypatch.delenv("FLASK_SECRET_KEY", raising=False)
    monkeypatch.setenv(environment_name, "production")

    with pytest.raises(RuntimeError, match="FLASK_SECRET_KEY"):
        create_app()


def test_flask_app_uses_the_configured_production_session_key(monkeypatch):
    monkeypatch.setenv("VERCEL_ENV", "production")
    monkeypatch.setenv("FLASK_SECRET_KEY", "configured-production-secret")

    app = create_app()

    assert app.secret_key == "configured-production-secret"
