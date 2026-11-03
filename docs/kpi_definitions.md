# KPI Definitions and Assumptions

All money values are stored as `DECIMAL(10, 2)` in USD. These definitions match
[`analysis.py`](../analysis.py) and the schema dictionary.

## Order eligibility

`completed` and `delivered` are eligible statuses. `cancelled` is excluded
from eligible gross sales, discounts, refunds, net sales, order count, AOV,
monthly revenue, and category/region sales.

## Formulas

For each order-item line:

```text
line gross sales = quantity * unit_price
line discounts   = discount_amount
line refunds     = refund_amount
line net sales   = line gross sales - line discounts - line refunds
```

Across eligible order-item lines:

```text
gross sales = sum(line gross sales)
discounts   = sum(line discounts)
refunds     = sum(line refunds)
net sales   = sum(line net sales)
```

The dashboard's **Net revenue** card is eligible net sales. “Gross sales” in
the detail table is before line discounts and refunds.

```text
eligible order count = count of distinct order_id values with eligible status
average order value  = eligible net sales / eligible order count
```

The order count counts each eligible order once, even when it has multiple
product lines. AOV is `N/A` (`null` in JSON) when no eligible order exists.

## Monthly revenue and growth

Monthly revenue is the sum of eligible line net sales grouped by the calendar
month of `orders.order_date`. Months with no sales between the first and last
eligible month are output as zero.

```text
month-over-month growth (%) =
    ((current month revenue - previous month revenue)
      / previous month revenue) * 100
```

Growth is `N/A` for the first month and when the previous month's revenue is
zero. With a date filter, the first month in the filtered result has no prior
comparison within that report and is therefore `N/A`.

The dashboard's **MoM Revenue Growth** KPI compares the latest month in the
report with its immediately preceding calendar month, using the same eligible
net-revenue totals as the monthly revenue table:

```text
MoM revenue growth (%) =
    ((current month net revenue - previous month net revenue)
      / previous month net revenue) * 100
```

Without a date filter, the current month is the latest month with eligible
sales, and the comparison is available only when the immediately preceding
month is within the available monthly history. Months without eligible sales
inside that history have zero revenue. When the previous month's revenue is
zero, the KPI displays `N/A — no previous-month revenue`; when no prior month
is available, it displays an insufficient-history status. A current month with
zero sales and a previous month with revenue produces `-100.00%`.

With `start_date` and/or `end_date` filters, the current month is the month
touched by `end_date` when supplied, or otherwise the latest month with
eligible sales. The KPI compares it to the immediately preceding calendar
month only if that month is on or after the report's first month (the month
touched by `start_date`, when supplied). Revenue values include only
transactions that pass the selected inclusive date range, so boundary months
can be partial; this is called out on the dashboard. A month covered by the
selected range but without eligible sales is treated as zero. If the preceding
month falls before the selected period, the KPI reports insufficient history
rather than presenting an out-of-period comparison.

## Return/refund handling

`refund_amount` stores the actual line-level amount refunded for the returned
units. It is subtracted exactly once in line net sales. `returned_quantity` is
validated and retained as descriptive data; it is **not** another sales
deduction. The refund is not recomputed from the returned quantity. The schema
requires refunds to be nonnegative, bounded by discounted line sales, and
consistent with a positive returned quantity.

## Category and region summaries

Category summaries group eligible item lines by `products.category`; region
summaries group by `orders.region`. Both report gross sales, discounts,
refunds, and net sales. They use the same eligible statuses and line formulas
as the summary KPI.

## Date filter

`start_date` and `end_date` are optional `YYYY-MM-DD` query parameters. The
database query filters `orders.order_date >= start_date` and/or
`orders.order_date <= end_date` using bound SQL parameters, making both
boundaries inclusive. An invalid date or start after end returns HTTP 400.
The product count is the total catalog count and does not vary with the
transaction date filter.

## Category and region filters

The dashboard's category and region dropdowns are populated from distinct,
non-null values in `products.category` and `orders.region`. A blank selection
means all values. Nonblank selections are validated against those database
options before the sales query runs; invalid values return HTTP 400.

Selected category, region, and date bounds are combined in the joined sales
query using parameterized equality/date predicates. All transaction-based
KPIs, monthly revenue, category/region summaries, the Top 5 products, and MoM
growth therefore use the same filtered eligible sales rows. The catalog
product-count KPI is narrowed by category when one is selected; region and
date do not alter the catalog count.

The category chart shows category sales within the active filters. If a
category is selected, it intentionally displays that category's total (a
single category) rather than implying a comparison with excluded categories.
The region chart behaves similarly for a selected region. The chart subtitles
identify when a dimension is narrowed and, when applicable, which other
dimension it is narrowed within. Monthly chart links carry the same date,
category, and region selections as the dashboard.

## Exclusions

Taxes and shipping are absent from the database schema, so neither is included.
No calculation subtracts returned quantity in addition to recorded refunds.

## Business insights

The insight cards are descriptive summaries of the current filtered report,
not forecasts. The leading category and region are selected by net sales; the
best-selling product is selected by quantity, then net sales as a tie-breaker.
The MoM observation uses the same adjacent-calendar-month comparison and
statuses as the KPI. If no eligible sales or comparison data exists, the
dashboard reports that insights or the comparison are unavailable instead of
showing fabricated values.

## CSV imports

Each uploaded row represents one order-item line. Rows with the same
`order_reference` are grouped into a single order, and each order can contain
multiple different products in accordance with the existing unique
`(order_id, product_id)` constraint. Invalid CSV rows block the entire import.
The `sales_import_batches` table stores a hash of normalized validated rows as
an idempotency key; reordering rows or changing CSV formatting does not create
a second import. The new tracking table does not alter existing transaction
records.

Imported line `discount_amount` and `refund_amount` are line totals and follow
the same net-sales formula above. Completed and delivered orders contribute to
sales metrics; cancelled orders may be stored but are excluded. The import
requires a positive line price when creating a new catalog product because
`products.unit_price` is constrained to be positive. Existing catalog products
must match the CSV category; the order-item unit price retains the imported
historical line price.
