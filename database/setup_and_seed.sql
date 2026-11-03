-- E-Commerce Business Intelligence Dashboard
-- Synthetic sample data only. Currency: USD.
-- Requires MySQL 8.0.16 or newer so CHECK constraints are enforced.
-- Select the target database before running this script. Railway creates its
-- database from MYSQLDATABASE; local MySQL users should create and select
-- ecommerce_bi_dashboard before executing the schema and seed statements.

CREATE TABLE IF NOT EXISTS products (
    product_id INT UNSIGNED NOT NULL AUTO_INCREMENT,
    product_name VARCHAR(120) NOT NULL,
    category VARCHAR(80) NOT NULL,
    unit_price DECIMAL(10, 2) NOT NULL DEFAULT 0.00,
    PRIMARY KEY (product_id),
    UNIQUE KEY uq_products_product_name (product_name),
    CONSTRAINT chk_products_unit_price_positive
        CHECK (unit_price > 0.00)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS orders (
    order_id INT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_status ENUM('completed', 'delivered', 'cancelled') NOT NULL,
    order_date DATE NOT NULL,
    region VARCHAR(80) NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_orders_date_status (order_date, order_status),
    KEY idx_orders_region (region)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS order_items (
    order_item_id INT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_id INT UNSIGNED NOT NULL,
    product_id INT UNSIGNED NOT NULL,
    quantity SMALLINT UNSIGNED NOT NULL,
    unit_price DECIMAL(10, 2) NOT NULL,
    discount_amount DECIMAL(10, 2) NOT NULL DEFAULT 0.00,
    returned_quantity SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    refund_amount DECIMAL(10, 2) NOT NULL DEFAULT 0.00,
    PRIMARY KEY (order_item_id),
    UNIQUE KEY uq_order_items_order_product (order_id, product_id),
    KEY idx_order_items_product (product_id),
    CONSTRAINT chk_order_items_quantity_positive
        CHECK (quantity > 0),
    CONSTRAINT chk_order_items_unit_price_nonnegative
        CHECK (unit_price >= 0.00),
    CONSTRAINT chk_order_items_discount_nonnegative
        CHECK (discount_amount >= 0.00),
    CONSTRAINT chk_order_items_discount_not_over_gross
        CHECK (discount_amount <= quantity * unit_price),
    CONSTRAINT chk_order_items_returned_quantity
        CHECK (returned_quantity <= quantity),
    CONSTRAINT chk_order_items_refund_nonnegative
        CHECK (refund_amount >= 0.00),
    CONSTRAINT chk_order_items_refund_not_over_discounted_sales
        CHECK (refund_amount <= (quantity * unit_price) - discount_amount),
    CONSTRAINT chk_order_items_return_refund_consistent
        CHECK (
            (returned_quantity = 0 AND refund_amount = 0.00)
            OR (returned_quantity > 0 AND refund_amount > 0.00)
        ),
    CONSTRAINT fk_order_items_order
        FOREIGN KEY (order_id) REFERENCES orders (order_id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_order_items_product
        FOREIGN KEY (product_id) REFERENCES products (product_id)
        ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB;

-- Content fingerprints make an identical CSV import idempotent without
-- altering existing order, product, or order-item records.
CREATE TABLE IF NOT EXISTS sales_import_batches (
    content_sha256 CHAR(64) NOT NULL,
    imported_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    orders_imported INT UNSIGNED NOT NULL DEFAULT 0,
    items_imported INT UNSIGNED NOT NULL DEFAULT 0,
    products_created INT UNSIGNED NOT NULL DEFAULT 0,
    products_matched INT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (content_sha256)
) ENGINE=InnoDB;

-- Product catalog: all products and transactions below are synthetic.
INSERT INTO products (product_id, product_name, category, unit_price) VALUES
    (201, 'Wireless Headphones', 'Electronics', 99.99),
    (202, 'Laptop Stand', 'Electronics', 59.00),
    (203, 'Coffee Maker', 'Home', 129.50),
    (204, 'Desk Lamp', 'Home', 34.99),
    (205, 'Cotton Hoodie', 'Apparel', 48.50),
    (206, 'Skincare Set', 'Beauty', 72.00),
    (207, 'Yoga Mat', 'Sports', 39.99),
    (208, 'Cookbook', 'Books', 24.50);

-- Two orders per month across all of 2025, across four sales regions.
INSERT INTO orders (order_id, order_status, order_date, region) VALUES
    (1001, 'delivered', '2025-01-08', 'Northeast'),
    (1002, 'completed', '2025-01-21', 'West'),
    (1003, 'delivered', '2025-02-05', 'South'),
    (1004, 'completed', '2025-02-19', 'Midwest'),
    (1005, 'completed', '2025-03-11', 'Northeast'),
    (1006, 'delivered', '2025-03-26', 'West'),
    (1007, 'delivered', '2025-04-03', 'Midwest'),
    (1008, 'completed', '2025-04-22', 'South'),
    (1009, 'completed', '2025-05-09', 'West'),
    (1010, 'delivered', '2025-05-24', 'Northeast'),
    (1011, 'delivered', '2025-06-06', 'South'),
    (1012, 'completed', '2025-06-18', 'Midwest'),
    (1013, 'cancelled', '2025-07-02', 'West'),
    (1014, 'delivered', '2025-07-17', 'Northeast'),
    (1015, 'completed', '2025-08-04', 'South'),
    (1016, 'delivered', '2025-08-23', 'Midwest'),
    (1017, 'completed', '2025-09-10', 'Northeast'),
    (1018, 'delivered', '2025-09-28', 'West'),
    (1019, 'delivered', '2025-10-07', 'South'),
    (1020, 'completed', '2025-10-20', 'Midwest'),
    (1021, 'completed', '2025-11-05', 'West'),
    (1022, 'delivered', '2025-11-19', 'Northeast'),
    (1023, 'cancelled', '2025-12-03', 'Midwest'),
    (1024, 'delivered', '2025-12-16', 'South');

-- discount_amount and refund_amount are line-level totals, not per-unit values.
-- Refunds are the amounts actually refunded for returned quantity, after discount.
-- Example: order 1002 has 2 headphones ($100 gross), a $10 discount, and a
-- $45 refund for one returned headphone. Do not calculate or deduct that
-- return a second time elsewhere.
INSERT INTO order_items
    (order_item_id, order_id, product_id, quantity, unit_price,
     discount_amount, returned_quantity, refund_amount)
VALUES
    (1,  1001, 203, 1,  80.00,  0.00, 0,  0.00),
    (2,  1001, 208, 2,  25.00,  5.00, 0,  0.00),
    (3,  1002, 201, 2,  50.00, 10.00, 1, 45.00),
    (4,  1002, 207, 1,  30.00,  0.00, 0,  0.00),
    (5,  1003, 202, 2,  45.00,  0.00, 0,  0.00),
    (6,  1003, 206, 1,  60.00,  5.00, 0,  0.00),
    (7,  1004, 205, 2,  40.00,  8.00, 0,  0.00),
    (8,  1004, 208, 1,  25.00,  0.00, 0,  0.00),
    (9,  1005, 203, 1,  80.00,  0.00, 0,  0.00),
    (10, 1005, 201, 1,  50.00,  5.00, 0,  0.00),
    (11, 1006, 205, 3,  40.00, 12.00, 1, 36.00),
    (12, 1006, 204, 1,  35.00,  0.00, 0,  0.00),
    (13, 1007, 202, 1,  45.00,  0.00, 0,  0.00),
    (14, 1007, 207, 2,  30.00,  5.00, 0,  0.00),
    (15, 1008, 206, 2,  60.00, 10.00, 0,  0.00),
    (16, 1008, 208, 2,  25.00,  0.00, 0,  0.00),
    (17, 1009, 201, 1,  50.00,  0.00, 0,  0.00),
    (18, 1009, 203, 2,  80.00, 15.00, 0,  0.00),
    (19, 1010, 205, 1,  40.00,  0.00, 0,  0.00),
    (20, 1010, 206, 1,  60.00,  0.00, 0,  0.00),
    (21, 1011, 203, 2,  80.00, 20.00, 1, 70.00),
    (22, 1011, 204, 1,  35.00,  0.00, 0,  0.00),
    (23, 1012, 202, 2,  45.00,  5.00, 0,  0.00),
    (24, 1012, 208, 3,  25.00,  5.00, 0,  0.00),
    (25, 1013, 201, 1,  50.00,  0.00, 0,  0.00),
    (26, 1013, 207, 1,  30.00,  0.00, 0,  0.00),
    (27, 1014, 203, 1,  80.00,  0.00, 0,  0.00),
    (28, 1014, 205, 2,  40.00,  8.00, 0,  0.00),
    (29, 1015, 206, 2,  60.00,  5.00, 0,  0.00),
    (30, 1015, 207, 1,  30.00,  0.00, 0,  0.00),
    (31, 1016, 204, 2,  35.00,  5.00, 0,  0.00),
    (32, 1016, 202, 1,  45.00,  0.00, 0,  0.00),
    (33, 1017, 201, 2,  50.00, 10.00, 0,  0.00),
    (34, 1017, 208, 1,  25.00,  0.00, 0,  0.00),
    (35, 1018, 204, 1,  35.00,  5.00, 1, 30.00),
    (36, 1018, 206, 1,  60.00,  0.00, 0,  0.00),
    (37, 1019, 203, 1,  80.00,  0.00, 0,  0.00),
    (38, 1019, 207, 2,  30.00,  5.00, 0,  0.00),
    (39, 1020, 205, 2,  40.00,  0.00, 0,  0.00),
    (40, 1020, 202, 1,  45.00,  0.00, 0,  0.00),
    (41, 1021, 201, 1,  50.00,  5.00, 0,  0.00),
    (42, 1021, 206, 2,  60.00, 10.00, 0,  0.00),
    (43, 1022, 207, 2,  30.00,  0.00, 1, 30.00),
    (44, 1022, 208, 2,  25.00,  0.00, 0,  0.00),
    (45, 1023, 203, 1,  80.00,  0.00, 0,  0.00),
    (46, 1023, 204, 1,  35.00,  0.00, 0,  0.00),
    (47, 1024, 206, 1,  60.00,  5.00, 0,  0.00),
    (48, 1024, 205, 1,  40.00,  0.00, 0,  0.00);
