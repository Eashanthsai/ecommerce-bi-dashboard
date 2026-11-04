from werkzeug.security import check_password_hash

import set_dashboard_credentials


def test_setup_saves_a_hashed_password_and_preserves_database_settings(
    tmp_path, monkeypatch, capsys
):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "DB_HOST=127.0.0.1\nDB_NAME=existing_database\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(set_dashboard_credentials, "ENV_PATH", env_path)
    monkeypatch.setattr("builtins.input", lambda _prompt: "local-admin")
    password_responses = iter(("correct-horse-battery", "correct-horse-battery"))
    monkeypatch.setattr(
        set_dashboard_credentials,
        "getpass",
        lambda _prompt: next(password_responses),
    )

    set_dashboard_credentials.main()

    contents = env_path.read_text(encoding="utf-8")
    entries = dict(line.split("=", 1) for line in contents.splitlines())
    assert entries["DB_HOST"] == "127.0.0.1"
    assert entries["DB_NAME"] == "existing_database"
    assert entries["DASHBOARD_USERNAME"] == "local-admin"
    assert check_password_hash(
        entries["DASHBOARD_PASSWORD_HASH"], "correct-horse-battery"
    )
    assert entries["FLASK_SECRET_KEY"]
    assert "correct-horse-battery" not in contents
    assert "correct-horse-battery" not in capsys.readouterr().out
