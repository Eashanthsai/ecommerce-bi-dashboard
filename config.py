"""Environment-based configuration for the Flask application."""

import ipaddress
import os
from pathlib import Path

from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parent / ".env", override=False)


class DatabaseConfigurationError(RuntimeError):
    """Raised when required MySQL environment settings are invalid."""


def _environment_flag(name):
    value = os.getenv(name)
    if value is None:
        return None

    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes"}:
        return True
    if normalized in {"0", "false", "no"}:
        return False
    raise DatabaseConfigurationError(f"{name} must be a boolean value.")


def _is_local_database_host(host):
    normalized = host.strip().lower().rstrip(".")
    if normalized == "localhost" or normalized.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def get_database_config():
    """Return mysql-connector settings without embedding credentials in code."""
    try:
        port = int(os.getenv("DB_PORT", "3306"))
    except ValueError as exc:
        raise DatabaseConfigurationError("DB_PORT must be an integer.") from exc

    if not 1 <= port <= 65535:
        raise DatabaseConfigurationError("DB_PORT must be between 1 and 65535.")

    host = os.getenv("DB_HOST", "127.0.0.1")
    user = os.getenv("DB_USER")
    if not user:
        raise DatabaseConfigurationError("DB_USER must be set in the environment.")

    database = os.getenv("DB_NAME", "ecommerce_bi_dashboard")
    if not database:
        raise DatabaseConfigurationError("DB_NAME cannot be empty.")

    connection_config = {
        "host": host,
        "port": port,
        "user": user,
        "password": os.getenv("DB_PASSWORD", ""),
        "database": database,
    }

    ca_path = os.getenv("DB_SSL_CA", "").strip()
    verify_cert = _environment_flag("DB_SSL_VERIFY_CERT")
    verify_identity = _environment_flag("DB_SSL_VERIFY_IDENTITY")
    is_local = _is_local_database_host(host)

    if not is_local:
        if verify_cert is not True or verify_identity is not True:
            raise DatabaseConfigurationError(
                "Remote MySQL connections require DB_SSL_VERIFY_CERT=true "
                "and DB_SSL_VERIFY_IDENTITY=true."
            )
        connection_config.update(
            ssl_disabled=False,
            ssl_verify_cert=True,
            ssl_verify_identity=True,
        )
    elif any(
        value is not None
        for value in (verify_cert, verify_identity)
    ):
        connection_config["ssl_verify_cert"] = verify_cert is True
        connection_config["ssl_verify_identity"] = verify_identity is True
        if connection_config["ssl_verify_identity"] and not connection_config[
            "ssl_verify_cert"
        ]:
            raise DatabaseConfigurationError(
                "DB_SSL_VERIFY_IDENTITY=true requires DB_SSL_VERIFY_CERT=true."
            )

    if ca_path:
        ca_file = Path(ca_path).expanduser()
        if not ca_file.is_file() or not os.access(ca_file, os.R_OK):
            raise DatabaseConfigurationError(
                "DB_SSL_CA must point to an existing, readable CA certificate file."
            )
        connection_config["ssl_ca"] = str(ca_file)

    return connection_config
