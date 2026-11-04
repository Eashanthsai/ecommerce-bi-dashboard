"""Flask entry point and read-only API for the e-commerce dashboard."""

import os
import csv
import time
import secrets
import hmac
from uuid import uuid4
from io import StringIO
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from threading import Lock
from urllib.parse import urlsplit

import mysql.connector
from flask import Flask, Response, abort, flash, jsonify, redirect, render_template, request, send_file, session, url_for
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge
from werkzeug.security import check_password_hash

import analysis
import charts
import database
from config import DatabaseConfigurationError
from sales_import import validate_sales_csv


DEFAULT_LIMIT = 100
MAX_LIMIT = 500
MAX_UPLOAD_BYTES = 2 * 1024 * 1024
MAX_STAGED_IMPORTS = 50
STAGED_IMPORT_TTL_SECONDS = 30 * 60
MAX_LOGIN_ATTEMPTS = 5
LOGIN_ATTEMPT_WINDOW_SECONDS = 15 * 60


def create_app():
    app = Flask(__name__)
    secret_key = os.getenv("FLASK_SECRET_KEY")
    if not secret_key:
        raise RuntimeError("FLASK_SECRET_KEY must be configured in the environment.")
    dashboard_username = os.getenv("DASHBOARD_USERNAME")
    dashboard_password_hash = os.getenv("DASHBOARD_PASSWORD_HASH")
    if not dashboard_username or not dashboard_password_hash:
        raise RuntimeError(
            "DASHBOARD_USERNAME and DASHBOARD_PASSWORD_HASH must be configured."
        )
    app.secret_key = secret_key
    app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = os.getenv(
        "SESSION_COOKIE_SECURE",
        "true"
        if os.getenv("VERCEL_ENV") == "production"
        or os.getenv("FLASK_ENV") == "production"
        or os.getenv("ENVIRONMENT") == "production"
        else "false",
    ).lower() in {"1", "true", "yes"}
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=8)
    app.config["SESSION_REFRESH_EACH_REQUEST"] = False
    staged_imports = {}
    login_attempts = {}
    login_attempts_lock = Lock()

    def safe_redirect_target(target):
        if not target:
            return url_for("dashboard")
        parsed = urlsplit(target)
        if (
            parsed.scheme
            or parsed.netloc
            or not parsed.path.startswith("/")
            or parsed.path.startswith("//")
            or "\\" in target
        ):
            return url_for("dashboard")
        return target

    @app.context_processor
    def inject_csrf_token():
        return {"csrf_token": session.get("csrf_token", "")}

    @app.before_request
    def protect_application():
        if request.endpoint == "static" or request.endpoint in {"login", "health"}:
            return None

        if request.endpoint != "login_submit":
            if session.get("authenticated") is not True:
                if request.path.startswith("/api/"):
                    return jsonify({"error": "Authentication required."}), 401
                return redirect(url_for("login", next=request.full_path.rstrip("?")))

        if request.method == "POST":
            submitted_token = (
                request.form.get("csrf_token")
                or request.headers.get("X-CSRF-Token")
                or ""
            )
            expected_token = session.get("csrf_token", "")
            if not expected_token or not hmac.compare_digest(
                submitted_token, expected_token
            ):
                return error_response(
                    400, "The form expired. Reload the page and try again."
                )
        return None

    @app.after_request
    def set_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return response

    @app.get("/login")
    def login():
        if session.get("authenticated") is True:
            return redirect(url_for("dashboard"))
        session.setdefault("csrf_token", secrets.token_urlsafe(32))
        return render_template(
            "login.html",
            error_message=None,
            next_url=request.args.get("next", ""),
        )

    @app.post("/login")
    def login_submit():
        client_key = request.remote_addr or "unknown"
        now = time.monotonic()
        with login_attempts_lock:
            attempts = login_attempts.get(client_key)
            if (
                attempts is not None
                and now - attempts["started_at"] >= LOGIN_ATTEMPT_WINDOW_SECONDS
            ):
                del login_attempts[client_key]
                attempts = None
            if attempts is not None and attempts["count"] >= MAX_LOGIN_ATTEMPTS:
                session.setdefault("csrf_token", secrets.token_urlsafe(32))
                return (
                    render_template(
                        "login.html",
                        error_message="Too many sign-in attempts. Try again later.",
                        next_url=request.form.get("next", ""),
                    ),
                    429,
                )

        submitted_username = request.form.get("username", "")
        submitted_password = request.form.get("password", "")
        username_matches = hmac.compare_digest(
            submitted_username.encode("utf-8"),
            dashboard_username.encode("utf-8"),
        )
        password_matches = check_password_hash(
            dashboard_password_hash, submitted_password
        )
        if not (username_matches and password_matches):
            with login_attempts_lock:
                attempts = login_attempts.get(client_key)
                if attempts is None:
                    login_attempts[client_key] = {
                        "started_at": now,
                        "count": 1,
                    }
                else:
                    attempts["count"] += 1
            session.setdefault("csrf_token", secrets.token_urlsafe(32))
            return (
                render_template(
                    "login.html",
                    error_message="The username or password was incorrect.",
                    next_url=request.form.get("next", ""),
                ),
                401,
            )

        with login_attempts_lock:
            login_attempts.pop(client_key, None)
        session.clear()
        session["authenticated"] = True
        session["csrf_token"] = secrets.token_urlsafe(32)
        session.permanent = True
        return redirect(safe_redirect_target(request.form.get("next", "")))

    @app.post("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.errorhandler(RequestEntityTooLarge)
    def upload_too_large(_error):
        return (
            render_template(
                "error.html",
                error_message="CSV files must be 2 MB or smaller.",
                status_code=413,
            ),
            413,
        )

    def parse_date_range():
        parsed = {}
        for key in ("start_date", "end_date"):
            value = request.args.get(key, "").strip()
            if not value:
                parsed[key] = None
                continue
            try:
                parsed[key] = datetime.strptime(value, "%Y-%m-%d").date()
            except ValueError:
                return None, f"{key} must be a valid date in YYYY-MM-DD format."
        if (
            parsed["start_date"] is not None
            and parsed["end_date"] is not None
            and parsed["start_date"] > parsed["end_date"]
        ):
            return None, "start_date must be on or before end_date."
        return parsed, None

    def parse_dimension_filters(options):
        selected = {}
        for query_name, option_name in (
            ("category", "categories"),
            ("region", "regions"),
        ):
            value = request.args.get(query_name, "").strip()
            if value and value not in options[option_name]:
                return None, f"Invalid {query_name} filter."
            selected[query_name] = value or None
        return selected, None

    def error_response(status_code, message):
        if request.path == "/health" or request.path.startswith("/api/"):
            return jsonify({"error": message}), status_code
        return (
            render_template(
                "error.html",
                error_message=message,
                status_code=status_code,
            ),
            status_code,
        )

    def get_pagination():
        try:
            limit = int(request.args.get("limit", DEFAULT_LIMIT))
            offset = int(request.args.get("offset", 0))
        except ValueError:
            return None, (jsonify({"error": "limit and offset must be integers."}), 400)

        if not 1 <= limit <= MAX_LIMIT:
            return None, (
                jsonify({"error": f"limit must be between 1 and {MAX_LIMIT}."}),
                400,
            )
        if offset < 0:
            return None, (jsonify({"error": "offset cannot be negative."}), 400)

        return (limit, offset), None

    @app.get("/")
    def home():
        return render_template("landing.html")

    def dashboard_context():
        date_range, error = parse_date_range()
        if error:
            return (
                None,
                (
                    render_template(
                        "error.html",
                        error_message=error,
                        status_code=400,
                    ),
                    400,
                ),
            )
        filter_options = database.fetch_filter_options()
        dimension_filters, error = parse_dimension_filters(filter_options)
        if error:
            return (
                None,
                (
                    render_template(
                        "error.html",
                        error_message=error,
                        status_code=400,
                    ),
                    400,
                ),
            )
        query_filters = {
            **date_range,
            **{
                key: value
                for key, value in dimension_filters.items()
                if value is not None
            },
        }
        report = analysis.analyze_sales(
            database.fetch_sales_data(**query_filters),
            **date_range,
        )
        product_count = (
            database.fetch_product_count(category=dimension_filters["category"])
            if dimension_filters["category"] is not None
            else database.fetch_product_count()
        )
        return {
            "analytics": report,
            "product_count": product_count,
            "start_date": request.args.get("start_date", ""),
            "end_date": request.args.get("end_date", ""),
            "filters": date_range,
            "filter_options": filter_options,
            "selected_category": dimension_filters["category"] or "",
            "selected_region": dimension_filters["region"] or "",
        }, None

    @app.get("/dashboard")
    def dashboard():
        context, error = dashboard_context()
        if error:
            return error
        return render_template("dashboard.html", **context, active_nav="dashboard")

    @app.get("/analytics")
    def analytics_page():
        context, error = dashboard_context()
        if error:
            return error
        return render_template("dashboard.html", **context, active_nav="analytics")

    @app.get("/orders")
    def orders_page():
        date_range, error = parse_date_range()
        if error:
            return render_template(
                "error.html", error_message=error, status_code=400
            ), 400

        filter_options = database.fetch_filter_options()
        region = request.args.get("region", "").strip()
        if region and region not in filter_options["regions"]:
            return render_template(
                "error.html",
                error_message="Invalid region filter.",
                status_code=400,
            ), 400

        status = request.args.get("status", "").strip()
        statuses = database.fetch_order_statuses()
        if status and status not in statuses:
            return render_template(
                "error.html",
                error_message="Invalid order status filter.",
                status_code=400,
            ), 400

        pagination, error = get_pagination()
        if error:
            return error
        limit, offset = pagination
        orders, order_count = database.fetch_orders(
            start_date=date_range["start_date"],
            end_date=date_range["end_date"],
            status=status or None,
            region=region or None,
            limit=limit,
            offset=offset,
        )
        return render_template(
            "orders.html",
            active_nav="orders",
            orders=orders,
            order_count=order_count,
            statuses=statuses,
            regions=filter_options["regions"],
            start_date=request.args.get("start_date", ""),
            end_date=request.args.get("end_date", ""),
            selected_status=status,
            selected_region=region,
            limit=limit,
            offset=offset,
        )

    @app.get("/products")
    def products_page():
        pagination, error = get_pagination()
        if error:
            return error
        limit, offset = pagination
        products = database.fetch_all(
            """
            SELECT product_id, product_name, category, unit_price
            FROM products
            ORDER BY product_name, product_id
            LIMIT %s OFFSET %s
            """,
            (limit, offset),
        )
        return render_template(
            "products.html",
            active_nav="products",
            products=products,
            product_count=database.fetch_product_count(),
            limit=limit,
            offset=offset,
        )

    @app.get("/reports")
    def reports_page():
        context, error = dashboard_context()
        if error:
            return error
        return render_template("reports.html", **context, active_nav="reports")

    @app.get("/imports")
    def import_sales_page():
        return render_template(
            "sales_import.html",
            errors=[],
            preview_rows=[],
            preview_token=None,
            preview_count=0,
        )

    @app.post("/imports/preview")
    def preview_sales_import():
        upload = request.files.get("file")
        if upload is None or not upload.filename:
            return render_template(
                "sales_import.html",
                errors=[{"line": 1, "message": "Choose a CSV file to upload."}],
                preview_rows=[],
                preview_token=None,
                preview_count=0,
            ), 400
        if not upload.filename.lower().endswith(".csv"):
            return render_template(
                "sales_import.html",
                errors=[{"line": 1, "message": "Only .csv files are supported."}],
                preview_rows=[],
                preview_token=None,
                preview_count=0,
            ), 400

        content = upload.read(MAX_UPLOAD_BYTES + 1)
        if len(content) > MAX_UPLOAD_BYTES:
            return (
                render_template(
                    "sales_import.html",
                    errors=[{"line": 1, "message": "CSV files must be 2 MB or smaller."}],
                    preview_rows=[],
                    preview_token=None,
                    preview_count=0,
                ),
                413,
            )

        rows, errors, digest = validate_sales_csv(content)
        preview_token = None
        if not errors and rows:
            now = time.monotonic()
            for token, staged in list(staged_imports.items()):
                if now - staged["created_at"] > STAGED_IMPORT_TTL_SECONDS:
                    del staged_imports[token]
            if len(staged_imports) >= MAX_STAGED_IMPORTS:
                return (
                    render_template(
                        "sales_import.html",
                        errors=[
                            {
                                "line": 1,
                                "message": "Too many import previews are active. Wait for an existing preview to expire or confirm it, then retry.",
                            }
                        ],
                        preview_rows=[],
                        preview_token=None,
                        preview_count=0,
                    ),
                    429,
                )
            preview_token = uuid4().hex
            staged_imports[preview_token] = {
                "rows": rows,
                "digest": digest,
                "created_at": now,
            }
        elif not errors:
            errors.append({"line": 1, "message": "The CSV contains no sales rows."})

        return render_template(
            "sales_import.html",
            errors=errors,
            preview_rows=rows[:25],
            preview_token=preview_token,
            preview_count=len(rows),
        ), (400 if errors else 200)

    @app.post("/imports/confirm")
    def confirm_sales_import():
        token = request.form.get("preview_token", "")
        staged = staged_imports.get(token)
        if not token or staged is None:
            return (
                render_template(
                    "sales_import.html",
                    errors=[
                        {
                            "line": 1,
                            "message": "This preview expired. Upload the CSV again to review it.",
                        }
                    ],
                    preview_rows=[],
                    preview_token=None,
                    preview_count=0,
                ),
                400,
            )
        try:
            result = database.import_sales_rows(staged["rows"], staged["digest"])
        except ValueError as exc:
            return (
                render_template(
                    "sales_import.html",
                    errors=[{"line": 1, "message": str(exc)}],
                    preview_rows=staged["rows"][:25],
                    preview_token=token,
                    preview_count=len(staged["rows"]),
                ),
                400,
            )
        except mysql.connector.Error:
            app.logger.exception("Sales CSV import failed")
            return (
                render_template(
                    "sales_import.html",
                    errors=[
                        {
                            "line": 1,
                            "message": "The database could not complete the import. No sales rows were imported.",
                        }
                    ],
                    preview_rows=staged["rows"][:25],
                    preview_token=token,
                    preview_count=len(staged["rows"]),
                ),
                503,
            )

        del staged_imports[token]
        if result["already_imported"]:
            flash("This exact CSV file has already been imported; no records were added.")
        else:
            flash(
                "Import complete: "
                f'{result["orders_imported"]} orders, '
                f'{result["items_imported"]} order items, '
                f'{result["products_created"]} products created, and '
                f'{result["products_matched"]} products matched. '
                "Rejected rows: 0."
            )
        return redirect(url_for("dashboard"))

    @app.get("/imports/sample.csv")
    def download_sample_csv():
        output = StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(
            (
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
        )
        writer.writerow(
            (
                "SAMPLE-ORDER-001",
                "2025-01-15",
                "completed",
                "West",
                "Sample Mug",
                "Home",
                "2",
                "12.50",
                "0.00",
                "0",
                "0.00",
            )
        )
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={
                "Content-Disposition": 'attachment; filename="sales-import-template.csv"',
                "Cache-Control": "no-store",
            },
        )

    @app.get("/exports/sales.csv")
    def export_sales_csv():
        date_range, error = parse_date_range()
        if error:
            return error_response(400, error)

        filter_options = database.fetch_filter_options()
        dimension_filters, error = parse_dimension_filters(filter_options)
        if error:
            return error_response(400, error)

        query_filters = {
            **date_range,
            **{
                key: value
                for key, value in dimension_filters.items()
                if value is not None
            },
        }
        records = database.fetch_sales_data(**query_filters)
        output = StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(analysis.SALES_EXPORT_COLUMNS)
        for row in analysis.sales_export_rows(records):
            writer.writerow(row[column] for column in analysis.SALES_EXPORT_COLUMNS)

        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={
                "Content-Disposition": 'attachment; filename="sales-report.csv"',
                "Cache-Control": "no-store",
            },
        )

    def validate_product_form(form_data=None):
        if form_data is None:
            form_data = request.form

        cleaned = {
            "product_name": (form_data.get("product_name") or "").strip(),
            "category": (form_data.get("category") or "").strip(),
            "unit_price": (form_data.get("unit_price") or "").strip(),
        }
        errors = {}

        if not cleaned["product_name"]:
            errors["product_name"] = "Product name is required."
        elif len(cleaned["product_name"]) > 120:
            errors["product_name"] = "Product name is too long. Maximum length is 120 characters."

        if not cleaned["category"]:
            errors["category"] = "Category is required."
        elif len(cleaned["category"]) > 80:
            errors["category"] = "Category is too long. Maximum length is 80 characters."

        if not cleaned["unit_price"]:
            errors["unit_price"] = "Unit price is required."
        else:
            try:
                price = Decimal(cleaned["unit_price"])
            except (InvalidOperation, ValueError):
                errors["unit_price"] = "Unit price must be a valid positive number."
            else:
                if price <= 0:
                    errors["unit_price"] = "Unit price must be a positive number."
                elif price > Decimal("9999999.99"):
                    errors["unit_price"] = "Unit price is too large. Maximum value is 9,999,999.99."
                else:
                    cleaned["unit_price"] = price

        if errors:
            return cleaned, errors
        return cleaned, None

    @app.get("/products/new")
    def add_product_form():
        return render_template(
            "add_product.html",
            form_data={},
            errors={},
            error_message=None,
        )

    @app.post("/products/new")
    def add_product_submit():
        form_data = {
            "product_name": (request.form.get("product_name") or "").strip(),
            "category": (request.form.get("category") or "").strip(),
            "unit_price": (request.form.get("unit_price") or "").strip(),
        }
        cleaned, errors = validate_product_form(form_data)
        if errors:
            return (
                render_template(
                    "add_product.html",
                    form_data=form_data,
                    errors=errors,
                    error_message=None,
                ),
                400,
            )

        try:
            database.add_product(
                product_name=cleaned["product_name"],
                category=cleaned["category"],
                unit_price=cleaned["unit_price"],
            )
        except ValueError as exc:
            return (
                render_template(
                    "add_product.html",
                    form_data=form_data,
                    errors={},
                    error_message=str(exc),
                ),
                400,
            )
        except mysql.connector.Error:
            app.logger.exception("Product insert failed")
            return (
                render_template(
                    "add_product.html",
                    form_data=form_data,
                    errors={},
                    error_message="The database is unavailable. Please try again later.",
                ),
                503,
            )

        flash("Product added successfully.")
        return redirect(url_for("dashboard"))

    @app.get("/health")
    def health():
        if not database.ping_database():
            return jsonify({"status": "unavailable", "database": "unavailable"}), 503
        return jsonify({"status": "ok", "database": "connected"}), 200

    @app.get("/api/products")
    def list_products():
        pagination, error = get_pagination()
        if error:
            return error
        limit, offset = pagination
        rows = database.fetch_all(
            """
            SELECT product_id, product_name, category
            FROM products
            ORDER BY product_id
            LIMIT %s OFFSET %s
            """,
            (limit, offset),
        )
        return jsonify(
            {
                "data": rows,
                "pagination": {"limit": limit, "offset": offset},
            }
        )

    @app.get("/api/orders")
    def list_orders():
        pagination, error = get_pagination()
        if error:
            return error
        limit, offset = pagination
        rows = database.fetch_all(
            """
            SELECT order_id, order_status, order_date, region
            FROM orders
            ORDER BY order_id
            LIMIT %s OFFSET %s
            """,
            (limit, offset),
        )
        for row in rows:
            if isinstance(row["order_date"], date):
                row["order_date"] = row["order_date"].isoformat()
        return jsonify(
            {
                "data": rows,
                "pagination": {"limit": limit, "offset": offset},
            }
        )

    @app.get("/api/order-items")
    def list_order_items():
        pagination, error = get_pagination()
        if error:
            return error
        limit, offset = pagination
        rows = database.fetch_all(
            """
            SELECT order_item_id, order_id, product_id, quantity, unit_price,
                   discount_amount, returned_quantity, refund_amount
            FROM order_items
            ORDER BY order_item_id
            LIMIT %s OFFSET %s
            """,
            (limit, offset),
        )
        return jsonify(
            {
                "data": rows,
                "pagination": {"limit": limit, "offset": offset},
            }
        )

    def get_analytics(date_range=None, category=None, region=None):
        query_filters = dict(date_range or {})
        if category is not None:
            query_filters["category"] = category
        if region is not None:
            query_filters["region"] = region
        if all(value is None for value in query_filters.values()):
            records = database.fetch_sales_data()
        else:
            records = database.fetch_sales_data(**query_filters)
        return analysis.analyze_sales(records, **(date_range or {}))

    def api_analytics_filters():
        date_range, error = parse_date_range()
        if error:
            return None, (jsonify({"error": error}), 400)
        options = database.fetch_filter_options()
        dimension_filters, error = parse_dimension_filters(options)
        if error:
            return None, (jsonify({"error": error}), 400)
        return (date_range, dimension_filters), None

    @app.get("/api/analytics")
    def analytics_overview():
        filters, error = api_analytics_filters()
        if error:
            return error
        date_range, dimensions = filters
        return jsonify(get_analytics(date_range, **dimensions))

    @app.get("/api/analytics/summary")
    def analytics_summary():
        filters, error = api_analytics_filters()
        if error:
            return error
        date_range, dimensions = filters
        return jsonify(get_analytics(date_range, **dimensions)["summary"])

    @app.get("/api/analytics/monthly-revenue")
    def analytics_monthly_revenue():
        filters, error = api_analytics_filters()
        if error:
            return error
        date_range, dimensions = filters
        return jsonify(
            {"data": get_analytics(date_range, **dimensions)["monthly_revenue"]}
        )

    @app.get("/api/analytics/category-sales")
    def analytics_category_sales():
        filters, error = api_analytics_filters()
        if error:
            return error
        date_range, dimensions = filters
        return jsonify(
            {"data": get_analytics(date_range, **dimensions)["category_sales"]}
        )

    @app.get("/api/analytics/region-sales")
    def analytics_region_sales():
        filters, error = api_analytics_filters()
        if error:
            return error
        date_range, dimensions = filters
        return jsonify(
            {"data": get_analytics(date_range, **dimensions)["region_sales"]}
        )

    @app.get("/api/analytics/top-products")
    def analytics_top_products():
        filters, error = api_analytics_filters()
        if error:
            return error
        date_range, dimensions = filters
        return jsonify(
            {"data": get_analytics(date_range, **dimensions)["top_products"]}
        )

    @app.get("/charts/<chart_name>.png")
    def chart_image(chart_name):
        if chart_name not in charts.CHART_NAMES:
            abort(404)
        date_range, error = parse_date_range()
        if error:
            return error_response(400, error)
        filter_options = database.fetch_filter_options()
        dimension_filters, error = parse_dimension_filters(filter_options)
        if error:
            return error_response(400, error)
        report = get_analytics(date_range, **dimension_filters)
        try:
            image = charts.generate_chart(chart_name, report)
        except (KeyError, TypeError, ValueError):
            app.logger.exception("Invalid data while generating %s chart", chart_name)
            return (
                render_template(
                    "error.html",
                    error_message="This chart could not be generated from the current sales data.",
                    status_code=500,
                ),
                500,
            )
        except Exception:
            app.logger.exception("Chart generation failed for %s", chart_name)
            return (
                render_template(
                    "error.html",
                    error_message="A chart could not be generated. Please refresh the dashboard and try again.",
                    status_code=500,
                ),
                500,
            )
        return send_file(
            image,
            mimetype="image/png",
            download_name=f"{chart_name}.png",
            max_age=0,
        )

    @app.errorhandler(DatabaseConfigurationError)
    def handle_database_configuration_error(error):
        app.logger.error("Database configuration error: %s", error)
        return error_response(503, "Database configuration is incomplete or invalid.")

    @app.errorhandler(mysql.connector.Error)
    def handle_mysql_error(error):
        app.logger.exception("MySQL request failed")
        return error_response(503, "The database is unavailable. Please try again later.")

    @app.errorhandler(404)
    def handle_not_found(_error):
        return error_response(404, "The requested page was not found.")

    @app.errorhandler(HTTPException)
    def handle_http_exception(error):
        return error_response(error.code or 500, error.description)

    @app.errorhandler(Exception)
    def handle_unexpected_error(error):
        app.logger.exception("Unexpected application error")
        return error_response(500, "An unexpected server error occurred.")

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=False)
