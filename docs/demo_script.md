# Project Demonstration Script (about 10 minutes)

Use a dedicated demonstration database with synthetic data. CSV confirmation
persists rows, so do not import the sample into a database whose existing
records must remain unchanged. Do not display `.env` or type credentials while
recording. The timings total approximately ten minutes and fit the requested
8–12 minute window.

## 0:00–0:45 — Welcome and introduction

“This is an E-Commerce Business Intelligence Dashboard built with Python,
Flask, MySQL, Pandas, NumPy, Matplotlib, and Bootstrap. It helps a manager
import and review synthetic sales performance. Its focus is KPI consistency: completed
and delivered orders count as eligible, cancelled orders do not, and recorded
refunds are deducted once.”

Show the landing page and its Upload, Dashboard, and Sample CSV actions.

## 0:45–1:45 — Problem and objectives

Explain the reporting problem: order line values alone do not explain net
revenue, returns, month changes, or regional/category contribution. State that
the application summarizes these views rather than implementing shopping or
payment features.

## 1:45–3:00 — Architecture and import

Show the system design slide. Describe the request path:

1. The landing page links to the CSV import workflow and dashboard.
2. CSV data is validated and previewed before explicit confirmation.
3. `database.py` writes orders, products, item lines, and an idempotency
   fingerprint in one transaction.
4. `analysis.py` prepares summaries with Pandas and NumPy; `charts.py`
   generates Matplotlib PNGs returned by Flask.

Mention that credentials are local in `.env`, not in source code.

On a dedicated demo database, download the sample CSV, preview it, and confirm
once. Show the imported order/item/product summary. Optionally try the exact
same file again to show that the second confirmation does not add duplicate
records.

## 3:00–4:15 — Database design

Show the ER diagram or database slide. Explain:

- `orders` stores status, date, and region.
- `products` stores product name and category.
- `order_items` connects orders to products and stores quantity, price,
  discount, return quantity, and refund.

Point out that the foreign keys preserve the relationships and the pair
`(order_id, product_id)` is unique per item table.

## 4:15–5:15 — KPI logic

Show the KPI slide and state:

```text
gross = quantity * unit_price
net = gross - discount_amount - refund_amount
```

Only completed and delivered orders are included. Count distinct order IDs
once. Returned quantity is not separately deducted when the recorded refund is
already subtracted. AOV is eligible net revenue divided by eligible orders;
when the denominator is zero, it is shown as N/A.

## 5:15–7:15 — Dashboard walkthrough

Open `http://127.0.0.1:5000/dashboard`.

- Read the net revenue, eligible order, AOV, and product count cards.
- Point to monthly net revenue and the month-over-month table.
- Compare category and region charts.
- Show the Top 5 Best-Selling Products table and descriptive Business Insights.
- Note that the charts have labeled axes and currency ticks.
- Scroll through the tables to show the corresponding values.
- Mention that these figures are calculated from the current database records,
  not constants embedded in the template.

## 7:15–8:00 — Filters and export

Enter a range such as `2025-01-01` to `2025-03-31`, apply it, and explain that
the order-date bounds are inclusive and parameterized in SQL. Optionally try a
category and region together and download the filtered Export CSV. Optionally
try a future date range to show the empty-data state.

## 8:00–9:00 — API and errors

Show `/health` and `/api/analytics/summary` in a browser or API client. Explain
that malformed date inputs return HTTP 400; database failures are shown as a
safe error to the user and logged in the Flask terminal.

## 9:00–10:00 — Tests, limitations, conclusion

Run `python -m pytest -q --import-mode=importlib` and report the result from the
current run. Explain that many route tests and import transaction tests use
mocks; the health check and dashboard request are separate live database
checks. State limitations: synthetic small data,
no taxes/shipping, no authentication, no predictive features, and local
development server only. Finish by summarizing that the application provides
an understandable and documented sales-reporting workflow.
