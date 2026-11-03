# Testing and Verification

## Reproduce the automated tests

From the Windows project root with the project virtual environment active:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pytest -q
```

Alternatively, invoke pytest directly:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

## Recorded result

On **2026-10-19**, the full suite was run with the project virtual environment:

```text
34 passed in 1.87s
```

This result is from an actual pytest run, not a proposed or fabricated result.
Run the command again after changes to reproduce the result for the current
working tree.

## Coverage in the test files

- [`tests/test_analysis.py`](../tests/test_analysis.py): gross/net formulas,
  distinct eligible order count, cancelled-order exclusion, single refund
  deduction, monthly revenue and growth, missing months, empty data, and
  invalid columns.
- [`tests/test_app.py`](../tests/test_app.py): dashboard HTML with mocked data,
  invalid date input, data and analytics routes, API date arguments, safe
  database failures, chart route image response, and chart failure response.
- [`tests/test_charts.py`](../tests/test_charts.py): valid PNG signatures for
  all chart types, empty chart data, and unknown chart rejection.
- [`tests/test_database.py`](../tests/test_database.py): parameterized
  inclusive date conditions and product-count query.

Most automated route tests use mocks. They verify application behavior without
requiring a live MySQL server, but do not by themselves certify database
credentials, database contents, or live-server availability.

## Manual verification with MySQL

After configuring `.env`, loading the SQL seed script, and running `python
app.py`, visit or request:

```text
http://127.0.0.1:5000/health
http://127.0.0.1:5000/
http://127.0.0.1:5000/?start_date=2025-01-01&end_date=2025-06-30
http://127.0.0.1:5000/api/analytics/summary
http://127.0.0.1:5000/charts/monthly-revenue.png
http://127.0.0.1:5000/charts/category-sales.png
http://127.0.0.1:5000/charts/region-sales.png
```

`/health` should report a connected database; dashboard and chart requests
should return HTTP 200 when database access succeeds. Date input errors return
HTTP 400. Database and chart failures should show the application's
user-readable error response; inspect the Flask terminal for server-side error
details. Manual checks depend on the local MySQL setup and are not implied by
the mocked tests.
