import pytest

import analysis


@pytest.fixture
def sales_records():
    return [
        {
            "order_id": 1,
            "order_status": "completed",
            "order_date": "2025-01-10",
            "region": "West",
            "product_name": "Laptop",
            "category": "Electronics",
            "quantity": 2,
            "unit_price": 50.00,
            "discount_amount": 10.00,
            "returned_quantity": 1,
            "refund_amount": 45.00,
        },
        {
            "order_id": 1,
            "order_status": "completed",
            "order_date": "2025-01-10",
            "region": "West",
            "product_name": "Desk Lamp",
            "category": "Home",
            "quantity": 1,
            "unit_price": 20.00,
            "discount_amount": 0.00,
            "returned_quantity": 0,
            "refund_amount": 0.00,
        },
        {
            "order_id": 2,
            "order_status": "delivered",
            "order_date": "2025-02-12",
            "region": "East",
            "product_name": "Desk Lamp",
            "category": "Home",
            "quantity": 1,
            "unit_price": 100.00,
            "discount_amount": 0.00,
            "returned_quantity": 0,
            "refund_amount": 0.00,
        },
        {
            "order_id": 3,
            "order_status": "cancelled",
            "order_date": "2025-02-15",
            "region": "West",
            "product_name": "Cancelled Item",
            "category": "Electronics",
            "quantity": 5,
            "unit_price": 200.00,
            "discount_amount": 0.00,
            "returned_quantity": 0,
            "refund_amount": 0.00,
        },
    ]


def test_summary_calculates_gross_net_and_distinct_eligible_orders(sales_records):
    result = analysis.analyze_sales(sales_records)

    assert result["summary"] == {
        "gross_sales": 220.0,
        "discounts": 10.0,
        "refunds": 45.0,
        "net_sales": 165.0,
        "eligible_order_count": 2,
        "average_order_value": 82.5,
    }


def test_cancelled_order_is_excluded_from_sales_and_order_count(sales_records):
    result = analysis.analyze_sales(sales_records)

    assert result["summary"]["eligible_order_count"] == 2
    assert result["summary"]["gross_sales"] == 220.0
    assert all(
        region["region"] != "West" or region["net_sales"] == 65.0
        for region in result["region_sales"]
    )


def test_recorded_refund_is_deducted_once_without_return_quantity_deduction(
    sales_records,
):
    result = analysis.analyze_sales(sales_records)

    # Cancelled orders are excluded; the returned unit is not deducted again.
    electronics = next(
        row for row in result["category_sales"] if row["category"] == "Electronics"
    )
    assert electronics["gross_sales"] == 100.0
    assert electronics["refunds"] == 45.0
    assert electronics["net_sales"] == 45.0


def test_monthly_revenue_and_month_over_month_growth(sales_records):
    result = analysis.analyze_sales(sales_records)

    assert result["monthly_revenue"] == [
        {
            "month": "2025-01",
            "revenue": 65.0,
            "month_over_month_growth_percent": None,
        },
        {
            "month": "2025-02",
            "revenue": 100.0,
            "month_over_month_growth_percent": 53.85,
        },
    ]


def _monthly_revenue_record(order_id, order_date, revenue):
    return {
        "order_id": order_id,
        "order_status": "completed",
        "order_date": order_date,
        "region": "West",
        "product_name": f"Product {order_id}",
        "category": "Test",
        "quantity": 1,
        "unit_price": revenue,
        "discount_amount": 0,
        "returned_quantity": 0,
        "refund_amount": 0,
    }


@pytest.mark.parametrize(
    ("previous_revenue", "current_revenue", "expected_growth"),
    [
        (100, 150, 50.0),
        (200, 100, -50.0),
        (100, 100, 0.0),
    ],
)
def test_month_over_month_growth_handles_positive_negative_and_zero_growth(
    previous_revenue, current_revenue, expected_growth
):
    result = analysis.analyze_sales(
        [
            _monthly_revenue_record(1, "2025-01-15", previous_revenue),
            _monthly_revenue_record(2, "2025-02-15", current_revenue),
        ]
    )

    assert result["month_over_month_growth"] == {
        "current_month": "2025-02",
        "current_revenue": float(current_revenue),
        "previous_month": "2025-01",
        "previous_revenue": float(previous_revenue),
        "growth_percent": expected_growth,
        "status": "calculated",
    }


def test_month_over_month_growth_handles_zero_previous_month_revenue():
    result = analysis.analyze_sales(
        [
            _monthly_revenue_record(1, "2025-01-15", 0),
            _monthly_revenue_record(2, "2025-02-15", 100),
        ]
    )

    assert result["month_over_month_growth"] == {
        "current_month": "2025-02",
        "current_revenue": 100.0,
        "previous_month": "2025-01",
        "previous_revenue": 0.0,
        "growth_percent": None,
        "status": "zero_previous_month_revenue",
    }


def test_month_over_month_growth_uses_zero_for_a_missing_calendar_month():
    result = analysis.analyze_sales(
        [
            _monthly_revenue_record(1, "2025-01-15", 100),
            _monthly_revenue_record(2, "2025-03-15", 50),
        ]
    )

    assert result["monthly_revenue"][1]["month"] == "2025-02"
    assert result["monthly_revenue"][1]["revenue"] == 0.0
    assert result["month_over_month_growth"] == {
        "current_month": "2025-03",
        "current_revenue": 50.0,
        "previous_month": "2025-02",
        "previous_revenue": 0.0,
        "growth_percent": None,
        "status": "zero_previous_month_revenue",
    }


def test_month_over_month_growth_counts_a_filtered_month_without_sales_as_zero():
    result = analysis.analyze_sales(
        [_monthly_revenue_record(1, "2025-01-15", 100)],
        start_date="2025-01-01",
        end_date="2025-02-28",
    )

    assert result["month_over_month_growth"] == {
        "current_month": "2025-02",
        "current_revenue": 0.0,
        "previous_month": "2025-01",
        "previous_revenue": 100.0,
        "growth_percent": -100.0,
        "status": "calculated",
    }


def test_month_over_month_growth_reports_insufficient_history():
    result = analysis.analyze_sales(
        [_monthly_revenue_record(1, "2025-01-15", 100)]
    )

    assert result["month_over_month_growth"] == {
        "current_month": "2025-01",
        "current_revenue": 100.0,
        "previous_month": "2024-12",
        "previous_revenue": None,
        "growth_percent": None,
        "status": "insufficient_history",
    }


def test_sales_export_rows_uses_eligible_lines_and_existing_net_sales_rules():
    records = [
        {
            "order_id": 1,
            "order_status": "delivered",
            "order_date": "2025-02-03",
            "region": "West",
            "product_name": "Desk Lamp",
            "category": "Home",
            "quantity": 2,
            "unit_price": 25,
            "discount_amount": 5,
            "returned_quantity": 1,
            "refund_amount": 10,
        },
        {
            "order_id": 2,
            "order_status": "cancelled",
            "order_date": "2025-02-04",
            "region": "West",
            "product_name": "Cancelled Lamp",
            "category": "Home",
            "quantity": 1,
            "unit_price": 20,
            "discount_amount": 0,
            "returned_quantity": 0,
            "refund_amount": 0,
        },
    ]

    assert analysis.sales_export_rows(records) == [
        {
            "order_date": "2025-02-03",
            "order_id": 1,
            "product_name": "Desk Lamp",
            "category": "Home",
            "region": "West",
            "quantity": 2,
            "unit_price": 25,
            "gross_sales": 50.0,
            "discounts": 5.0,
            "refunds": 10.0,
            "net_sales": 35.0,
        }
    ]


def test_category_and_region_sales_use_only_eligible_net_sales(sales_records):
    result = analysis.analyze_sales(sales_records)

    assert result["category_sales"] == [
        {
            "category": "Electronics",
            "gross_sales": 100.0,
            "discounts": 10.0,
            "refunds": 45.0,
            "net_sales": 45.0,
        },
        {
            "category": "Home",
            "gross_sales": 120.0,
            "discounts": 0.0,
            "refunds": 0.0,
            "net_sales": 120.0,
        },
    ]
    assert result["region_sales"] == [
        {
            "region": "East",
            "gross_sales": 100.0,
            "discounts": 0.0,
            "refunds": 0.0,
            "net_sales": 100.0,
        },
        {
            "region": "West",
            "gross_sales": 120.0,
            "discounts": 10.0,
            "refunds": 45.0,
            "net_sales": 65.0,
        },
    ]


def test_empty_dataset_returns_zero_totals_and_no_summaries():
    result = analysis.analyze_sales([])

    assert result == {
        "summary": {
            "gross_sales": 0.0,
            "discounts": 0.0,
            "refunds": 0.0,
            "net_sales": 0.0,
            "eligible_order_count": 0,
            "average_order_value": None,
        },
        "monthly_revenue": [],
        "category_sales": [],
        "region_sales": [],
        "top_products": [],
        "month_over_month_growth": {
            "current_month": None,
            "current_revenue": None,
            "previous_month": None,
            "previous_revenue": None,
            "growth_percent": None,
            "status": "insufficient_history",
        },
        "insights": [],
    }


def test_zero_previous_month_revenue_has_undefined_growth():
    records = [
        {
            "order_id": 1,
            "order_status": "completed",
            "order_date": "2025-01-10",
            "region": "West",
            "product_name": "Book A",
            "category": "Books",
            "quantity": 1,
            "unit_price": 0,
            "discount_amount": 0,
            "returned_quantity": 0,
            "refund_amount": 0,
        },
        {
            "order_id": 2,
            "order_status": "completed",
            "order_date": "2025-02-10",
            "region": "West",
            "product_name": "Book B",
            "category": "Books",
            "quantity": 1,
            "unit_price": 10,
            "discount_amount": 0,
            "returned_quantity": 0,
            "refund_amount": 0,
        },
    ]

    result = analysis.analyze_sales(records)

    assert result["monthly_revenue"][1]["month_over_month_growth_percent"] is None


def test_business_insights_use_current_sales_data_and_handle_ties(sales_records):
    result = analysis.analyze_sales(sales_records)

    assert result["insights"] == [
        {
            "title": "Highest-revenue category",
            "message": "Home leads with $120.00 in net revenue.",
        },
        {
            "title": "Best-selling product",
            "message": "Desk Lamp sold 2 units.",
        },
        {
            "title": "Strongest sales region",
            "message": "East leads with $100.00 in net revenue.",
        },
        {
            "title": "Month-over-month trend",
            "message": "Revenue increased by 53.85% from 2025-01 to 2025-02.",
        },
    ]


def test_missing_calendar_month_is_included_with_zero_revenue():
    records = [
        {
            "order_id": 1,
            "order_status": "completed",
            "order_date": "2025-01-10",
            "region": "West",
            "product_name": "Book A",
            "category": "Books",
            "quantity": 1,
            "unit_price": 10,
            "discount_amount": 0,
            "returned_quantity": 0,
            "refund_amount": 0,
        },
        {
            "order_id": 2,
            "order_status": "delivered",
            "order_date": "2025-03-10",
            "region": "West",
            "product_name": "Book B",
            "category": "Books",
            "quantity": 1,
            "unit_price": 20,
            "discount_amount": 0,
            "returned_quantity": 0,
            "refund_amount": 0,
        },
    ]

    result = analysis.analyze_sales(records)

    assert result["monthly_revenue"] == [
        {
            "month": "2025-01",
            "revenue": 10.0,
            "month_over_month_growth_percent": None,
        },
        {
            "month": "2025-02",
            "revenue": 0.0,
            "month_over_month_growth_percent": -100.0,
        },
        {
            "month": "2025-03",
            "revenue": 20.0,
            "month_over_month_growth_percent": None,
        },
    ]


def test_top_products_are_ranked_by_quantity_and_net_revenue():
    records = [
        {
            "order_id": 1,
            "order_status": "completed",
            "order_date": "2025-01-10",
            "region": "West",
            "product_name": "Laptop",
            "category": "Electronics",
            "quantity": 2,
            "unit_price": 50.00,
            "discount_amount": 10.00,
            "returned_quantity": 1,
            "refund_amount": 45.00,
        },
        {
            "order_id": 2,
            "order_status": "delivered",
            "order_date": "2025-01-12",
            "region": "East",
            "product_name": "Laptop",
            "category": "Electronics",
            "quantity": 3,
            "unit_price": 60.00,
            "discount_amount": 0.00,
            "returned_quantity": 0,
            "refund_amount": 0.00,
        },
        {
            "order_id": 3,
            "order_status": "delivered",
            "order_date": "2025-02-04",
            "region": "South",
            "product_name": "Desk Lamp",
            "category": "Home",
            "quantity": 1,
            "unit_price": 20.00,
            "discount_amount": 0.00,
            "returned_quantity": 0,
            "refund_amount": 0.00,
        },
        {
            "order_id": 4,
            "order_status": "completed",
            "order_date": "2025-02-05",
            "region": "North",
            "product_name": "Desk Lamp",
            "category": "Home",
            "quantity": 4,
            "unit_price": 25.00,
            "discount_amount": 5.00,
            "returned_quantity": 0,
            "refund_amount": 0.00,
        },
        {
            "order_id": 5,
            "order_status": "cancelled",
            "order_date": "2025-02-06",
            "region": "West",
            "product_name": "Cancelled Item",
            "category": "Electronics",
            "quantity": 10,
            "unit_price": 100.00,
            "discount_amount": 0.00,
            "returned_quantity": 0,
            "refund_amount": 0.00,
        },
    ]

    result = analysis.analyze_sales(records)

    assert result["top_products"] == [
        {
            "product_name": "Laptop",
            "category": "Electronics",
            "total_quantity": 5,
            "revenue": 225.0,
        },
        {
            "product_name": "Desk Lamp",
            "category": "Home",
            "total_quantity": 5,
            "revenue": 115.0,
        },
    ]


def test_invalid_missing_analytics_column_is_rejected():
    with pytest.raises(ValueError, match="missing required columns"):
        analysis.analyze_sales([{"order_id": 1}])
