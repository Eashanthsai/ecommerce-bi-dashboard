from datetime import date
import csv
from decimal import Decimal
from io import BytesIO
import re
from unittest.mock import patch

import mysql.connector
import pytest

import analysis
from app import app


@pytest.fixture(autouse=True)
def mock_dashboard_filter_options(monkeypatch):
    monkeypatch.setattr(
        "app.database.fetch_filter_options",
        lambda: {
            "categories": ["Electronics", "Home"],
            "regions": ["East", "West"],
        },
    )


def setup_function():
    app.config.update(TESTING=True)


def test_welcome_page_links_to_import_dashboard_and_sample_csv():
    with app.test_client() as client:
        response = client.get("/")

    assert response.status_code == 200
    assert b"Make sales data easier to understand" in response.data
    assert b"/imports" in response.data
    assert b"/dashboard" in response.data
    assert b"/imports/sample.csv" in response.data


def test_dashboard_page_renders_dashboard():
    report = {
        "summary": {
            "net_sales": 120.5,
            "eligible_order_count": 2,
            "average_order_value": 60.25,
        },
        "monthly_revenue": [],
        "category_sales": [],
        "region_sales": [],
        "month_over_month_growth": {
            "current_month": "2025-02",
            "current_revenue": 120.5,
            "previous_month": "2025-01",
            "previous_revenue": 100.0,
            "growth_percent": 20.5,
            "status": "calculated",
        },
    }
    with patch("app.database.fetch_sales_data", return_value=[]), patch(
        "app.database.fetch_product_count", return_value=8
    ), patch("app.analysis.analyze_sales", return_value=report) as analyze:
        with app.test_client() as client:
            response = client.get("/dashboard")

    assert response.status_code == 200
    assert b"Welcome to Your Business Dashboard" in response.data
    assert b"Key performance indicators for this period" in response.data
    assert b"$120.50" in response.data
    assert b"MOM REVENUE GROWTH" in response.data
    assert b"+20.50%" in response.data
    assert b"2025-02" in response.data
    assert b"2025-01" in response.data
    assert b"8" in response.data
    assert b"monthly-revenue.png" in response.data
    analyze.assert_called_once_with([], start_date=None, end_date=None)


def test_dashboard_date_filter_is_passed_to_analytics_and_chart_urls():
    report = {
        "summary": {
            "net_sales": 0,
            "eligible_order_count": 0,
            "average_order_value": None,
        },
        "monthly_revenue": [],
        "category_sales": [],
        "region_sales": [],
        "top_products": [],
        "month_over_month_growth": {
            "current_month": "2025-02",
            "current_revenue": 0.0,
            "previous_month": "2025-01",
            "previous_revenue": 0.0,
            "growth_percent": None,
            "status": "zero_previous_month_revenue",
        },
    }
    with patch("app.database.fetch_sales_data", return_value=[]) as fetch_data, patch(
        "app.database.fetch_product_count", return_value=8
    ), patch("app.analysis.analyze_sales", return_value=report) as analyze:
        with app.test_client() as client:
            response = client.get("/dashboard?start_date=2025-01-01&end_date=2025-02-28")

    assert response.status_code == 200
    assert fetch_data.call_args.kwargs == {
        "start_date": date(2025, 1, 1),
        "end_date": date(2025, 2, 28),
    }
    analyze.assert_called_once_with(
        [],
        start_date=date(2025, 1, 1),
        end_date=date(2025, 2, 28),
    )
    assert b"start_date=2025-01-01" in response.data
    assert b"end_date=2025-02-28" in response.data
    assert b"Revenue reflects the selected date range" in response.data


def test_dashboard_populates_and_preserves_actual_filter_options():
    with patch("app.database.fetch_sales_data", return_value=[]), patch(
        "app.database.fetch_product_count", return_value=8
    ):
        with app.test_client() as client:
            response = client.get("/dashboard?category=Home&region=West")

    assert response.status_code == 200
    assert re.search(rb'<option value="Electronics"\s*>Electronics</option>', response.data)
    assert b'value="Home" selected>Home</option>' in response.data
    assert b'value="West" selected>West</option>' in response.data
    assert b'value="">All categories</option>' in response.data
    assert b'value="">All regions</option>' in response.data
    assert b"category=Home" in response.data
    assert b"region=West" in response.data
    assert b"/exports/sales.csv" in response.data


@pytest.mark.parametrize(
    ("query", "expected_filters"),
    [
        ("category=Home", {"category": "Home"}),
        ("region=West", {"region": "West"}),
    ],
)
def test_dashboard_applies_each_dimension_filter(query, expected_filters):
    with patch("app.database.fetch_sales_data", return_value=[]) as fetch_data, patch(
        "app.database.fetch_product_count", return_value=3
    ) as product_count:
        with app.test_client() as client:
            response = client.get(f"/dashboard?{query}")

    assert response.status_code == 200
    assert fetch_data.call_args.kwargs == {
        "start_date": None,
        "end_date": None,
        **expected_filters,
    }
    if "category" in expected_filters:
        product_count.assert_called_once_with(category="Home")
    else:
        product_count.assert_called_once_with()


def test_dashboard_combines_date_category_and_region_filters_and_updates_mom():
    records = [
        {
            "order_id": 1,
            "order_status": "completed",
            "order_date": date(2025, 1, 15),
            "region": "West",
            "product_name": "Notebook",
            "category": "Home",
            "quantity": 1,
            "unit_price": 100,
            "discount_amount": 0,
            "returned_quantity": 0,
            "refund_amount": 0,
        },
        {
            "order_id": 2,
            "order_status": "delivered",
            "order_date": date(2025, 2, 15),
            "region": "West",
            "product_name": "Notebook",
            "category": "Home",
            "quantity": 1,
            "unit_price": 150,
            "discount_amount": 0,
            "returned_quantity": 0,
            "refund_amount": 0,
        },
    ]
    with patch("app.database.fetch_sales_data", return_value=records) as fetch_data, patch(
        "app.database.fetch_product_count", return_value=3
    ):
        with app.test_client() as client:
            response = client.get(
                "/dashboard?start_date=2025-01-01&end_date=2025-02-28"
                "&category=Home&region=West"
            )

    assert response.status_code == 200
    assert fetch_data.call_args.kwargs == {
        "start_date": date(2025, 1, 1),
        "end_date": date(2025, 2, 28),
        "category": "Home",
        "region": "West",
    }
    assert b"+50.00%" in response.data
    assert b"2025-02" in response.data
    assert b"2025-01" in response.data
    assert b"category=Home" in response.data
    assert b"region=West" in response.data


def test_dashboard_invalid_dimension_values_return_400_without_sales_query():
    with patch("app.database.fetch_sales_data") as fetch_data:
        with app.test_client() as client:
            response = client.get("/dashboard?category=Unknown")

    assert response.status_code == 400
    assert b"Invalid category filter" in response.data
    fetch_data.assert_not_called()


def test_dashboard_valid_filters_with_no_matches_show_empty_state():
    with patch("app.database.fetch_sales_data", return_value=[]), patch(
        "app.database.fetch_product_count", return_value=0
    ):
        with app.test_client() as client:
            response = client.get("/dashboard?category=Electronics&region=East")

    assert response.status_code == 200
    assert b"No qualifying sales for this date range." in response.data
    assert b'<option value="Electronics" selected>Electronics</option>' in response.data
    assert b'<option value="East" selected>East</option>' in response.data


def test_sales_csv_export_returns_filtered_eligible_sales_with_download_headers():
    records = [
        {
            "order_id": 10,
            "order_status": "delivered",
            "order_date": date(2025, 2, 3),
            "region": "West",
            "product_name": "Desk Lamp",
            "category": "Home",
            "quantity": 2,
            "unit_price": Decimal("25.00"),
            "discount_amount": Decimal("5.00"),
            "returned_quantity": 1,
            "refund_amount": Decimal("10.00"),
        },
        {
            "order_id": 11,
            "order_status": "cancelled",
            "order_date": date(2025, 2, 4),
            "region": "West",
            "product_name": "Cancelled Lamp",
            "category": "Home",
            "quantity": 1,
            "unit_price": Decimal("20.00"),
            "discount_amount": Decimal("0.00"),
            "returned_quantity": 0,
            "refund_amount": Decimal("0.00"),
        },
    ]
    with patch("app.database.fetch_sales_data", return_value=records) as fetch_data:
        with app.test_client() as client:
            response = client.get(
                "/exports/sales.csv?start_date=2025-02-01&end_date=2025-02-28"
                "&category=Home&region=West"
            )

    assert response.status_code == 200
    assert response.mimetype == "text/csv"
    assert response.headers["Content-Disposition"] == (
        'attachment; filename="sales-report.csv"'
    )
    assert response.headers["Cache-Control"] == "no-store"
    fetch_data.assert_called_once_with(
        start_date=date(2025, 2, 1),
        end_date=date(2025, 2, 28),
        category="Home",
        region="West",
    )
    rows = list(csv.DictReader(response.get_data(as_text=True).splitlines()))
    assert rows == [
        {
            "order_date": "2025-02-03",
            "order_id": "10",
            "product_name": "Desk Lamp",
            "category": "Home",
            "region": "West",
            "quantity": "2",
            "unit_price": "25.0",
            "gross_sales": "50.0",
            "discounts": "5.0",
            "refunds": "10.0",
            "net_sales": "35.0",
        }
    ]


def test_sales_csv_export_with_no_results_returns_header_only():
    with patch("app.database.fetch_sales_data", return_value=[]):
        with app.test_client() as client:
            response = client.get("/exports/sales.csv")

    assert response.status_code == 200
    assert list(csv.reader(response.get_data(as_text=True).splitlines())) == [
        list(analysis.SALES_EXPORT_COLUMNS)
    ]


@pytest.mark.parametrize(
    ("query", "message"),
    [
        ("category=Unknown", "Invalid category filter."),
        ("region=Unknown", "Invalid region filter."),
    ],
)
def test_sales_csv_export_rejects_invalid_dimension_filters(query, message):
    with patch("app.database.fetch_sales_data") as fetch_data:
        with app.test_client() as client:
            response = client.get(f"/exports/sales.csv?{query}")

    assert response.status_code == 400
    assert message.encode() in response.data
    fetch_data.assert_not_called()


def test_sales_csv_export_rejects_invalid_dates_without_sales_query():
    with patch("app.database.fetch_sales_data") as fetch_data:
        with app.test_client() as client:
            response = client.get("/exports/sales.csv?start_date=2025-02-31")

    assert response.status_code == 400
    assert b"YYYY-MM-DD" in response.data
    fetch_data.assert_not_called()


def test_sales_csv_export_handles_database_failure_without_leaking_details():
    with patch(
        "app.database.fetch_sales_data",
        side_effect=mysql.connector.Error("private database detail"),
    ):
        with app.test_client() as client:
            response = client.get("/exports/sales.csv?category=Home")

    assert response.status_code == 503
    assert b"database is unavailable" in response.data
    assert b"private database detail" not in response.data


def test_dashboard_renders_top_products_section():
    report = {
        "summary": {
            "net_sales": 0,
            "eligible_order_count": 0,
            "average_order_value": None,
        },
        "monthly_revenue": [],
        "category_sales": [],
        "region_sales": [],
        "month_over_month_growth": {
            "current_month": None,
            "current_revenue": None,
            "previous_month": None,
            "previous_revenue": None,
            "growth_percent": None,
            "status": "insufficient_history",
        },
        "top_products": [
            {
                "product_name": "Laptop",
                "category": "Electronics",
                "total_quantity": 5,
                "revenue": 340.0,
            }
        ],
    }
    with patch("app.database.fetch_sales_data", return_value=[]), patch(
        "app.database.fetch_product_count", return_value=8
    ), patch("app.analysis.analyze_sales", return_value=report):
        with app.test_client() as client:
            response = client.get("/dashboard")

    assert response.status_code == 200
    assert b"Top 5 best-selling products" in response.data
    assert b"Laptop" in response.data
    assert b"5" in response.data


def test_invalid_dashboard_date_range_returns_400_without_querying_database():
    with patch("app.database.fetch_sales_data") as fetch_data:
        with app.test_client() as client:
            response = client.get("/dashboard?start_date=not-a-date")

    assert response.status_code == 400
    assert b"YYYY-MM-DD" in response.data
    fetch_data.assert_not_called()


def test_health_endpoint_reports_database_connection():
    with patch("app.database.ping_database", return_value=True):
        with app.test_client() as client:
            response = client.get("/health")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok", "database": "connected"}


def test_health_endpoint_reports_database_unavailable():
    with patch(
        "app.database.ping_database",
        side_effect=mysql.connector.Error("private connection detail"),
    ):
        with app.test_client() as client:
            response = client.get("/health")

    assert response.status_code == 503
    assert response.get_json() == {
        "error": "The database is unavailable. Please try again later."
    }
    assert b"private connection detail" not in response.data


def test_products_api_returns_records_using_parameterized_pagination():
    product = {
        "product_id": 201,
        "product_name": "Wireless Headphones",
        "category": "Electronics",
    }
    with patch("app.database.fetch_all", return_value=[product]) as fetch_all:
        with app.test_client() as client:
            response = client.get("/api/products?limit=1&offset=2")

    assert response.status_code == 200
    assert response.get_json() == {
        "data": [product],
        "pagination": {"limit": 1, "offset": 2},
    }
    assert fetch_all.call_args.args[1] == (1, 2)
    assert "LIMIT %s OFFSET %s" in fetch_all.call_args.args[0]


def test_orders_api_returns_dates_as_json_strings():
    order = {
        "order_id": 1001,
        "order_status": "delivered",
        "order_date": date(2025, 1, 8),
        "region": "Northeast",
    }
    with patch("app.database.fetch_all", return_value=[order]):
        with app.test_client() as client:
            response = client.get("/api/orders")

    assert response.status_code == 200
    assert response.get_json()["data"][0]["order_date"] == "2025-01-08"


def test_order_items_api_selects_existing_schema_columns():
    item = {
        "order_item_id": 1,
        "order_id": 1001,
        "product_id": 203,
        "quantity": 1,
        "unit_price": "80.00",
        "discount_amount": "0.00",
        "returned_quantity": 0,
        "refund_amount": "0.00",
    }
    with patch("app.database.fetch_all", return_value=[item]) as fetch_all:
        with app.test_client() as client:
            response = client.get("/api/order-items")

    assert response.status_code == 200
    assert response.get_json()["data"] == [item]
    query = fetch_all.call_args.args[0]
    for column in (
        "order_item_id",
        "order_id",
        "product_id",
        "discount_amount",
        "returned_quantity",
        "refund_amount",
    ):
        assert column in query


def test_api_database_error_returns_safe_503_response():
    with patch(
        "app.database.fetch_all",
        side_effect=mysql.connector.Error("private connection detail"),
    ):
        with app.test_client() as client:
            response = client.get("/api/orders")

    assert response.status_code == 503
    assert response.get_json() == {
        "error": "The database is unavailable. Please try again later."
    }
    assert b"private connection detail" not in response.data


def test_invalid_pagination_returns_400_without_querying_database():
    with patch("app.database.fetch_all") as fetch_all:
        with app.test_client() as client:
            response = client.get("/api/products?limit=501")

    assert response.status_code == 400
    assert response.get_json() == {"error": "limit must be between 1 and 500."}
    fetch_all.assert_not_called()


def test_api_rejects_unsupported_http_method_with_405():
    with app.test_client() as client:
        response = client.post("/api/orders")

    assert response.status_code == 405
    assert "error" in response.get_json()


def test_analytics_summary_api_uses_database_sales_data():
    records = [
        {
            "order_id": 1001,
            "order_status": "delivered",
            "order_date": date(2025, 1, 8),
            "region": "Northeast",
            "product_name": "Coffee Maker",
            "category": "Home",
            "quantity": 1,
            "unit_price": 80,
            "discount_amount": 0,
            "returned_quantity": 0,
            "refund_amount": 0,
        }
    ]
    with patch("app.database.fetch_sales_data", return_value=records) as fetch_data:
        with app.test_client() as client:
            response = client.get("/api/analytics/summary")

    assert response.status_code == 200
    assert response.get_json() == {
        "gross_sales": 80.0,
        "discounts": 0.0,
        "refunds": 0.0,
        "net_sales": 80.0,
        "eligible_order_count": 1,
        "average_order_value": 80.0,
    }
    fetch_data.assert_called_once_with()


def test_analytics_api_returns_all_summary_tables():
    with patch("app.database.fetch_sales_data", return_value=[]):
        with app.test_client() as client:
            response = client.get("/api/analytics")

    assert response.status_code == 200
    assert set(response.get_json()) == {
        "summary",
        "monthly_revenue",
        "category_sales",
        "region_sales",
        "top_products",
        "month_over_month_growth",
        "insights",
    }


def test_top_products_api_returns_ranked_products_for_date_range():
    records = [
        {
            "order_id": 1,
            "order_status": "completed",
            "order_date": date(2025, 1, 8),
            "region": "Northeast",
            "product_name": "Laptop",
            "category": "Electronics",
            "quantity": 2,
            "unit_price": 70.00,
            "discount_amount": 10.00,
            "returned_quantity": 0,
            "refund_amount": 0.00,
        },
        {
            "order_id": 2,
            "order_status": "delivered",
            "order_date": date(2025, 2, 10),
            "region": "West",
            "product_name": "Desk Lamp",
            "category": "Home",
            "quantity": 3,
            "unit_price": 20.00,
            "discount_amount": 0.00,
            "returned_quantity": 0,
            "refund_amount": 0.00,
        },
    ]
    with patch("app.database.fetch_sales_data", return_value=records):
        with app.test_client() as client:
            response = client.get(
                "/api/analytics/top-products?start_date=2025-01-01&end_date=2025-02-28"
            )

    assert response.status_code == 200
    assert response.get_json() == {
        "data": [
            {
                "product_name": "Desk Lamp",
                "category": "Home",
                "total_quantity": 3,
                "revenue": 60.0,
            },
            {
                "product_name": "Laptop",
                "category": "Electronics",
                "total_quantity": 2,
                "revenue": 130.0,
            },
        ]
    }


def test_analytics_api_accepts_parameterized_date_range():
    with patch("app.database.fetch_sales_data", return_value=[]) as fetch_data:
        with app.test_client() as client:
            response = client.get(
                "/api/analytics/summary?start_date=2025-01-01&end_date=2025-03-31"
            )

    assert response.status_code == 200
    assert fetch_data.call_args.kwargs == {
        "start_date": date(2025, 1, 1),
        "end_date": date(2025, 3, 31),
    }


def test_analytics_api_applies_combined_category_region_and_date_filters():
    records = [
        {
            "order_id": 1,
            "order_status": "completed",
            "order_date": date(2025, 1, 8),
            "region": "West",
            "product_name": "Notebook",
            "category": "Home",
            "quantity": 1,
            "unit_price": 80,
            "discount_amount": 0,
            "returned_quantity": 0,
            "refund_amount": 0,
        }
    ]
    with patch("app.database.fetch_sales_data", return_value=records) as fetch_data:
        with app.test_client() as client:
            response = client.get(
                "/api/analytics/summary?start_date=2025-01-01"
                "&end_date=2025-01-31&category=Home&region=West"
            )

    assert response.status_code == 200
    assert response.get_json()["net_sales"] == 80.0
    fetch_data.assert_called_once_with(
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
        category="Home",
        region="West",
    )


def test_analytics_api_rejects_invalid_dimension_filter():
    with patch("app.database.fetch_sales_data") as fetch_data:
        with app.test_client() as client:
            response = client.get("/api/analytics?region=Unknown")

    assert response.status_code == 400
    assert response.get_json() == {"error": "Invalid region filter."}
    fetch_data.assert_not_called()


def test_invalid_api_date_range_returns_400():
    with patch("app.database.fetch_sales_data") as fetch_data:
        with app.test_client() as client:
            response = client.get("/api/analytics?start_date=2025-02-31")

    assert response.status_code == 400
    assert "error" in response.get_json()
    fetch_data.assert_not_called()


def test_chart_endpoint_returns_png_and_uses_filtered_analytics():
    report = {
        "monthly_revenue": [
            {
                "month": "2025-01",
                "revenue": 100.0,
                "month_over_month_growth_percent": None,
            }
        ]
    }
    with patch("app.database.fetch_sales_data", return_value=[]), patch(
        "app.analysis.analyze_sales", return_value=report
    ), patch("app.charts.generate_chart", return_value=BytesIO(b"png")) as generate:
        with app.test_client() as client:
            response = client.get(
                "/charts/monthly-revenue.png?start_date=2025-01-01"
            )

    assert response.status_code == 200
    assert response.mimetype == "image/png"
    generate.assert_called_once_with("monthly-revenue", report)


def test_chart_endpoint_applies_category_and_region_filters():
    report = {"category_sales": [], "region_sales": []}
    with patch("app.database.fetch_sales_data", return_value=[]) as fetch_data, patch(
        "app.analysis.analyze_sales", return_value=report
    ), patch("app.charts.generate_chart", return_value=BytesIO(b"png")):
        with app.test_client() as client:
            response = client.get(
                "/charts/category-sales.png?category=Home&region=West"
            )

    assert response.status_code == 200
    fetch_data.assert_called_once_with(
        start_date=None,
        end_date=None,
        category="Home",
        region="West",
    )


def test_chart_generation_failure_shows_dashboard_error():
    report = {"category_sales": []}
    with patch("app.database.fetch_sales_data", return_value=[]), patch(
        "app.analysis.analyze_sales", return_value=report
    ), patch("app.charts.generate_chart", side_effect=RuntimeError("chart issue")):
        with app.test_client() as client:
            response = client.get("/charts/category-sales.png")

    assert response.status_code == 500
    assert b"A chart could not be generated" in response.data


def test_add_product_form_renders_template():
    with app.test_client() as client:
        response = client.get("/products/new")

    assert response.status_code == 200
    assert b"Add Product" in response.data
    assert b"Product name" in response.data
    assert b"Unit price" in response.data


def test_add_product_submit_success_redirects_to_dashboard():
    with patch("app.database.add_product", return_value=999) as add_product:
        with app.test_client() as client:
            response = client.post(
                "/products/new",
                data={
                    "product_name": "Solar Desk Lamp",
                    "category": "Home",
                    "unit_price": "49.95",
                },
                follow_redirects=False,
            )

    assert response.status_code == 302
    assert response.headers["Location"] == "/dashboard"
    add_product.assert_called_once_with(
        product_name="Solar Desk Lamp",
        category="Home",
        unit_price=Decimal("49.95"),
    )


def test_add_product_submit_rejects_invalid_product_values():
    with app.test_client() as client:
        response = client.post(
            "/products/new",
            data={
                "product_name": "",
                "category": "",
                "unit_price": "-1",
            },
        )

    assert response.status_code == 400
    assert b"Product name is required." in response.data
    assert b"Category is required." in response.data
    assert b"Unit price must be a positive number." in response.data


def test_add_product_submit_handles_duplicate_name():
    with patch(
        "app.database.add_product",
        side_effect=ValueError("A product with this name already exists."),
    ):
        with app.test_client() as client:
            response = client.post(
                "/products/new",
                data={
                    "product_name": "Wireless Headphones",
                    "category": "Electronics",
                    "unit_price": "59.99",
                },
            )

    assert response.status_code == 400
    assert b"A product with this name already exists." in response.data


def test_add_product_submit_handles_database_failure_safely():
    with patch(
        "app.database.add_product",
        side_effect=mysql.connector.Error("private db detail"),
    ):
        with app.test_client() as client:
            response = client.post(
                "/products/new",
                data={
                    "product_name": "Test Product",
                    "category": "Home",
                    "unit_price": "19.99",
                },
            )

    assert response.status_code == 503
    assert b"The database is unavailable. Please try again later." in response.data
    assert b"private db detail" not in response.data
