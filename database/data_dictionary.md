# Data dictionary

This schema stores synthetic e-commerce transactions for the dashboard. All
example prices, discounts, and refunds are in **US dollars (USD)**. The sample
orders cover January through December 2025. No real customer data is included.
The SQL setup requires MySQL 8.0.16 or newer so its `CHECK` constraints are
enforced.

## `orders`

One row represents one order. An order can contain multiple `order_items`.

| Column | MySQL type | Rules | Description |
|---|---|---|---|
| `order_id` | `INT UNSIGNED` | Primary key; auto-increment | Unique order identifier. |
| `order_status` | `ENUM('completed', 'delivered', 'cancelled')` | Required | Status used to decide whether the order is eligible for sales KPIs. `completed` and `delivered` are eligible; `cancelled` is excluded. |
| `order_date` | `DATE` | Required | Date the order was placed; used for monthly reporting. |
| `region` | `VARCHAR(80)` | Required | Synthetic sales region associated with the order. |

## `products`

One row represents one product in the product catalog. The category is stored
here so it can be used to group order-item sales.

| Column | MySQL type | Rules | Description |
|---|---|---|---|
| `product_id` | `INT UNSIGNED` | Primary key; auto-increment | Unique product identifier. |
| `product_name` | `VARCHAR(120)` | Required; unique | Synthetic product name. |
| `category` | `VARCHAR(80)` | Required | Product category used for category-level reporting. |
| `unit_price` | `DECIMAL(10, 2)` | Required; greater than zero | Current catalog price. Imported order-item lines retain their own historical unit prices. |

## `order_items`

One row represents a product line within an order. The same product may appear
in many orders, but it can appear at most once within a particular order.

| Column | MySQL type | Rules | Description |
|---|---|---|---|
| `order_item_id` | `INT UNSIGNED` | Primary key; auto-increment | Unique order-line identifier. |
| `order_id` | `INT UNSIGNED` | Required; foreign key to `orders.order_id` | The order containing this product line. |
| `product_id` | `INT UNSIGNED` | Required; foreign key to `products.product_id` | The product on this line. |
| `quantity` | `SMALLINT UNSIGNED` | Required; greater than zero | Number of units originally ordered. |
| `unit_price` | `DECIMAL(10, 2)` | Required; nonnegative | Price per unit before discount. |
| `discount_amount` | `DECIMAL(10, 2)` | Required; defaults to zero; no greater than line gross | Total discount for the entire line, not a per-unit discount. |
| `returned_quantity` | `SMALLINT UNSIGNED` | Required; defaults to zero; no greater than quantity | Number of units returned from this line. |
| `refund_amount` | `DECIMAL(10, 2)` | Required; defaults to zero; nonnegative | Total refund actually issued for this line's returned units. It is a recorded amount, not another calculation of the same return. |

The tables use InnoDB foreign keys. Deleting an order or product referenced by an
order item is restricted to protect transaction history. Updating a referenced
key cascades to its order items. `order_items` also has a unique constraint on
`(order_id, product_id)`.

## `sales_import_batches`

One row records the successfully committed normalized content fingerprint of
an imported CSV. The primary key prevents importing the same logical row set
again. Import orders and item lines are written in one transaction with this
record; a failed import rolls back all three.

| Column | MySQL type | Rules | Description |
|---|---|---|---|
| `content_sha256` | `CHAR(64)` | Primary key | SHA-256 digest of canonical validated CSV row values. |
| `imported_at` | `TIMESTAMP` | Required; defaults to current timestamp | Time at which the import was committed. |
| `orders_imported` | `INT UNSIGNED` | Required; defaults to zero | Number of orders created by the import. |
| `items_imported` | `INT UNSIGNED` | Required; defaults to zero | Number of order-item lines created. |
| `products_created` | `INT UNSIGNED` | Required; defaults to zero | Number of new catalog products created. |
| `products_matched` | `INT UNSIGNED` | Required; defaults to zero | Number of existing catalog products matched. |

## KPI and amount definitions

Amounts are calculated per order-item line:

- **Line gross sales:** `quantity * unit_price`.
- **Line discounts:** `discount_amount`.
- **Line sales after discount, before returns:** `line gross sales - discount_amount`.
- **Line refunds:** `refund_amount`, entered once as the refund for returned units.
- **Line net sales:** `line gross sales - discount_amount - refund_amount`.
- **Eligible order:** an order whose status is `completed` or `delivered`.
- **Eligible order count:** count of distinct eligible `order_id` values. Orders
  with only cancelled status are excluded. Each eligible order is counted once
  regardless of the number of item lines.
- **Average order value (AOV):** eligible net sales divided by eligible order
  count; report `N/A` when there are no eligible orders.
- **Monthly revenue:** sum of eligible line net sales grouped by calendar month.
  Months without eligible sales between the first and last eligible order month
  are included with zero revenue.
- **Month-over-month growth:** `((current month revenue - previous month
  revenue) / previous month revenue) * 100`. Report `N/A` for the first month
  and whenever the previous month's revenue is zero.
- **Category and region sales:** eligible line gross sales, discounts, refunds,
  and net sales aggregated by the product category or order region.

Dashboard totals include only item lines belonging to eligible orders. For
these sample records, gross sales means the value of all originally ordered
units before discounts and returns; cancelled orders are excluded from KPI
totals. Discounts are subtracted once, then the recorded refunds are subtracted
once. Returned quantity is descriptive and must **not** also be converted into
a second deduction. Tax and shipping are not represented or included.

`refund_amount` is stored explicitly because real refunds may depend on return
policy or adjustments. For the synthetic examples, each refund is the
discount-adjusted amount for the returned quantity. Constraints ensure a refund
is nonzero only when at least one unit is marked returned, and that it does not
exceed the line amount after discount.

## Sample domain values

- Statuses: `completed`, `delivered`, `cancelled`
- Regions: `Northeast`, `South`, `Midwest`, `West`
- Categories: `Electronics`, `Home`, `Apparel`, `Beauty`, `Sports`, `Books`
