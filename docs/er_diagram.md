# Entity-relationship diagram

The diagram represents the sales tables and import-fingerprint table created by
[`setup_and_seed.sql`](../database/setup_and_seed.sql).

```mermaid
erDiagram
    orders ||--|{ order_items : contains
    products ||--o{ order_items : identifies

    orders {
        INT order_id PK
        ENUM order_status
        DATE order_date
        VARCHAR region
    }

    products {
        INT product_id PK
        VARCHAR product_name UK
        VARCHAR category
        DECIMAL unit_price
    }

    order_items {
        INT order_item_id PK
        INT order_id FK
        INT product_id FK
        SMALLINT quantity
        DECIMAL unit_price
        DECIMAL discount_amount
        SMALLINT returned_quantity
        DECIMAL refund_amount
    }

    sales_import_batches {
        CHAR content_sha256 PK
        TIMESTAMP imported_at
        INT orders_imported
        INT items_imported
        INT products_created
        INT products_matched
    }
```

## Relationships

- One order has one or more order-item lines. Each order-item line belongs to
  exactly one order.
- One product can appear in zero or more order-item lines. Each order-item line
  refers to exactly one product.
- The pair `(order_id, product_id)` is unique in `order_items`, so a product
  appears at most once in a particular order.
- `order_items.order_id` references `orders.order_id`;
  `order_items.product_id` references `products.product_id`.
- `sales_import_batches` has no sales-table foreign key. Its content hash is a
  transactional idempotency marker for normalized CSV row sets.
