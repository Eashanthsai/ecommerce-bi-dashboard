# Final Project Report

## Abstract

The E-Commerce Business Intelligence Dashboard is a Flask application for
reviewing synthetic e-commerce sales. It includes a welcome page, reviewed
transactional CSV imports, product entry, a date/category/region-filtered
dashboard, CSV exports, descriptive insights, APIs, and Matplotlib charts.
Pandas and NumPy calculate the documented measures; cancelled orders are
excluded from eligible sales reporting.

## Introduction

Managers need a consistent view of revenue and order performance. Individual
order lines contain quantities, prices, discounts, and refunds; without common
rules, summaries can exclude or deduct amounts inconsistently. This project
demonstrates a small end-to-end data application that stores transactions,
calculates KPIs, and presents results in a dashboard.

All seeded data is synthetic. The example dataset spans January through
December 2025 and contains products, orders, and item lines; it includes
completed, delivered, and cancelled orders, discounts, and partial returns.

## Requirements

### Functional

- Persist orders, products, and order-item details in MySQL; support safe CSV
  imports with preview, confirmation, rollback, and duplicate-file prevention.
- Calculate eligible gross sales, discounts, refunds, net revenue, eligible
  order count, and average order value.
- Summarize monthly revenue and month-over-month growth.
- Compare sales by product category and region.
- Provide a welcome page, product entry, responsive dashboard, three
  Matplotlib charts, read-only APIs, and filtered CSV exports.
- Filter dashboard, charts, APIs, and exports by inclusive date range,
  category, and region.
- Rank the Top 5 products and calculate Month-over-Month growth and descriptive
  insights from filtered live records.
- Return safe errors for invalid date inputs and database/chart failures.

### Non-functional and project constraints

- Keep the schema names and fields consistent.
- Keep credentials outside Python source.
- Use synthetic data, server-side templates, and maintainable beginner-level
  components.
- Do not include authentication, payment, cart, or machine-learning systems.

## Methodology

1. Designed `orders`, `products`, and `order_items` with keys, constraints,
   and foreign-key relationships.
2. Seeded synthetic 2025 order transactions.
3. Implemented a reusable database connection helper and joined read query.
4. Validated records and calculated sales summaries with Pandas and NumPy.
5. Rendered those summaries in Flask templates and generated images using
   Matplotlib's Agg backend.
6. Added pytest coverage for analytics, APIs, filters, queries, and chart
   output.

## Implementation

`/` is the welcome page and `/dashboard` reads order data and product count,
passes the shared analytics result to Jinja, and displays KPIs, the Top 5
products, business insights, and summary tables. `/imports` previews an upload
before requiring explicit confirmation. `sales_import_batches` stores a
normalized content fingerprint alongside transaction counts, while the
orders/products/order-items writes occur in one database transaction. Chart
images are generated on demand by `/charts/<chart_name>.png` and streamed from
memory; they are not hardcoded or saved as precomputed data.

The API exposes `/health`, product/order/order-item lists, a consolidated
analytics response, and dedicated summary, monthly, category, and regional
routes. `start_date` and `end_date` are validated as `YYYY-MM-DD` and used in
parameterized inclusive SQL conditions.

## Results and verification

The current suite result is recorded in [`testing.md`](testing.md). Tests cover
analytics and insights, import validation and duplicate handling, transaction
rollback, product entry, filter combinations, CSV exports, date validation,
PNG output, and safe route behavior. Most route and import-persistence tests
use mocks; the configured local MySQL server was independently checked with
`/health`, and the live dashboard rendered the Top 5 section and product rows.
No CSV was imported during that live check.

The current local MySQL database was queried during documentation preparation:
it contained 8 products, 24 orders, and 48 order-item lines. The live analytics
query returned $3,035.00 gross sales, $163.00 discounts, $211.00 refunds,
$2,661.00 net sales, 22 eligible orders, and $120.95 AOV at that time. These
are a verified snapshot of the local synthetic database, not hardcoded
application outputs; values may change if its records change.

## Limitations

- The demonstration dataset is small and synthetic; it does not represent
  market performance.
- Tax and shipping are absent from the schema and excluded.
- Refund amounts are stored totals; the application does not model refund
  events, policies, or reasons.
- A date filter changes the data loaded for that report. Consequently, the
  first month shown in a filtered report has no earlier month in that same
  result for growth comparison.
- Tests using mocks do not replace testing against a user's own MySQL setup.
- The application is a local educational Flask development app, not a
  production deployment. It has no login, roles, CSRF protection, caching, or
  monitoring. Use a dedicated demo database for persistent CSV import
  demonstrations.
- Bootstrap CSS is loaded from a CDN; external network access is needed for
  Bootstrap styles.

## Conclusion

The project demonstrates an end-to-end Flask/MySQL reporting workflow with
transparent KPI formulas and a responsive visualization layer. Reusing the
same analysis function for the dashboard and APIs helps maintain consistent
business rules, while parameterized date conditions and explicit empty/error
handling improve reliability.

## Future enhancements

- Add API-level query and result pagination for larger datasets.
- Add automated browser tests and a repeatable local MySQL integration-test
  setup.
- Add caching or background report generation if data volume grows.
- Add configurable currency and timezone handling if the schema is extended.
- Consider authentication and production hosting only if the project scope
  later requires them.
