# Project Proposal: E-Commerce Business Intelligence Dashboard

## Problem statement

Order data is useful to a manager only when it can be summarized consistently.
Gross order totals alone do not account for cancelled orders, discounts, or
recorded refunds, and they do not make month-to-month or category comparisons
easy to see. This project provides a simple browser-based view of synthetic
sales records using a documented set of KPI rules.

## Objectives

1. Store sample products, orders, and order-item amounts in a relational
   database.
2. Calculate sales measures consistently from the stored records.
3. Exclude cancelled orders from eligible sales measures.
4. Show monthly revenue and month-over-month change.
5. Compare sales by product category and sales region.
6. Provide date, category, and region filters, product rankings, CSV export,
   and descriptive business insights.
7. Accept reviewed CSV imports and preserve transaction integrity and duplicate
   import protection.
8. Keep database credentials out of source code and use parameterized SQL for
   filters and writes.

## Scope

### Included

- Synthetic order data covering January through December 2025.
- MySQL schema with `orders`, `products`, and `order_items`.
- Welcome page, dashboard, product entry, health check, read-only record APIs,
  and analytics APIs.
- CSV sample download, validated preview, explicit transactional import, and
  normalized-content duplicate detection.
- Pandas/NumPy calculations for summary KPIs and grouped tables.
- Matplotlib charts for month, category, and region summaries.
- Inclusive date, category, and region filtering; filtered sales CSV export.
- Top-five product ranking, MoM revenue growth, and descriptive insights.
- Automated pytest coverage for calculations, routes, date inputs, queries, and
  generated image content.

### Excluded

- Real customer or payment information.
- Authentication, roles, shopping cart, checkout, payment gateway, or order
  editing.
- Machine learning, forecasting, or recommendations.
- Tax and shipping calculations; these fields do not exist in the schema.
- Customer and profit metrics; the current data model has no customer or cost
  fields.
- Production deployment and production monitoring.

## Technology stack

| Technology | Project use |
|---|---|
| Python | Application and calculation logic |
| Flask | Web application, HTML rendering, and HTTP APIs |
| MySQL / InnoDB | Persistent relational data and foreign-key constraints |
| mysql-connector-python | Parameterized database connectivity |
| Pandas | Tabular validation, grouping, and monthly reporting |
| NumPy | Array calculations and safe month-over-month division |
| Matplotlib | Server-generated PNG charts |
| Jinja templates, HTML, CSS | Server-rendered dashboard |
| Bootstrap 5 | Responsive layout and common UI styling |
| pytest | Automated unit and route tests |

## Deliverables and status

The schema and seed script, data dictionary, Mermaid ER diagram, Flask app,
analytics layer, welcome/import/dashboard pages, charts, automated tests,
README, and final documentation are implemented in this project. The
PowerPoint presentation is included in the documentation folder. The project
does not claim to be a production-hardened service.
