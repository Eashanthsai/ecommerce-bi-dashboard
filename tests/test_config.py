import pytest

import config
import database
from app import create_app


def test_database_config_uses_environment_values(monkeypatch):
    clear_tls_environment(monkeypatch)
    monkeypatch.setenv("DB_HOST", "mysql.internal")
    monkeypatch.setenv("DB_PORT", "3307")
    monkeypatch.setenv("DB_USER", "dashboard_user")
    monkeypatch.setenv("DB_PASSWORD", "test-only-password")
    monkeypatch.setenv("DB_NAME", "dashboard_test")
    monkeypatch.setenv("DB_SSL_VERIFY_CERT", "true")
    monkeypatch.setenv("DB_SSL_VERIFY_IDENTITY", "true")

    assert config.get_database_config() == {
        "host": "mysql.internal",
        "port": 3307,
        "user": "dashboard_user",
        "password": "test-only-password",
        "database": "dashboard_test",
        "ssl_disabled": False,
        "ssl_verify_cert": True,
        "ssl_verify_identity": True,
    }


def clear_tls_environment(monkeypatch):
    for name in ("DB_SSL_CA", "DB_SSL_VERIFY_CERT", "DB_SSL_VERIFY_IDENTITY"):
        monkeypatch.delenv(name, raising=False)


def test_local_database_keeps_connector_tls_defaults(monkeypatch):
    clear_tls_environment(monkeypatch)
    monkeypatch.setenv("DB_HOST", "127.0.0.1")
    monkeypatch.setenv("DB_USER", "dashboard_user")

    connection_config = config.get_database_config()

    assert connection_config["host"] == "127.0.0.1"
    assert not any(key.startswith("ssl_") for key in connection_config)


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "::1", "dev.localhost"])
def test_loopback_database_hosts_do_not_require_tls_flags(monkeypatch, host):
    clear_tls_environment(monkeypatch)
    monkeypatch.setenv("DB_HOST", host)
    monkeypatch.setenv("DB_USER", "dashboard_user")

    assert config.get_database_config()["host"] == host


def test_remote_database_requires_explicit_certificate_and_identity_verification(
    monkeypatch,
):
    clear_tls_environment(monkeypatch)
    monkeypatch.setenv("DB_HOST", "mysql.example.net")
    monkeypatch.setenv("DB_USER", "dashboard_user")

    with pytest.raises(config.DatabaseConfigurationError, match="DB_SSL_VERIFY_CERT"):
        config.get_database_config()


@pytest.mark.parametrize(
    ("verify_cert", "verify_identity"),
    [("false", "true"), ("true", "false"), ("false", "false")],
)
def test_remote_database_rejects_disabled_tls_verification(
    monkeypatch, verify_cert, verify_identity
):
    clear_tls_environment(monkeypatch)
    monkeypatch.setenv("DB_HOST", "mysql.example.net")
    monkeypatch.setenv("DB_USER", "dashboard_user")
    monkeypatch.setenv("DB_SSL_VERIFY_CERT", verify_cert)
    monkeypatch.setenv("DB_SSL_VERIFY_IDENTITY", verify_identity)

    with pytest.raises(config.DatabaseConfigurationError, match="require"):
        config.get_database_config()


def test_invalid_tls_flag_is_rejected(monkeypatch):
    clear_tls_environment(monkeypatch)
    monkeypatch.setenv("DB_HOST", "127.0.0.1")
    monkeypatch.setenv("DB_USER", "dashboard_user")
    monkeypatch.setenv("DB_SSL_VERIFY_CERT", "sometimes")

    with pytest.raises(config.DatabaseConfigurationError, match="boolean"):
        config.get_database_config()


def test_local_identity_verification_requires_certificate_verification(monkeypatch):
    clear_tls_environment(monkeypatch)
    monkeypatch.setenv("DB_HOST", "localhost")
    monkeypatch.setenv("DB_USER", "dashboard_user")
    monkeypatch.setenv("DB_SSL_VERIFY_IDENTITY", "true")

    with pytest.raises(config.DatabaseConfigurationError, match="requires"):
        config.get_database_config()


def test_remote_database_uses_configured_ca_file(monkeypatch, tmp_path):
    clear_tls_environment(monkeypatch)
    ca_file = tmp_path / "provider-ca.pem"
    ca_file.write_text("test-only CA placeholder", encoding="utf-8")
    monkeypatch.setenv("DB_HOST", "mysql.example.net")
    monkeypatch.setenv("DB_USER", "dashboard_user")
    monkeypatch.setenv("DB_SSL_CA", str(ca_file))
    monkeypatch.setenv("DB_SSL_VERIFY_CERT", "yes")
    monkeypatch.setenv("DB_SSL_VERIFY_IDENTITY", "1")

    connection_config = config.get_database_config()

    assert connection_config["ssl_ca"] == str(ca_file)
    assert connection_config["ssl_verify_cert"] is True
    assert connection_config["ssl_verify_identity"] is True
    assert connection_config["ssl_disabled"] is False


def test_invalid_ca_file_is_rejected(monkeypatch, tmp_path):
    clear_tls_environment(monkeypatch)
    monkeypatch.setenv("DB_HOST", "localhost")
    monkeypatch.setenv("DB_USER", "dashboard_user")
    monkeypatch.setenv("DB_SSL_CA", str(tmp_path / "missing-ca.pem"))

    with pytest.raises(config.DatabaseConfigurationError, match="DB_SSL_CA"):
        config.get_database_config()


def test_database_connection_passes_verified_tls_options_to_connector(
    monkeypatch, tmp_path
):
    clear_tls_environment(monkeypatch)
    ca_file = tmp_path / "provider-ca.pem"
    ca_file.write_text("test-only CA placeholder", encoding="utf-8")
    monkeypatch.setenv("DB_HOST", "mysql.example.net")
    monkeypatch.setenv("DB_USER", "dashboard_user")
    monkeypatch.setenv("DB_SSL_CA", str(ca_file))
    monkeypatch.setenv("DB_SSL_VERIFY_CERT", "true")
    monkeypatch.setenv("DB_SSL_VERIFY_IDENTITY", "true")
    monkeypatch.setattr(
        "database.mysql.connector.connect", lambda **kwargs: kwargs
    )

    connection_config = database.get_connection()

    assert connection_config["ssl_ca"] == str(ca_file)
    assert connection_config["ssl_verify_cert"] is True
    assert connection_config["ssl_verify_identity"] is True


def test_database_config_requires_a_user(monkeypatch):
    monkeypatch.delenv("DB_USER", raising=False)

    with pytest.raises(config.DatabaseConfigurationError, match="DB_USER"):
        config.get_database_config()


def test_flask_app_requires_a_configured_session_key(monkeypatch):
    monkeypatch.delenv("FLASK_SECRET_KEY", raising=False)

    with pytest.raises(RuntimeError, match="FLASK_SECRET_KEY"):
        create_app()


def test_flask_app_requires_dashboard_credentials(monkeypatch):
    monkeypatch.delenv("DASHBOARD_USERNAME", raising=False)

    with pytest.raises(RuntimeError, match="DASHBOARD_USERNAME"):
        create_app()


def test_flask_app_uses_the_configured_session_key(monkeypatch):
    monkeypatch.setenv("FLASK_SECRET_KEY", "configured-production-secret")

    app = create_app()

    assert app.secret_key == "configured-production-secret"
