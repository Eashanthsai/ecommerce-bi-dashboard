"""Validation helpers for CSV sales import previews."""

import csv
import hashlib
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from io import StringIO


MAX_IMPORT_ROWS = 5000
MAX_AMOUNT = Decimal("9999999.99")
REQUIRED_COLUMNS = (
    "order_reference",
    "order_date",
    "order_status",
    "region",
    "product_name",
    "category",
    "quantity",
    "unit_price",
    "discount_amount",
    "returned_quantity",
    "refund_amount",
)


def validate_sales_csv(content):
    """Decode and validate a complete CSV; any row errors block the import."""
    digest = hashlib.sha256(content).hexdigest()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return [], [{"line": 1, "message": "File must use UTF-8 text encoding."}], digest

    try:
        reader = csv.DictReader(StringIO(text, newline=""))
        headers = reader.fieldnames or []
        if len(headers) != len(set(headers)):
            return [], [{"line": 1, "message": "CSV column names must be unique."}], digest
        missing = [column for column in REQUIRED_COLUMNS if column not in headers]
        if missing:
            return [], [
                {
                    "line": 1,
                    "message": "Missing required columns: " + ", ".join(missing),
                }
            ], digest

        rows = []
        errors = []
        orders = {}
        seen_order_products = set()
        for line_number, raw in enumerate(reader, start=2):
            if line_number > MAX_IMPORT_ROWS + 1:
                errors.append(
                    {
                        "line": line_number,
                        "message": f"File exceeds the {MAX_IMPORT_ROWS}-row limit.",
                    }
                )
                break

            try:
                row = _validate_row(raw)
                reference = row["order_reference"]
                order_details = (
                    row["order_date"],
                    row["order_status"],
                    row["region"],
                )
                if reference in orders and orders[reference] != order_details:
                    raise ValueError(
                        "Rows with the same order_reference must share date, status, and region."
                    )
                orders[reference] = order_details

                order_product = (reference, row["product_name"].casefold())
                if order_product in seen_order_products:
                    raise ValueError(
                        "A product may appear only once per order; combine its quantity on one row."
                    )
                seen_order_products.add(order_product)
                rows.append(row)
            except (ValueError, InvalidOperation) as exc:
                errors.append({"line": line_number, "message": str(exc)})

        if not errors:
            canonical_rows = []
            for row in rows:
                canonical_rows.append(
                    [
                        row["order_reference"],
                        row["order_date"].isoformat(),
                        row["order_status"],
                        row["region"],
                        row["product_name"],
                        row["category"],
                        row["quantity"],
                        format(row["unit_price"], ".2f"),
                        format(row["discount_amount"], ".2f"),
                        row["returned_quantity"],
                        format(row["refund_amount"], ".2f"),
                    ]
                )
            canonical_rows.sort()
            digest = hashlib.sha256(
                json.dumps(canonical_rows, ensure_ascii=False, separators=(",", ":")).encode(
                    "utf-8"
                )
            ).hexdigest()
        return rows, errors, digest
    except csv.Error as exc:
        return [], [{"line": 1, "message": f"CSV parsing failed: {exc}"}], digest


def _validate_row(raw):
    if None in raw:
        raise ValueError("Row contains more columns than the CSV header.")
    cleaned = {key: (value or "").strip() for key, value in raw.items()}
    for column in REQUIRED_COLUMNS:
        if not cleaned.get(column):
            raise ValueError(f"{column} is required.")

    reference = cleaned["order_reference"]
    product_name = cleaned["product_name"]
    category = cleaned["category"]
    region = cleaned["region"]
    if len(reference) > 120:
        raise ValueError("order_reference must be at most 120 characters.")
    if len(product_name) > 120:
        raise ValueError("product_name must be at most 120 characters.")
    if len(category) > 80:
        raise ValueError("category must be at most 80 characters.")
    if len(region) > 80:
        raise ValueError("region must be at most 80 characters.")

    try:
        order_date = datetime.strptime(cleaned["order_date"], "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("order_date must use YYYY-MM-DD format.") from exc
    if order_date.isoformat() != cleaned["order_date"]:
        raise ValueError("order_date must use YYYY-MM-DD format.")

    order_status = cleaned["order_status"].lower()
    if order_status not in {"completed", "delivered", "cancelled"}:
        raise ValueError("order_status must be completed, delivered, or cancelled.")

    try:
        quantity = int(cleaned["quantity"])
        returned_quantity = int(cleaned["returned_quantity"])
        unit_price = Decimal(cleaned["unit_price"])
        discount_amount = Decimal(cleaned["discount_amount"])
        refund_amount = Decimal(cleaned["refund_amount"])
    except (ValueError, InvalidOperation) as exc:
        raise ValueError("Quantity and amount fields must be valid numbers.") from exc

    if not 1 <= quantity <= 65535:
        raise ValueError("quantity must be an integer between 1 and 65535.")
    if not 0 <= returned_quantity <= quantity:
        raise ValueError("returned_quantity must be between zero and quantity.")
    for field, value in (
        ("unit_price", unit_price),
        ("discount_amount", discount_amount),
        ("refund_amount", refund_amount),
    ):
        if not value.is_finite() or value < 0 or value > MAX_AMOUNT:
            raise ValueError(f"{field} must be between 0.00 and 9,999,999.99.")
        if value.as_tuple().exponent < -2:
            raise ValueError(f"{field} must have no more than two decimal places.")

    gross_sales = quantity * unit_price
    if discount_amount > gross_sales:
        raise ValueError("discount_amount cannot exceed quantity times unit_price.")
    if refund_amount > gross_sales - discount_amount:
        raise ValueError("refund_amount cannot exceed discounted line sales.")
    if (returned_quantity == 0) != (refund_amount == 0):
        raise ValueError(
            "refund_amount must be zero when nothing was returned and positive otherwise."
        )

    return {
        "order_reference": reference,
        "order_date": order_date,
        "order_status": order_status,
        "region": region,
        "product_name": product_name,
        "category": category,
        "quantity": quantity,
        "unit_price": unit_price,
        "discount_amount": discount_amount,
        "returned_quantity": returned_quantity,
        "refund_amount": refund_amount,
    }
