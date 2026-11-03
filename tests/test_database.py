from decimal import Decimal
from datetime import date
from unittest.mock import MagicMock, patch

import mysql.connector

import database


def test_fetch_all_uses_dictionary_cursor_rows():
    cursor = MagicMock()
    cursor.fetchall.return_value = [{"healthy": 1}]
    connection = MagicMock()
    connection.cursor.return_value = cursor

    with patch("database.get_connection", return_value=connection):
        rows = database.fetch_all("SELECT 1 AS healthy")

    assert rows == [{"healthy": 1}]
    connection.cursor.assert_called_once_with(dictionary=True)


def test_fetch_sales_data_uses_parameterized_inclusive_date_filters():
    with patch("database.fetch_all", return_value=[]) as fetch_all:
        database.fetch_sales_data(
            start_date="2025-01-01",
            end_date="2025-01-31",
        )

    query, params = fetch_all.call_args.args
    assert "o.order_date >= %s" in query
    assert "o.order_date <= %s" in query
    assert params == ("2025-01-01", "2025-01-31")


def test_fetch_sales_data_uses_parameterized_category_and_region_filters():
    with patch("database.fetch_all", return_value=[]) as fetch_all:
        database.fetch_sales_data(category="Home", region="West")

    query, params = fetch_all.call_args.args
    assert "p.category = %s" in query
    assert "o.region = %s" in query
    assert params == ("Home", "West")


def test_fetch_sales_data_combines_date_category_and_region_filters():
    with patch("database.fetch_all", return_value=[]) as fetch_all:
        database.fetch_sales_data(
            start_date="2025-01-01",
            end_date="2025-01-31",
            category="Home",
            region="West",
        )

    query, params = fetch_all.call_args.args
    assert "o.order_date >= %s" in query
    assert "o.order_date <= %s" in query
    assert "p.category = %s" in query
    assert "o.region = %s" in query
    assert params == ("2025-01-01", "2025-01-31", "Home", "West")


def test_fetch_sales_data_without_dates_preserves_full_sales_query():
    with patch("database.fetch_all", return_value=[]) as fetch_all:
        database.fetch_sales_data()

    query, params = fetch_all.call_args.args
    assert "WHERE" not in query
    assert "FROM orders AS o" in query
    assert params == ()


def test_fetch_product_count_returns_database_count():
    with patch(
        "database.fetch_all",
        return_value=[{"product_count": 8}],
    ) as fetch_all:
        product_count = database.fetch_product_count()

    assert product_count == 8
    assert "COUNT(*)" in fetch_all.call_args.args[0]


def test_fetch_product_count_can_be_limited_to_selected_category():
    with patch(
        "database.fetch_all",
        return_value=[{"product_count": 3}],
    ) as fetch_all:
        product_count = database.fetch_product_count(category="Home")

    assert product_count == 3
    assert "category = %s" in fetch_all.call_args.args[0]
    assert fetch_all.call_args.args[1] == ("Home",)


def test_fetch_filter_options_returns_actual_categories_and_regions():
    rows = [
        {"filter_name": "category", "filter_value": "Books"},
        {"filter_name": "category", "filter_value": "Home"},
        {"filter_name": "region", "filter_value": "East"},
        {"filter_name": "region", "filter_value": "West"},
    ]
    with patch("database.fetch_all", return_value=rows) as fetch_all:
        options = database.fetch_filter_options()

    assert options == {
        "categories": ["Books", "Home"],
        "regions": ["East", "West"],
    }
    query = fetch_all.call_args.args[0]
    assert "FROM products" in query
    assert "FROM orders" in query
    assert "UNION ALL" in query


def test_add_product_uses_parameterized_insert_and_validates_positive_price():
    mock_cursor = MagicMock()
    mock_cursor.lastrowid = 999
    mock_connection = MagicMock()
    mock_connection.cursor.return_value = mock_cursor

    with patch("database.get_connection", return_value=mock_connection):
        product_id = database.add_product(
            product_name="Portable Blender",
            category="Home",
            unit_price="59.99",
        )

    assert product_id == 999
    mock_cursor.execute.assert_called_once()
    sql, params = mock_cursor.execute.call_args.args
    assert "INSERT INTO products" in sql
    assert params == ("Portable Blender", "Home", Decimal("59.99"))

    try:
        database.add_product("", "Home", "59.99")
    except ValueError as exc:
        assert "Product name is required." in str(exc)
    else:
        raise AssertionError("Expected ValueError for empty product name")

    try:
        database.add_product("Coffee Grinder", "Home", "0")
    except ValueError as exc:
        assert "positive number" in str(exc)
    else:
        raise AssertionError("Expected ValueError for non-positive price")


def _import_rows():
    return [
        {
            "order_reference": "GROUP-1",
            "order_date": date(2025, 4, 1),
            "order_status": "completed",
            "region": "West",
            "product_name": "New Mug",
            "category": "Home",
            "quantity": 2,
            "unit_price": Decimal("10.00"),
            "discount_amount": Decimal("1.00"),
            "returned_quantity": 1,
            "refund_amount": Decimal("4.00"),
        },
        {
            "order_reference": "GROUP-1",
            "order_date": date(2025, 4, 1),
            "order_status": "completed",
            "region": "West",
            "product_name": "New Notebook",
            "category": "Home",
            "quantity": 1,
            "unit_price": Decimal("5.00"),
            "discount_amount": Decimal("0.00"),
            "returned_quantity": 0,
            "refund_amount": Decimal("0.00"),
        },
    ]


def test_import_sales_rows_writes_order_items_and_import_marker_in_one_transaction():
    cursor = MagicMock()
    cursor.lastrowid = 900
    cursor.fetchone.return_value = None
    connection = MagicMock()
    connection.cursor.return_value = cursor

    with patch("database.get_connection", return_value=connection):
        result = database.import_sales_rows(_import_rows(), "a" * 64)

    assert result == {
        "already_imported": False,
        "orders_imported": 1,
        "items_imported": 2,
        "products_created": 2,
        "products_matched": 0,
    }
    executed = cursor.execute.call_args_list
    assert "CREATE TABLE IF NOT EXISTS sales_import_batches" in executed[0].args[0]
    assert "INSERT INTO sales_import_batches" in executed[1].args[0]
    assert any("INSERT INTO orders" in call.args[0] for call in executed)
    item_inserts = [call for call in executed if "INSERT INTO order_items" in call.args[0]]
    assert len(item_inserts) == 2
    assert all("%s" in call.args[0] for call in executed if "INSERT INTO" in call.args[0])
    assert connection.commit.call_count == 2
    connection.close.assert_called_once()


def test_import_sales_rows_detects_duplicate_batch_key_without_writing_sales():
    cursor = MagicMock()
    cursor.execute.side_effect = [
        None,
        mysql.connector.IntegrityError("duplicate", errno=1062),
    ]
    connection = MagicMock()
    connection.cursor.return_value = cursor

    with patch("database.get_connection", return_value=connection):
        result = database.import_sales_rows(_import_rows(), "b" * 64)

    assert result == {"already_imported": True}
    assert cursor.execute.call_count == 2
    connection.rollback.assert_called_once()
    connection.close.assert_called_once()


def test_import_sales_rows_rolls_back_everything_on_item_insert_failure():
    cursor = MagicMock()
    cursor.lastrowid = 900
    cursor.fetchone.return_value = None

    def fail_on_order_item(sql, _params=None):
        if "INSERT INTO order_items" in sql:
            raise mysql.connector.Error("insert failed")

    cursor.execute.side_effect = fail_on_order_item
    connection = MagicMock()
    connection.cursor.return_value = cursor

    with patch("database.get_connection", return_value=connection):
        try:
            database.import_sales_rows(_import_rows(), "c" * 64)
        except mysql.connector.Error:
            pass
        else:
            raise AssertionError("Expected database error")

    connection.rollback.assert_called_once()
    connection.close.assert_called_once()
