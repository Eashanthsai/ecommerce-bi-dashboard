import re

import pytest
from flask.testing import FlaskClient
from werkzeug.security import generate_password_hash

from app import create_app


@pytest.fixture
def unauthenticated_client(monkeypatch):
    monkeypatch.setenv("FLASK_SECRET_KEY", "authentication-test-secret")
    monkeypatch.setenv("DASHBOARD_USERNAME", "dashboard-admin")
    monkeypatch.setenv(
        "DASHBOARD_PASSWORD_HASH", generate_password_hash("correct-horse-battery")
    )
    application = create_app()
    application.config.update(TESTING=True)
    return application, FlaskClient(application)


def csrf_from_login(client):
    response = client.get("/login")
    assert response.status_code == 200
    match = re.search(rb'name="csrf_token" value="([^"]+)"', response.data)
    assert match
    return match.group(1).decode()


def test_sensitive_pages_and_data_apis_require_authentication(
    unauthenticated_client, monkeypatch
):
    _application, client = unauthenticated_client
    monkeypatch.setattr(
        "app.database.fetch_filter_options",
        lambda: pytest.fail("Unauthenticated request reached the database"),
    )

    for path in (
        "/",
        "/dashboard",
        "/imports",
        "/imports/sample.csv",
        "/products/new",
        "/charts/monthly-revenue.png",
    ):
        response = client.get(path)
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    response = client.get("/api/products")
    assert response.status_code == 401
    assert response.get_json() == {"error": "Authentication required."}


def test_login_requires_csrf_and_rejects_invalid_credentials(unauthenticated_client):
    _application, client = unauthenticated_client
    csrf_token = csrf_from_login(client)

    missing_token = client.post(
        "/login",
        data={"username": "dashboard-admin", "password": "correct-horse-battery"},
    )
    assert missing_token.status_code == 400

    csrf_token = csrf_from_login(client)
    invalid_credentials = client.post(
        "/login",
        data={
            "csrf_token": csrf_token,
            "username": "dashboard-admin",
            "password": "wrong-password",
        },
    )
    assert invalid_credentials.status_code == 401
    assert b"username or password was incorrect" in invalid_credentials.data


def test_login_rate_limits_repeated_failed_attempts(unauthenticated_client):
    _application, client = unauthenticated_client
    csrf_token = csrf_from_login(client)

    for _attempt in range(5):
        response = client.post(
            "/login",
            data={
                "csrf_token": csrf_token,
                "username": "dashboard-admin",
                "password": "wrong-password",
            },
        )
        assert response.status_code == 401

    blocked = client.post(
        "/login",
        data={
            "csrf_token": csrf_token,
            "username": "dashboard-admin",
            "password": "correct-horse-battery",
        },
    )
    assert blocked.status_code == 429
    assert b"Too many sign-in attempts" in blocked.data


@pytest.mark.parametrize(
    "unsafe_target",
    [
        "https://attacker.example/",
        "//attacker.example/",
        r"/\\attacker.example/",
    ],
)
def test_login_authenticates_and_blocks_external_redirects(
    unauthenticated_client, unsafe_target
):
    _application, client = unauthenticated_client
    csrf_token = csrf_from_login(client)

    response = client.post(
        "/login",
        data={
            "csrf_token": csrf_token,
            "username": "dashboard-admin",
            "password": "correct-horse-battery",
            "next": unsafe_target,
        },
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/dashboard")
    with client.session_transaction() as session:
        assert session["authenticated"] is True
        assert session.permanent is True
        assert session["csrf_token"] != csrf_token


def test_authenticated_dashboard_loads_and_has_csrf_protected_forms(
    unauthenticated_client, monkeypatch
):
    _application, client = unauthenticated_client
    csrf_token = csrf_from_login(client)
    client.post(
        "/login",
        data={
            "csrf_token": csrf_token,
            "username": "dashboard-admin",
            "password": "correct-horse-battery",
        },
    )
    monkeypatch.setattr(
        "app.database.fetch_filter_options",
        lambda: {"categories": [], "regions": []},
    )
    monkeypatch.setattr("app.database.fetch_sales_data", lambda **_filters: [])
    monkeypatch.setattr("app.database.fetch_product_count", lambda **_filters: 0)

    response = client.get("/dashboard")

    assert response.status_code == 200
    assert b"Performance snapshot" in response.data
    response = client.get("/imports")
    assert response.status_code == 200
    assert b'name="csrf_token" value="' in response.data


def test_authenticated_post_without_csrf_is_rejected(unauthenticated_client):
    _application, client = unauthenticated_client
    csrf_token = csrf_from_login(client)
    client.post(
        "/login",
        data={
            "csrf_token": csrf_token,
            "username": "dashboard-admin",
            "password": "correct-horse-battery",
        },
    )

    response = client.post("/products/new", data={"product_name": "No token"})

    assert response.status_code == 400
    assert b"form expired" in response.data


def test_logout_clears_session_and_returns_to_login(unauthenticated_client):
    _application, client = unauthenticated_client
    csrf_token = csrf_from_login(client)
    client.post(
        "/login",
        data={
            "csrf_token": csrf_token,
            "username": "dashboard-admin",
            "password": "correct-horse-battery",
        },
    )
    with client.session_transaction() as session:
        csrf_token = session["csrf_token"]

    response = client.post("/logout", data={"csrf_token": csrf_token})

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")
    response = client.get("/dashboard")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
