"""Pandas and NumPy calculations for e-commerce sales reporting."""

import numpy as np
import pandas as pd


ELIGIBLE_STATUSES = {"completed", "delivered"}
REQUIRED_COLUMNS = {
    "order_id",
    "order_status",
    "order_date",
    "region",
    "product_name",
    "category",
    "quantity",
    "unit_price",
    "discount_amount",
    "returned_quantity",
    "refund_amount",
}
AMOUNT_COLUMNS = ("gross_sales", "discounts", "refunds", "net_sales")
SALES_EXPORT_COLUMNS = (
    "order_date",
    "order_id",
    "product_name",
    "category",
    "region",
    "quantity",
    "unit_price",
    "gross_sales",
    "discounts",
    "refunds",
    "net_sales",
)


def _empty_month_over_month_growth():
    return {
        "current_month": None,
        "current_revenue": None,
        "previous_month": None,
        "previous_revenue": None,
        "growth_percent": None,
        "status": "insufficient_history",
    }


def _month_over_month_growth(monthly_revenue, start_date=None, end_date=None):
    monthly_totals = {
        row["month"]: row["revenue"]
        for row in monthly_revenue
    }
    available_months = list(monthly_totals)

    if end_date is not None:
        current_period = pd.Period(end_date, freq="M")
    elif available_months:
        current_period = pd.Period(max(available_months), freq="M")
    else:
        current_period = None

    if start_date is not None:
        first_period = pd.Period(start_date, freq="M")
    elif available_months:
        first_period = pd.Period(min(available_months), freq="M")
    else:
        first_period = None

    if current_period is None:
        return _empty_month_over_month_growth()

    previous_period = current_period - 1
    current_month = str(current_period)
    previous_month = str(previous_period)
    current_revenue = (
        _rounded_amount(monthly_totals.get(current_month, 0.0))
        if first_period is not None and current_period >= first_period
        else None
    )
    previous_revenue = (
        _rounded_amount(monthly_totals.get(previous_month, 0.0))
        if first_period is not None and previous_period >= first_period
        else None
    )

    result = {
        "current_month": current_month,
        "current_revenue": current_revenue,
        "previous_month": previous_month,
        "previous_revenue": previous_revenue,
        "growth_percent": None,
        "status": "insufficient_history",
    }
    if previous_revenue is None:
        return result
    if previous_revenue == 0:
        result["status"] = "zero_previous_month_revenue"
        return result

    result["growth_percent"] = _rounded_amount(
        (current_revenue - previous_revenue) / previous_revenue * 100
    )
    result["status"] = "calculated"
    return result


def _empty_analytics(month_over_month_growth=None):
    return {
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
        "month_over_month_growth": (
            month_over_month_growth or _empty_month_over_month_growth()
        ),
        "insights": [],
    }


def _rounded_amount(value):
    return round(float(value), 2)


def _group_sales(data, column):
    if data.empty:
        return []

    grouped = (
        data.groupby(column, as_index=False, dropna=False)[list(AMOUNT_COLUMNS)]
        .sum()
        .sort_values(column)
    )
    return [
        {
            column: row[column],
            **{
                amount: _rounded_amount(row[amount])
                for amount in AMOUNT_COLUMNS
            },
        }
        for row in grouped.to_dict(orient="records")
    ]


def _prepare_sales_data(records):
    data = records.copy() if isinstance(records, pd.DataFrame) else pd.DataFrame(records)
    if data.empty:
        return data

    missing_columns = REQUIRED_COLUMNS.difference(data.columns)
    if missing_columns:
        raise ValueError(
            "Sales data is missing required columns: "
            + ", ".join(sorted(missing_columns))
        )

    numeric_columns = (
        "quantity",
        "unit_price",
        "discount_amount",
        "returned_quantity",
        "refund_amount",
    )
    for column in numeric_columns:
        data[column] = pd.to_numeric(data[column], errors="raise")
        values = data[column].to_numpy(dtype=float)
        if not np.isfinite(values).all():
            raise ValueError(f"{column} must contain finite numeric values.")

    if data[list(REQUIRED_COLUMNS)].isnull().any().any():
        raise ValueError("Sales data cannot contain missing required values.")

    if (data["quantity"] <= 0).any():
        raise ValueError("quantity must be greater than zero.")
    if (data[["unit_price", "discount_amount", "refund_amount"]] < 0).any().any():
        raise ValueError("Prices, discounts, and refunds cannot be negative.")
    if (data["returned_quantity"] < 0).any() or (
        data["returned_quantity"] > data["quantity"]
    ).any():
        raise ValueError("returned_quantity must be between zero and quantity.")

    line_gross = data["quantity"].to_numpy(dtype=float) * data[
        "unit_price"
    ].to_numpy(dtype=float)
    discounts = data["discount_amount"].to_numpy(dtype=float)
    refunds = data["refund_amount"].to_numpy(dtype=float)
    if (discounts > line_gross).any():
        raise ValueError("discount_amount cannot exceed line gross sales.")
    if (refunds > line_gross - discounts).any():
        raise ValueError("refund_amount cannot exceed discounted line sales.")

    data["gross_sales"] = line_gross
    data["discounts"] = discounts
    data["refunds"] = refunds
    data["net_sales"] = line_gross - discounts - refunds
    data["order_date"] = pd.to_datetime(data["order_date"], errors="raise")
    return data


def sales_export_rows(records):
    """Return eligible order-item lines with validated net-sales amounts."""
    data = _prepare_sales_data(records)
    if data.empty:
        return []

    eligible = data.loc[data["order_status"].isin(ELIGIBLE_STATUSES)]
    rows = []
    for record in eligible.to_dict(orient="records"):
        order_date = record["order_date"]
        rows.append(
            {
                "order_date": order_date.strftime("%Y-%m-%d"),
                "order_id": record["order_id"],
                "product_name": record["product_name"],
                "category": record["category"],
                "region": record["region"],
                "quantity": record["quantity"],
                "unit_price": record["unit_price"],
                "gross_sales": _rounded_amount(record["gross_sales"]),
                "discounts": _rounded_amount(record["discounts"]),
                "refunds": _rounded_amount(record["refunds"]),
                "net_sales": _rounded_amount(record["net_sales"]),
            }
        )
    return rows


def analyze_sales(records, start_date=None, end_date=None):
    """Calculate sales KPIs and summaries from joined order-item records.

    Each input row must represent one order-item joined to its order and
    product. Returns are deducted only through the recorded refund amount;
    returned_quantity is validated but never used as an additional deduction.
    Date bounds are used to define the comparison months, including a month
    with no sales at the end of a filtered period.
    """
    data = _prepare_sales_data(records)
    if data.empty:
        return _empty_analytics(
            _month_over_month_growth([], start_date=start_date, end_date=end_date)
        )

    eligible = data.loc[data["order_status"].isin(ELIGIBLE_STATUSES)].copy()
    if eligible.empty:
        return _empty_analytics(
            _month_over_month_growth([], start_date=start_date, end_date=end_date)
        )

    eligible_order_count = int(eligible["order_id"].nunique())
    totals = {
        amount: _rounded_amount(np.sum(eligible[amount].to_numpy(dtype=float)))
        for amount in AMOUNT_COLUMNS
    }
    totals["eligible_order_count"] = eligible_order_count
    totals["average_order_value"] = (
        _rounded_amount(totals["net_sales"] / eligible_order_count)
        if eligible_order_count
        else None
    )

    eligible["order_month"] = eligible["order_date"].dt.to_period("M")
    monthly = (
        eligible.groupby("order_month")["net_sales"]
        .sum()
        .reindex(
            pd.period_range(
                start=eligible["order_month"].min(),
                end=eligible["order_month"].max(),
                freq="M",
            ),
            fill_value=0,
        )
        .rename_axis("order_month")
        .reset_index(name="net_sales")
    )
    revenue = monthly["net_sales"].to_numpy(dtype=float)
    previous_revenue = np.roll(revenue, 1)
    growth = np.full(revenue.shape, np.nan, dtype=float)
    valid_previous_month = np.isfinite(previous_revenue) & (previous_revenue != 0)
    np.divide(
        revenue - previous_revenue,
        previous_revenue,
        out=growth,
        where=valid_previous_month,
    )
    if growth.size:
        growth[0] = np.nan

    monthly_revenue = [
        {
            "month": str(row["order_month"]),
            "revenue": _rounded_amount(row["net_sales"]),
            "month_over_month_growth_percent": (
                _rounded_amount(growth[index] * 100)
                if np.isfinite(growth[index])
                else None
            ),
        }
        for index, row in enumerate(monthly.to_dict(orient="records"))
    ]
    month_over_month_growth = _month_over_month_growth(
        monthly_revenue,
        start_date=start_date,
        end_date=end_date,
    )

    top_products = (
        eligible.groupby(["product_name", "category"], as_index=False, dropna=False)
        .agg(
            total_quantity=("quantity", "sum"),
            gross_sales=("gross_sales", "sum"),
            discounts=("discounts", "sum"),
            refunds=("refunds", "sum"),
        )
        .copy()
    )
    top_products["net_sales"] = (
        top_products["gross_sales"] - top_products["discounts"] - top_products["refunds"]
    )
    top_products = (
        top_products[["product_name", "category", "total_quantity", "net_sales"]]
        .sort_values(
            ["total_quantity", "net_sales", "product_name"],
            ascending=[False, False, True],
        )
        .head(5)
        .reset_index(drop=True)
    )
    top_products = [
        {
            "product_name": row["product_name"],
            "category": row["category"],
            "total_quantity": int(row["total_quantity"]),
            "revenue": _rounded_amount(row["net_sales"]),
        }
        for row in top_products.to_dict(orient="records")
    ]

    category_sales = _group_sales(eligible, "category")
    region_sales = _group_sales(eligible, "region")
    insights = []
    if category_sales:
        leading_category = max(
            category_sales, key=lambda row: (row["net_sales"], row["category"])
        )
        insights.append(
            {
                "title": "Highest-revenue category",
                "message": (
                    f'{leading_category["category"]} leads with '
                    f'${leading_category["net_sales"]:,.2f} in net revenue.'
                ),
            }
        )
    if top_products:
        leading_product = max(
            top_products,
            key=lambda row: (
                row["total_quantity"],
                row["revenue"],
                row["product_name"],
            ),
        )
        insights.append(
            {
                "title": "Best-selling product",
                "message": (
                    f'{leading_product["product_name"]} sold '
                    f'{leading_product["total_quantity"]:,} units.'
                ),
            }
        )
    if region_sales:
        leading_region = max(
            region_sales, key=lambda row: (row["net_sales"], row["region"])
        )
        insights.append(
            {
                "title": "Strongest sales region",
                "message": (
                    f'{leading_region["region"]} leads with '
                    f'${leading_region["net_sales"]:,.2f} in net revenue.'
                ),
            }
        )

    growth = month_over_month_growth
    if growth["status"] == "calculated":
        direction = "increased" if growth["growth_percent"] > 0 else "decreased"
        if growth["growth_percent"] == 0:
            direction = "was unchanged"
        insights.append(
            {
                "title": "Month-over-month trend",
                "message": (
                    f'Revenue {direction} by {abs(growth["growth_percent"]):.2f}% '
                    f'from {growth["previous_month"]} to {growth["current_month"]}.'
                ),
            }
        )
    else:
        insights.append(
            {
                "title": "Month-over-month trend",
                "message": "A consecutive-month revenue comparison is not available.",
            }
        )

    return {
        "summary": totals,
        "monthly_revenue": monthly_revenue,
        "category_sales": category_sales,
        "region_sales": region_sales,
        "top_products": top_products,
        "month_over_month_growth": month_over_month_growth,
        "insights": insights,
    }
