import re
from datetime import date
from decimal import Decimal

import pytest
from flask.testing import FlaskClient

from app import app


@pytest.fixture
def authenticated_client(monkeypatch):
    monkeypatch.setattr(
        "app.database.fetch_filter_options",
        lambda: {"categories": ["Electronics"], "regions": ["West"]},
    )
    monkeypatch.setattr("app.database.fetch_sales_data", lambda **_filters: [])
    monkeypatch.setattr("app.database.fetch_product_count", lambda **_filters: 1)
    monkeypatch.setattr(
        "app.database.fetch_order_statuses", lambda: ["completed", "cancelled"]
    )
    monkeypatch.setattr(
        "app.database.fetch_orders",
        lambda **_filters: (
            [
                {
                    "order_id": 12,
                    "order_status": "completed",
                    "order_date": date(2025, 1, 15),
                    "region": "West",
                    "item_count": 2,
                }
            ],
            1,
        ),
    )
    monkeypatch.setattr(
        "app.database.fetch_all",
        lambda *_args, **_kwargs: [
            {
                "product_id": 3,
                "product_name": "Desk lamp",
                "category": "Electronics",
                "unit_price": Decimal("12.50"),
            }
        ],
    )
    monkeypatch.setattr(
        "app.analysis.analyze_sales",
        lambda *_args, **_kwargs: {
            "summary": {
                "gross_sales": 25.0,
                "discounts": 0.0,
                "refunds": 0.0,
                "net_sales": 25.0,
                "eligible_order_count": 1,
                "average_order_value": 25.0,
            },
            "monthly_revenue": [],
            "category_sales": [],
            "region_sales": [],
            "top_products": [],
            "month_over_month_growth": {
                "current_month": None,
                "current_revenue": None,
                "previous_month": None,
                "previous_revenue": None,
                "growth_percent": None,
                "status": "insufficient_history",
            },
            "insights": [],
        },
    )
    client = FlaskClient(app)
    with client.session_transaction() as session:
        session["authenticated"] = True
        session["csrf_token"] = "navigation-test-token"
    return client


@pytest.mark.parametrize(
    ("path", "active_nav"),
    [
        ("/dashboard", "dashboard"),
        ("/orders", "orders"),
        ("/products", "products"),
        ("/analytics", "analytics"),
        ("/reports", "reports"),
    ],
)
def test_sidebar_pages_load_after_login_refresh_and_highlight_current_item(
    authenticated_client, path, active_nav
):
    first_response = authenticated_client.get(path)
    refreshed_response = authenticated_client.get(path)

    assert first_response.status_code == 200
    assert refreshed_response.status_code == 200
    html = first_response.get_data(as_text=True)
    active_link = re.search(
        r'<a class="sidebar-link is-active" href="([^"]+)" aria-current="page">',
        html,
    )
    assert active_link
    assert active_link.group(1) == path
    assert f"<span>{active_nav.title()}</span>" in html


def test_sidebar_links_resolve_to_pages_and_settings_stays_disabled(
    authenticated_client,
):
    response = authenticated_client.get("/dashboard")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    sidebar = html.split('<nav class="sidebar-nav">', 1)[1].split("</nav>", 1)[0]
    links = re.findall(r'<a class="sidebar-link[^"]*" href="([^"]+)"', sidebar)

    assert links == ["/dashboard", "/orders", "/products", "/analytics", "/reports"]
    for path in links:
        assert authenticated_client.get(path).status_code == 200

    assert '<span class="sidebar-link is-disabled" aria-disabled="true"' in sidebar
    assert "<span>Settings</span><span class=\"nav-soon\">Soon</span>" in sidebar


@pytest.mark.parametrize(
    "path",
    ["/dashboard", "/orders", "/products", "/analytics", "/reports"],
)
def test_sidebar_pages_require_authentication(path, monkeypatch):
    client = FlaskClient(app)
    monkeypatch.setattr(
        "app.database.fetch_filter_options",
        lambda: pytest.fail("Unauthenticated request reached dashboard data"),
    )

    response = client.get(path)

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_orders_page_shows_database_order_fields_and_filters(authenticated_client):
    response = authenticated_client.get("/orders?status=completed&region=West")

    assert response.status_code == 200
    assert b"#12" in response.data
    assert b"2025-01-15" in response.data
    assert b"Completed" in response.data
    assert b"West" in response.data
    assert b"2" in response.data


def test_products_page_links_to_existing_product_management(authenticated_client):
    response = authenticated_client.get("/products")

    assert response.status_code == 200
    assert b"Desk lamp" in response.data
    assert b"$12.50" in response.data
    assert b'href="/products/new"' in response.data


def test_reports_page_preserves_existing_filtered_csv_export(authenticated_client):
    response = authenticated_client.get(
        "/reports?start_date=2025-01-01&category=Electronics&region=West"
    )

    assert response.status_code == 200
    assert b"Filtered sales CSV" in response.data
    assert (
        b"/exports/sales.csv?start_date=2025-01-01&amp;category=Electronics&amp;region=West"
        in response.data
    )


def test_analytics_page_keeps_database_backed_dashboard_kpis_and_charts(
    authenticated_client,
):
    response = authenticated_client.get("/analytics")

    assert response.status_code == 200
    assert b"Sales Analytics" in response.data
    assert b"$25.00" in response.data
    assert b"monthly-revenue.png" in response.data
