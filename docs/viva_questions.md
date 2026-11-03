# Viva Questions and Answers

## Project and architecture

1. **What problem does the project address?**  
   It turns synthetic order records into consistent sales KPIs and comparisons
   by month, product category, and region.

2. **Who is the intended user?**  
   A business manager reviewing sales performance in the educational example.

3. **Why use Flask?**  
   Flask provides simple routes for the HTML dashboard, APIs, and chart images
   without introducing a larger framework.

4. **What is the request flow?**  
   Flask receives the request, `database.py` reads MySQL data, `analysis.py`
   calculates summaries, then a template, JSON response, or Matplotlib PNG is
   returned.

5. **Why are calculations outside the template?**  
   The analysis module centralizes business rules and lets the dashboard and
   APIs reuse the same results.

6. **Why use Pandas?**  
   Pandas provides tabular validation, grouping, date conversion, and monthly
   aggregation.

7. **Why use NumPy?**  
   NumPy handles numeric arrays and safe vectorized month-over-month
   calculations.

8. **Why use Matplotlib?**  
   It generates labeled static PNG charts on the server without requiring a
   separate JavaScript charting framework.

9. **Is the project production-ready?**  
   No. It is a local educational app and lacks production deployment,
   monitoring, authentication, and scaling features.

10. **Does it use real customer data?**  
    No. The included data is synthetic and the schema has no customer table.

## Database

11. **What are the database tables?**  
    The sales tables are `orders`, `products`, and `order_items`;
    `sales_import_batches` stores committed CSV fingerprints and counts.

12. **What does `orders` contain?**  
    Order ID, status, date, and region.

13. **What does `products` contain?**  
    Product ID, unique product name, category, and current catalog unit price.

14. **What does `order_items` contain?**  
    Order and product foreign keys, quantity, unit price, discount amount,
    returned quantity, and refund amount.

15. **Why is there a separate order-item table?**  
    An order may contain multiple products, and the line table records the
    quantity and amounts for each product within an order.

16. **How are foreign keys used?**  
    `order_items.order_id` references `orders.order_id`, and
    `order_items.product_id` references `products.product_id`.

17. **Why use DECIMAL for money?**  
    DECIMAL stores fixed-point monetary amounts more appropriately than
    approximate floating-point database types.

18. **How are database credentials stored?**  
    In the local ignored `.env` file and loaded by `config.py`; credentials are
    not embedded in Python source.

## Business rules and analytics

19. **What is gross sales?**  
    For each eligible item line, quantity multiplied by unit price, before
    discounts and refunds.

20. **How is net sales calculated?**  
    Line gross sales minus that line's `discount_amount` minus its recorded
    `refund_amount`.

21. **Which orders are eligible?**  
    Orders with status `completed` or `delivered`.

22. **How are cancelled orders handled?**  
    Their item lines are excluded from eligible sales summaries and order
    counts.

23. **How is eligible order count calculated?**  
    Count distinct eligible order IDs, so multiple item lines do not count an
    order multiple times.

24. **How is average order value calculated?**  
    Eligible net sales divided by the distinct eligible order count. It is
    `N/A` when no eligible order exists.

25. **How are returns handled?**  
    The stored refund amount is deducted once. Returned quantity is not
    converted into a second deduction.

26. **Are tax and shipping included?**  
    No. They do not exist in this schema.

27. **How is month-over-month growth calculated?**  
    `(current revenue - previous revenue) / previous revenue * 100`. The first
    month and a month after zero previous revenue show no percentage.

28. **How does the date filter work?**  
    It validates `YYYY-MM-DD` and binds inclusive `order_date >= start` and
    `order_date <= end` values as SQL parameters.

29. **What happens if a date is invalid?**  
    The page or API returns HTTP 400 without running the filtered analytics
    query.

30. **Does the product count obey the order date filter?**  
    No. It is the current total number of catalog products.

## Web application and tests

31. **What APIs are available?**  
    Health, product/order/order-item lists, consolidated analytics, summary,
    monthly revenue, category sales, and region sales routes.

32. **How are charts served?**  
    Three allowlisted chart routes generate PNG images in memory and return
    them with the `image/png` content type.

33. **What happens when chart data is empty?**  
    Matplotlib produces an image with a no-eligible-sales message, and the page
    also provides empty table states.

34. **How do you run the tests?**  
    From the project root with its virtual environment active:
    `python -m pytest -q`.

35. **Do mocked tests prove the user's database is working?**  
    No. Mocked tests verify application behavior; a live connection and query
    are needed to verify a particular local MySQL setup.

36. **What is a limitation of the sample dataset?**  
    It is small, synthetic, and covers only the defined example period; it is
    not evidence of real business performance.

37. **What could be added later?**  
    Authentication, browser integration tests, larger-data pagination,
    caching, and production deployment controls, if the project scope requires
    them.

## CSV import and dashboard workflow

38. **How does CSV import work?**  
    The app validates the CSV, shows a preview and row-level errors, and waits
    for explicit confirmation before writing. Each row represents one
    order-item line.

39. **How are multiple products in one order represented?**  
    Rows sharing `order_reference` are grouped into one generated order. The
    reference is only used during the upload because the existing orders
    schema has no external-reference column.

40. **How does the import avoid duplicates?**  
    It creates a SHA-256 fingerprint from normalized validated row values and
    stores it in `sales_import_batches`, whose primary key allows a logical
    CSV row set to be imported only once.

41. **What happens if an import encounters a database error?**  
    The batch marker, orders, new products, and order items are in one InnoDB
    transaction; the application rolls it back and does not report success.

42. **How are existing products handled?**  
    Products are matched by unique product name and must have the same
    category. New products use a positive catalog unit price from the first
    imported line; order-item lines retain the historical prices from CSV.

43. **What insights does the dashboard show?**  
    Highest net-revenue category, best-selling product by quantity, strongest
    region by net revenue, and the latest MoM trend when a comparison exists.
    These are descriptive, not forecasts.

44. **How do filters affect exports and analytics?**  
    Date, category, and region selections are validated and combined for
    transaction KPIs, product ranking, charts, insights, and CSV exports.

45. **What does the automated suite prove about MySQL imports?**  
    Unit tests mock transaction behavior to verify commit/rollback and
    duplicate handling. The live database connection and rendered dashboard
    were checked separately; the suite does not claim a real import was
    performed.
