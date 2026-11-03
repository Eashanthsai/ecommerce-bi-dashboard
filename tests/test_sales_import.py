from io import BytesIO
import re
from unittest.mock import patch

import mysql.connector

from app import app
from sales_import import validate_sales_csv


CSV_HEADER = (
    "order_reference,order_date,order_status,region,product_name,category,"
    "quantity,unit_price,discount_amount,returned_quantity,refund_amount\n"
)
VALID_ROWS = (
    "SHOP-001,2025-04-01,completed,West,Tea Mug,Home,2,10.00,1.00,1,4.00\n"
    "SHOP-001,2025-04-01,completed,West,Notebook,Home,1,5.00,0.00,0,0.00\n"
    "SHOP-002,2025-04-02,delivered,East,Tea Mug,Home,1,10.00,0.00,0,0.00\n"
)


def test_sales_csv_validation_groups_multiple_items_and_normalizes_fingerprint():
    content = (CSV_HEADER + VALID_ROWS).encode("utf-8")
    rows, errors, digest = validate_sales_csv(content)

    assert errors == []
    assert len(rows) == 3
    assert rows[0]["order_reference"] == rows[1]["order_reference"]
    assert rows[0]["unit_price"].as_tuple().exponent == -2

    reversed_rows, reversed_errors, reversed_digest = validate_sales_csv(
        (CSV_HEADER + "".join(reversed(VALID_ROWS.splitlines(keepends=True)))).encode("utf-8")
    )
    assert reversed_errors == []
    assert len(reversed_rows) == 3
    assert reversed_digest == digest


def test_sales_csv_validation_rejects_bad_date_and_excess_discount():
    invalid = (
        CSV_HEADER
        + "ORDER-A,2025-02-30,completed,West,Item A,Home,1,10.00,0,0,0\n"
        + "ORDER-B,2025-02-20,completed,West,Item B,Home,1,10.00,11.00,0,0\n"
    ).encode("utf-8")

    rows, errors, _digest = validate_sales_csv(invalid)

    assert rows == []
    assert [error["line"] for error in errors] == [2, 3]
    assert "YYYY-MM-DD" in errors[0]["message"]
    assert "cannot exceed" in errors[1]["message"]


def test_sales_csv_validation_rejects_conflicting_order_data_and_duplicate_items():
    invalid = (
        CSV_HEADER
        + "ORDER-A,2025-02-20,completed,West,Item A,Home,1,10.00,0,0,0\n"
        + "ORDER-A,2025-02-21,completed,West,Item B,Home,1,10.00,0,0,0\n"
        + "ORDER-B,2025-02-20,completed,West,Item A,Home,1,10.00,0,0,0\n"
        + "ORDER-B,2025-02-20,completed,West,Item A,Home,1,10.00,0,0,0\n"
    ).encode("utf-8")

    _rows, errors, _digest = validate_sales_csv(invalid)

    assert len(errors) == 2
    assert "same order_reference" in errors[0]["message"]
    assert "only once per order" in errors[1]["message"]


def test_sample_csv_download_has_import_columns_and_attachment_header():
    with app.test_client() as client:
        response = client.get("/imports/sample.csv")

    assert response.status_code == 200
    assert response.mimetype == "text/csv"
    assert "attachment; filename=\"sales-import-template.csv\"" in response.headers[
        "Content-Disposition"
    ]
    assert response.data.decode("utf-8").splitlines()[0] == CSV_HEADER.strip()


def test_import_preview_shows_rows_and_requires_explicit_confirmation():
    with app.test_client() as client, patch(
        "app.database.import_sales_rows"
    ) as import_rows:
        response = client.post(
            "/imports/preview",
            data={"file": (BytesIO((CSV_HEADER + VALID_ROWS).encode("utf-8")), "sales.csv")},
            content_type="multipart/form-data",
        )

    assert response.status_code == 200
    assert b"CSV preview" in response.data
    assert b"Confirm and import all rows" in response.data
    import_rows.assert_not_called()


def test_invalid_import_preview_reports_errors_without_database_writes():
    invalid_csv = (CSV_HEADER + "ORDER-A,invalid,completed,West,Item,Home,1,3,0,0,0\n").encode(
        "utf-8"
    )
    with app.test_client() as client, patch(
        "app.database.import_sales_rows"
    ) as import_rows:
        response = client.post(
            "/imports/preview",
            data={"file": (BytesIO(invalid_csv), "sales.csv")},
            content_type="multipart/form-data",
        )

    assert response.status_code == 400
    assert b"order_date must use YYYY-MM-DD" in response.data
    import_rows.assert_not_called()


def test_import_preview_rejects_non_csv_file_names():
    with app.test_client() as client:
        response = client.post(
            "/imports/preview",
            data={"file": (BytesIO(b"not csv"), "sales.txt")},
            content_type="multipart/form-data",
        )

    assert response.status_code == 400
    assert b"Only .csv files are supported" in response.data


def test_import_preview_requires_a_selected_file():
    with app.test_client() as client:
        response = client.post("/imports/preview")

    assert response.status_code == 400
    assert b"Choose a CSV file to upload" in response.data


def test_confirm_import_calls_transaction_and_redirects_after_commit():
    with app.test_client() as client, patch(
        "app.database.import_sales_rows",
        return_value={
            "already_imported": False,
            "orders_imported": 2,
            "items_imported": 3,
            "products_created": 2,
            "products_matched": 0,
        },
    ) as import_rows:
        preview = client.post(
            "/imports/preview",
            data={"file": (BytesIO((CSV_HEADER + VALID_ROWS).encode("utf-8")), "sales.csv")},
            content_type="multipart/form-data",
        )
        token = re.search(
            rb'name="preview_token" value="([a-f0-9]+)"', preview.data
        ).group(1).decode("ascii")
        response = client.post("/imports/confirm", data={"preview_token": token})

    assert response.status_code == 302
    assert response.headers["Location"] == "/dashboard"
    rows, digest = import_rows.call_args.args
    assert len(rows) == 3
    assert len(digest) == 64


def test_confirm_import_reports_exact_duplicate_without_claiming_new_rows():
    with app.test_client() as client, patch(
        "app.database.import_sales_rows", return_value={"already_imported": True}
    ) as import_rows, patch("app.database.fetch_sales_data", return_value=[]), patch(
        "app.database.fetch_product_count", return_value=0
    ), patch(
        "app.database.fetch_filter_options",
        return_value={"categories": [], "regions": []},
    ):
        preview = client.post(
            "/imports/preview",
            data={"file": (BytesIO((CSV_HEADER + VALID_ROWS).encode("utf-8")), "sales.csv")},
            content_type="multipart/form-data",
        )
        token = re.search(
            rb'name="preview_token" value="([a-f0-9]+)"', preview.data
        ).group(1).decode("ascii")
        response = client.post(
            "/imports/confirm",
            data={"preview_token": token},
            follow_redirects=True,
        )

    assert response.status_code == 200
    assert b"already been imported" in response.data
    assert b"Import complete: 0 orders" not in response.data
    import_rows.assert_called_once()


def test_database_failure_does_not_expose_details_or_claim_import_success():
    with app.test_client() as client, patch(
        "app.database.import_sales_rows",
        side_effect=mysql.connector.Error("private SQL/password details"),
    ):
        preview = client.post(
            "/imports/preview",
            data={"file": (BytesIO((CSV_HEADER + VALID_ROWS).encode("utf-8")), "sales.csv")},
            content_type="multipart/form-data",
        )
        token = re.search(
            rb'name="preview_token" value="([a-f0-9]+)"', preview.data
        ).group(1).decode("ascii")
        response = client.post("/imports/confirm", data={"preview_token": token})

    assert response.status_code == 503
    assert b"No sales rows were imported" in response.data
    assert b"private SQL/password details" not in response.data
