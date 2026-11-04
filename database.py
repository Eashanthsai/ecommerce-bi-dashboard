"""Small MySQL access helpers for read-only dashboard/API requests."""

from decimal import Decimal, InvalidOperation

import mysql.connector

from config import get_database_config


IMPORT_BATCH_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS sales_import_batches (
        content_sha256 CHAR(64) NOT NULL,
        imported_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        orders_imported INT UNSIGNED NOT NULL DEFAULT 0,
        items_imported INT UNSIGNED NOT NULL DEFAULT 0,
        products_created INT UNSIGNED NOT NULL DEFAULT 0,
        products_matched INT UNSIGNED NOT NULL DEFAULT 0,
        PRIMARY KEY (content_sha256)
    ) ENGINE=InnoDB
"""


SALES_DATA_QUERY = """
    SELECT o.order_id, o.order_status, o.order_date, o.region,
           p.product_name, p.category, oi.quantity, oi.unit_price,
           oi.discount_amount, oi.returned_quantity, oi.refund_amount
    FROM orders AS o
    INNER JOIN order_items AS oi ON oi.order_id = o.order_id
    INNER JOIN products AS p ON p.product_id = oi.product_id
    ORDER BY o.order_date, o.order_id, oi.order_item_id
"""


def get_connection():
    """Open a MySQL connection using the environment-based configuration."""
    return mysql.connector.connect(**get_database_config())


def fetch_all(sql, params=()):
    """Execute a parameterized read query and return dictionary rows."""
    connection = get_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute(sql, params)
            return cursor.fetchall()
        finally:
            cursor.close()
    finally:
        connection.close()


def ping_database():
    """Return whether MySQL responds to a simple health-check query."""
    rows = fetch_all("SELECT 1 AS healthy")
    return bool(rows and rows[0].get("healthy") == 1)


def fetch_sales_data(
    start_date=None,
    end_date=None,
    category=None,
    region=None,
):
    """Return joined order-item data filtered by the supplied dashboard values."""
    conditions = []
    params = []
    if start_date is not None:
        conditions.append("o.order_date >= %s")
        params.append(start_date)
    if end_date is not None:
        conditions.append("o.order_date <= %s")
        params.append(end_date)
    if category is not None:
        conditions.append("p.category = %s")
        params.append(category)
    if region is not None:
        conditions.append("o.region = %s")
        params.append(region)

    query = SALES_DATA_QUERY
    if conditions:
        query = query.replace(
            "    ORDER BY",
            "    WHERE " + " AND ".join(conditions) + "\n    ORDER BY",
        )
    return fetch_all(query, tuple(params))


def fetch_filter_options():
    """Return actual category and region values for dashboard filter controls."""
    rows = fetch_all(
        """
        SELECT 'category' AS filter_name, category AS filter_value
        FROM products
        WHERE category IS NOT NULL
        GROUP BY category
        UNION ALL
        SELECT 'region' AS filter_name, region AS filter_value
        FROM orders
        WHERE region IS NOT NULL
        GROUP BY region
        ORDER BY filter_name, filter_value
        """
    )
    options = {"categories": [], "regions": []}
    for row in rows:
        option_key = "categories" if row["filter_name"] == "category" else "regions"
        options[option_key].append(row["filter_value"])
    return options


def fetch_product_count(category=None):
    """Return catalog product count, optionally limited to one category."""
    sql = "SELECT COUNT(*) AS product_count FROM products"
    params = ()
    if category is not None:
        sql += " WHERE category = %s"
        params = (category,)
    rows = fetch_all(sql, params)
    return int(rows[0]["product_count"])


def fetch_orders(
    start_date=None,
    end_date=None,
    status=None,
    region=None,
    limit=100,
    offset=0,
):
    """Return a page of orders with their item counts and the total matching count."""
    conditions = []
    params = []
    if start_date is not None:
        conditions.append("o.order_date >= %s")
        params.append(start_date)
    if end_date is not None:
        conditions.append("o.order_date <= %s")
        params.append(end_date)
    if status is not None:
        conditions.append("o.order_status = %s")
        params.append(status)
    if region is not None:
        conditions.append("o.region = %s")
        params.append(region)

    where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
    rows = fetch_all(
        """
        SELECT o.order_id, o.order_status, o.order_date, o.region,
               COUNT(oi.order_item_id) AS item_count
        FROM orders AS o
        LEFT JOIN order_items AS oi ON oi.order_id = o.order_id
        """
        + where_clause
        + """
        GROUP BY o.order_id, o.order_status, o.order_date, o.region
        ORDER BY o.order_date DESC, o.order_id DESC
        LIMIT %s OFFSET %s
        """,
        (*params, limit, offset),
    )
    count_rows = fetch_all(
        "SELECT COUNT(*) AS order_count FROM orders AS o" + where_clause,
        tuple(params),
    )
    return rows, int(count_rows[0]["order_count"])


def fetch_order_statuses():
    """Return order status values actually present in the database."""
    rows = fetch_all(
        "SELECT DISTINCT order_status FROM orders ORDER BY order_status"
    )
    return [row["order_status"] for row in rows]


def add_product(product_name, category, unit_price):
    """Insert a new product row and return its generated identifier."""
    cleaned_name = (product_name or "").strip()
    cleaned_category = (category or "").strip()
    if not cleaned_name:
        raise ValueError("Product name is required.")
    if len(cleaned_name) > 120:
        raise ValueError("Product name is too long. Maximum length is 120 characters.")
    if not cleaned_category:
        raise ValueError("Category is required.")
    if len(cleaned_category) > 80:
        raise ValueError("Category is too long. Maximum length is 80 characters.")

    try:
        price = Decimal(str(unit_price))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Unit price must be a valid number.") from exc

    if price <= 0:
        raise ValueError("Unit price must be a positive number.")
    if price > Decimal("9999999.99"):
        raise ValueError("Unit price is too large.")

    connection = get_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute(
                """
                INSERT INTO products (product_name, category, unit_price)
                VALUES (%s, %s, %s)
                """,
                (cleaned_name, cleaned_category, price),
            )
            connection.commit()
            return cursor.lastrowid
        except mysql.connector.IntegrityError as exc:
            connection.rollback()
            if exc.errno == 1062:
                raise ValueError("A product with this name already exists.") from exc
            raise
        finally:
            cursor.close()
    finally:
        connection.close()


def import_sales_rows(rows, content_sha256):
    """Atomically persist a validated CSV and prevent importing its bytes twice."""
    connection = get_connection()
    cursor = None
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(IMPORT_BATCH_TABLE_SQL)
        connection.commit()

        try:
            cursor.execute(
                """
                INSERT INTO sales_import_batches (content_sha256)
                VALUES (%s)
                """,
                (content_sha256,),
            )
        except mysql.connector.IntegrityError as exc:
            connection.rollback()
            if exc.errno == 1062:
                return {"already_imported": True}
            raise

        grouped_orders = {}
        for row in rows:
            grouped_orders.setdefault(row["order_reference"], []).append(row)

        product_ids = {}
        products_created = set()
        products_matched = set()
        items_imported = 0
        for order_rows in grouped_orders.values():
            first = order_rows[0]
            cursor.execute(
                """
                INSERT INTO orders (order_status, order_date, region)
                VALUES (%s, %s, %s)
                """,
                (first["order_status"], first["order_date"], first["region"]),
            )
            order_id = cursor.lastrowid

            for row in order_rows:
                product_name = row["product_name"]
                product_key = product_name.casefold()
                product_id = product_ids.get(product_key)
                if product_id is None:
                    cursor.execute(
                        """
                        SELECT product_id, category
                        FROM products
                        WHERE product_name = %s
                        """,
                        (product_name,),
                    )
                    product = cursor.fetchone()
                    if product is not None:
                        if product["category"] != row["category"]:
                            raise ValueError(
                                f"Product '{product_name}' already exists in a different category."
                            )
                        product_id = product["product_id"]
                        products_matched.add(product_key)
                    else:
                        if row["unit_price"] <= Decimal("0.00"):
                            raise ValueError(
                                f"New product '{product_name}' must have a positive unit price."
                            )
                        cursor.execute(
                            """
                            INSERT INTO products (product_name, category, unit_price)
                            VALUES (%s, %s, %s)
                            """,
                            (product_name, row["category"], row["unit_price"]),
                        )
                        product_id = cursor.lastrowid
                        products_created.add(product_key)
                    product_ids[product_key] = product_id

                cursor.execute(
                    """
                    INSERT INTO order_items (
                        order_id, product_id, quantity, unit_price,
                        discount_amount, returned_quantity, refund_amount
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        order_id,
                        product_id,
                        row["quantity"],
                        row["unit_price"],
                        row["discount_amount"],
                        row["returned_quantity"],
                        row["refund_amount"],
                    ),
                )
                items_imported += 1

        order_count = len(grouped_orders)
        products_created_count = len(products_created)
        products_matched_count = len(products_matched)
        cursor.execute(
            """
            UPDATE sales_import_batches
            SET orders_imported = %s, items_imported = %s,
                products_created = %s, products_matched = %s
            WHERE content_sha256 = %s
            """,
            (
                order_count,
                items_imported,
                products_created_count,
                products_matched_count,
                content_sha256,
            ),
        )
        connection.commit()
        return {
            "already_imported": False,
            "orders_imported": order_count,
            "items_imported": items_imported,
            "products_created": products_created_count,
            "products_matched": products_matched_count,
        }
    except Exception:
        connection.rollback()
        raise
    finally:
        if cursor is not None:
            cursor.close()
        connection.close()
