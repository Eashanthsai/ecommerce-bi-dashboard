"""Matplotlib chart generation for the dashboard."""

from io import BytesIO

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter


CHART_NAMES = {
    "monthly-revenue": "monthly_revenue",
    "category-sales": "category_sales",
    "region-sales": "region_sales",
}

COLORS = ("#2563eb", "#0891b2", "#7c3aed", "#059669", "#ea580c", "#db2777")


def _currency_axis(value, _position):
    return f"${value:,.0f}"


def generate_chart(chart_name, analytics):
    """Return a PNG stream for one chart in the analytics report."""
    if chart_name not in CHART_NAMES:
        raise ValueError(f"Unknown dashboard chart: {chart_name}")

    data = analytics[CHART_NAMES[chart_name]]
    figure, axis = plt.subplots(figsize=(9, 4.6), constrained_layout=True)
    figure.patch.set_facecolor("#ffffff")
    axis.set_facecolor("#ffffff")
    axis.yaxis.set_major_formatter(FuncFormatter(_currency_axis))

    if chart_name == "monthly-revenue":
        axis.grid(axis="y", color="#e8edf4", linewidth=0.8)
        title = "Monthly net revenue"
        axis.set_xlabel("Month")
        axis.set_ylabel("Net revenue (USD)")
        if data:
            labels = [row["month"] for row in data]
            values = [row["revenue"] for row in data]
            positions = list(range(len(labels)))
            axis.plot(
                positions,
                values,
                color=COLORS[0],
                marker="o",
                linewidth=2.5,
                markersize=5,
            )
            axis.fill_between(positions, values, color=COLORS[0], alpha=0.1)
            axis.set_xticks(positions, labels, rotation=35, ha="right")
        else:
            axis.text(
                0.5,
                0.5,
                "No eligible sales for this date range",
                ha="center",
                va="center",
                transform=axis.transAxes,
                color="#64748b",
            )
            axis.set_xticks([])
    else:
        is_category = chart_name == "category-sales"
        field = "category" if is_category else "region"
        title = "Net sales by product category" if is_category else "Net sales by region"
        axis.set_xlabel("Net sales (USD)")
        axis.set_ylabel("Product category" if is_category else "Region")
        axis.xaxis.set_major_formatter(FuncFormatter(_currency_axis))
        axis.grid(axis="x", color="#e8edf4", linewidth=0.8)
        if data:
            ordered = sorted(data, key=lambda row: row["net_sales"])
            labels = [row[field] for row in ordered]
            values = [row["net_sales"] for row in ordered]
            colors = [COLORS[index % len(COLORS)] for index in range(len(labels))]
            axis.barh(labels, values, color=colors)
        else:
            axis.text(
                0.5,
                0.5,
                "No eligible sales for this date range",
                ha="center",
                va="center",
                transform=axis.transAxes,
                color="#64748b",
            )
            axis.set_yticks([])

    axis.set_axisbelow(True)
    axis.set_title(title, loc="left", fontsize=14, fontweight="bold", pad=14)
    for spine in ("top", "right", "left"):
        axis.spines[spine].set_visible(False)
    axis.spines["bottom"].set_color("#dbe3ed")

    image = BytesIO()
    figure.savefig(image, format="png", dpi=140, facecolor=figure.get_facecolor())
    plt.close(figure)
    image.seek(0)
    return image
