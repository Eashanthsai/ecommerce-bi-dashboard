"""Securely set local dashboard credentials and a persistent Flask secret."""

import os
import secrets
import tempfile
from getpass import getpass
from pathlib import Path

from werkzeug.security import generate_password_hash


ENV_PATH = Path(__file__).resolve().parent / ".env"
MANAGED_KEYS = {
    "FLASK_SECRET_KEY",
    "DASHBOARD_USERNAME",
    "DASHBOARD_PASSWORD_HASH",
}


def main():
    username = input("Dashboard username: ").strip()
    if not username:
        raise SystemExit("Username cannot be empty.")

    password = getpass("Dashboard password (minimum 12 characters): ")
    if len(password) < 12:
        raise SystemExit("Password must contain at least 12 characters.")
    confirmation = getpass("Confirm dashboard password: ")
    if not secrets.compare_digest(password, confirmation):
        raise SystemExit("Passwords do not match.")

    existing_lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    values = {}
    for line in existing_lines:
        key, separator, value = line.partition("=")
        if separator and key.strip() in MANAGED_KEYS:
            values[key.strip()] = value.strip()

    values["FLASK_SECRET_KEY"] = values.get("FLASK_SECRET_KEY") or secrets.token_hex(32)
    values["DASHBOARD_USERNAME"] = username
    values["DASHBOARD_PASSWORD_HASH"] = generate_password_hash(password)

    output = [line for line in existing_lines if not (
        line.partition("=")[1] and line.partition("=")[0].strip() in MANAGED_KEYS
    )]
    output.extend(f"{key}={values[key]}" for key in sorted(MANAGED_KEYS))
    content = "\n".join(output).rstrip() + "\n"

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".env.", suffix=".tmp", dir=ENV_PATH.parent, text=True
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as env_file:
            env_file.write(content)
        os.replace(temporary_name, ENV_PATH)
    except OSError:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise

    print("Dashboard credentials saved to the ignored local .env file. Values were not displayed.")


if __name__ == "__main__":
    main()
