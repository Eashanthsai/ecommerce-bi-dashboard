from io import BytesIO

import pytest

import charts


def test_generate_monthly_revenue_chart_returns_png():
    report = {
        "monthly_revenue": [
            {
                "month": "2025-01",
                "revenue": 125.5,
                "month_over_month_growth_percent": None,
            }
        ]
    }

    image = charts.generate_chart("monthly-revenue", report)

    assert isinstance(image, BytesIO)
    assert image.read(8) == b"\x89PNG\r\n\x1a\n"


@pytest.mark.parametrize(
    ("chart_name", "key", "field"),
    [
        ("category-sales", "category_sales", "category"),
        ("region-sales", "region_sales", "region"),
    ],
)
def test_generate_comparison_chart_returns_png(chart_name, key, field):
    report = {
        key: [
            {
                field: "Group A",
                "gross_sales": 100.0,
                "discounts": 5.0,
                "refunds": 10.0,
                "net_sales": 85.0,
            }
        ]
    }

    image = charts.generate_chart(chart_name, report)

    assert image.read(8) == b"\x89PNG\r\n\x1a\n"


def test_empty_chart_data_still_returns_png():
    image = charts.generate_chart("category-sales", {"category_sales": []})

    assert image.read(8) == b"\x89PNG\r\n\x1a\n"


def test_unknown_chart_name_is_rejected():
    with pytest.raises(ValueError, match="Unknown dashboard chart"):
        charts.generate_chart("sales-pie", {})
