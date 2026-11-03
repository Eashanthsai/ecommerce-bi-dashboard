"""Environment-based configuration for the Flask application."""

import os
from pathlib import Path

from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parent / ".env", override=False)


class DatabaseConfigurationError(RuntimeError):
    """Raised when required MySQL environment settings are invalid."""


def get_database_config():
    """Return mysql-connector settings without embedding credentials in code."""
    try:
        port = int(os.getenv("DB_PORT", "3306"))
    except ValueError as exc:
        raise DatabaseConfigurationError("DB_PORT must be an integer.") from exc

    if not 1 <= port <= 65535:
        raise DatabaseConfigurationError("DB_PORT must be between 1 and 65535.")

    user = os.getenv("DB_USER")
    if not user:
        raise DatabaseConfigurationError("DB_USER must be set in the environment.")

    database = os.getenv("DB_NAME", "ecommerce_bi_dashboard")
    if not database:
        raise DatabaseConfigurationError("DB_NAME cannot be empty.")

    return {
        "host": os.getenv("DB_HOST", "127.0.0.1"),
        "port": port,
        "user": user,
        "password": os.getenv("DB_PASSWORD", ""),
        "database": database,
    }
