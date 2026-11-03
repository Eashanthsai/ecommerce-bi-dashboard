# E-Commerce Business Intelligence Dashboard

A Flask application for importing and reviewing e-commerce sales data stored
in MySQL. It includes a welcome page, reviewed CSV import workflow, product
entry, a filtered sales dashboard, and Matplotlib charts for monthly revenue,
product category, and region.

## Project status and scope

**Implemented:** MySQL-backed analytics and CSV exports, transactional CSV
imports with preview and duplicate-file protection, product entry, Pandas/NumPy
reporting, parameterized date/category/region filters, responsive Bootstrap
templates, and charts generated as PNG responses by Matplotlib.

**Not implemented:** authentication, editing/deleting existing records,
payment processing, shopping carts, machine learning, chart downloads, and
customer-level reporting. There is no customer table or real customer
information in the synthetic seed.

## Technology stack

- Python and Flask
- MySQL and `mysql-connector-python`
- Pandas and NumPy
- Matplotlib
- HTML, CSS, and Bootstrap 5
- pytest

## Prerequisites

- Windows 10/11
- Python 3.10 or newer; the project has been exercised using Python 3.13
- MySQL Server 8.0.16 or newer (required for enforced `CHECK` constraints)
- MySQL Workbench
- Visual Studio Code
- Internet access to load Bootstrap 5 CSS from its CDN

## Setup in Windows / VS Code

Open the project folder in VS Code, then open **Terminal → New Terminal** and
run these PowerShell commands from the project root:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Generate a unique local Flask session key:

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

Set the generated value as `FLASK_SECRET_KEY` in `.env`. The example file
contains only a placeholder; the application intentionally refuses to start
without a configured key.

If PowerShell blocks virtual-environment activation, allow it for the current
terminal only and retry:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
.\.venv\Scripts\Activate.ps1
```

Select the `.venv` interpreter in VS Code with **Python: Select Interpreter**.
Do not commit or share `.env`; it is ignored by `.gitignore`.

## MySQL setup

1. Start the local MySQL Server and open MySQL Workbench.
2. Connect to the server and create the schema if needed:
   `CREATE DATABASE IF NOT EXISTS ecommerce_bi_dashboard CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;`
3. Choose **File → Open SQL Script** and open
   [`database/setup_and_seed.sql`](database/setup_and_seed.sql).
4. Select `ecommerce_bi_dashboard` as the active schema, then execute the
   script with the lightning-bolt button.
5. Confirm the `ecommerce_bi_dashboard` schema contains `orders`, `products`,
   `order_items`, and `sales_import_batches`.

The seed script creates synthetic 2025 data: 8 products, 24 orders, and 48
order-item rows. It includes completed, delivered, and cancelled orders,
discounts, and recorded refunds. Run its seed inserts only once for a fresh
database; the setup statements use fixed sample IDs, so running the full script
again against already seeded tables causes duplicate-key errors.

## Environment configuration

Open `.env` in VS Code and set the database connection values for your local
MySQL account:

```dotenv
FLASK_SECRET_KEY=<generated random value>
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=your_mysql_username
DB_PASSWORD=your_local_password
DB_NAME=ecommerce_bi_dashboard
```

These are variable names and example values only. Use your own locally
configured MySQL username and password. Never put credentials in Python source
or documentation. `config.py` loads the project `.env` relative to its own
file as a local convenience; already-set environment variables always take
precedence. Production deployments must provide `FLASK_SECRET_KEY` and the
database variables through the hosting platform.

## Run the application

From the project root with `.venv` active:

```powershell
python app.py
```

The Flask development server listens at **http://127.0.0.1:5000/**. The root
URL is the welcome page; open `/dashboard` for the sales dashboard. Stop the
server with **Ctrl+C** in the terminal.

To run automated tests:

```powershell
python -m pytest -q
```

## Railway deployment

The repository includes `railway.json` with the production command
`gunicorn --bind 0.0.0.0:$PORT app:app` and `/health` as its database-aware
health check. Keep Railway MySQL private. Add an application service from this
GitHub repository, add a MySQL service, and configure these application-service
variables using Railway references (replace `MySQL` with the actual database
service name):

```text
DB_HOST=${{MySQL.MYSQLHOST}}
DB_PORT=${{MySQL.MYSQLPORT}}
DB_USER=${{MySQL.MYSQLUSER}}
DB_PASSWORD=${{MySQL.MYSQLPASSWORD}}
DB_NAME=${{MySQL.MYSQLDATABASE}}
FLASK_SECRET_KEY=<generate a unique random value>
```

Generate the production key locally with
`python -c "import secrets; print(secrets.token_hex(32))"` and paste it into
Railway's secret variable editor only. Never copy it into this repository or
`.env.example`. The application reads Railway's injected environment variables
directly; a local `.env` file is not required in production.

Railway creates the selected database from `MYSQLDATABASE`. Run
[`database/setup_and_seed.sql`](database/setup_and_seed.sql) against that
database once; the script creates the existing tables and inserts the
documented synthetic seed records without switching to a hardcoded schema
name. The seed inserts use fixed IDs and must only be run once against an
empty schema. The `/health` endpoint succeeds only when MySQL is reachable.
Review Railway's plan and usage limits before provisioning services; do not
upgrade or enable paid usage without approval.

## Routes

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Welcome page with links to the dashboard, import, and sample CSV. |
| GET | `/dashboard` | Dashboard; accepts optional date, category, and region filters. |
| GET | `/imports` | CSV upload instructions and preview form. |
| POST | `/imports/preview` | Validates and previews a CSV without database writes. |
| POST | `/imports/confirm` | Explicitly imports a validated preview in a transaction. |
| GET | `/imports/sample.csv` | Downloads the documented sample import template. |
| GET | `/products/new` | Product entry form. |
| GET | `/exports/sales.csv` | Downloads eligible order-item sales for the selected dashboard filters. |
| GET | `/health` | Checks MySQL connectivity. |
| GET | `/api/products` | Product records; accepts `limit` and `offset`. |
| GET | `/api/orders` | Order records; accepts `limit` and `offset`. |
| GET | `/api/order-items` | Order-item records; accepts `limit` and `offset`. |
| GET | `/api/analytics` | Consolidated summary and grouped sales data. |
| GET | `/api/analytics/summary` | Revenue, eligible order count, and AOV. |
| GET | `/api/analytics/monthly-revenue` | Monthly revenue and month-over-month growth. |
| GET | `/api/analytics/category-sales` | Sales grouped by product category. |
| GET | `/api/analytics/region-sales` | Sales grouped by order region. |
| GET | `/charts/monthly-revenue.png` | In-memory generated monthly revenue chart. |
| GET | `/charts/category-sales.png` | In-memory generated category chart. |
| GET | `/charts/region-sales.png` | In-memory generated region chart. |

Dashboard filter example:

```text
http://127.0.0.1:5000/dashboard?start_date=2025-01-01&end_date=2025-06-30&category=Home&region=West
```

Dates use `YYYY-MM-DD`; both endpoints are inclusive. Category and region
options come from the database, and a blank selection means all values.
Dashboard analytics and chart requests accept the same filter query
parameters; invalid dates, category, region, or a start date later than the
end date return HTTP 400. Category and region chart subtitles explain when
their dimension is narrowed by an active filter. Record-list pagination
accepts `limit` from 1 through 500 and a nonnegative `offset`.

The dashboard's **Export CSV** button downloads the eligible order-item lines
for the date range, category, and region currently selected in the filter
form. The CSV includes order date and ID, product and category, region,
quantity, unit price, gross sales, discounts, refunds, and net sales.
Cancelled orders are excluded; net sales use the same discounts and recorded
refunds as dashboard analytics.

## Importing sales data

From the welcome page choose **Upload Sales Data**, or visit `/imports`.
Download the sample CSV to see the exact required headers and row format.
Imports accept UTF-8 CSV files up to 2 MB and 5,000 item rows. Validate the
file, review the preview and any errors, and then use the explicit confirmation
button. The import is all-or-nothing: invalid rows block the import, database
failures roll back the transaction, and the dashboard is refreshed after a
successful commit.

Each row describes one product line. Rows with the same `order_reference` are
combined into one new order; the reference is used to group rows in the upload
and is not stored in the existing order schema. Existing products are matched
by product name and category; new products are created from their first
positive line unit price. Existing order-item unit prices remain the imported
historical prices.

`sales_import_batches` stores a SHA-256 fingerprint of normalized validated
CSV rows and the committed import counts. It prevents re-importing the same
logical row set even if row order or CSV formatting changes. This table does
not modify or replace existing sales records. It is created by the SQL setup
script and also ensured on demand for an existing database when an import is
confirmed.

The import accepts the schema's three order statuses. As in existing analytics,
cancelled imports are stored but excluded from eligible sales KPIs and exports.
No customer or profit fields are imported because the current schema does not
support them.

## Troubleshooting

- **Database unavailable:** check that MySQL Server is running; confirm the
  database name, host, port, and local credentials in `.env`; then visit
  `/health`. Keep the password local.
- **Flask cannot start because its key is missing:** configure `FLASK_SECRET_KEY`
  in `.env` locally or in the hosting platform's environment variables.
- **Missing table:** execute `database/setup_and_seed.sql` in Workbench and
  confirm the selected schema is `ecommerce_bi_dashboard`.
- **Port 5000 already in use:** stop the existing project Flask process with
  Ctrl+C in its terminal before starting another instance. Do not terminate an
  unrelated process.
- **Dependency import error:** activate `.venv` and run
  `python -m pip install -r requirements.txt`.
- **Bootstrap styles absent:** the stylesheet is loaded from a CDN, so check
  internet access. The dashboard stylesheet itself is served locally from
  `/static/css/style.css`.
- **Chart error:** inspect the Flask terminal output for the logged chart
  error. Chart responses are generated from the current database report for
  each request; no chart data is hardcoded.

## Documentation

- [Project proposal](docs/project_proposal.md)
- [System design](docs/system_design.md)
- [KPI definitions](docs/kpi_definitions.md)
- [Testing evidence](docs/testing.md)
- [Final report](docs/final_report.md)
- [8–12 minute demonstration script](docs/demo_script.md)
- [Viva questions and answers](docs/viva_questions.md)
- [ER diagram](docs/er_diagram.md)
- [Data dictionary](database/data_dictionary.md)
- [Presentation slides](docs/ecommerce_bi_dashboard_presentation.pptx)
