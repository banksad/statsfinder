from __future__ import annotations

from typing import Any


def format_chart_value(value: float) -> str:
    """
    Format chart tick labels without making them too noisy.
    """
    abs_value = abs(value)

    if abs_value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.1f}bn"

    if abs_value >= 1_000_000:
        return f"{value / 1_000_000:.1f}m"

    if abs_value >= 1_000:
        return f"{value / 1_000:.1f}k"

    if value.is_integer():
        return str(int(value))

    return f"{value:.2f}"


def format_chart_readout_value(value: float) -> str:
    """
    Format hover/latest values.

    Keep more precision than axis ticks, but avoid long floating point noise.
    """
    if value.is_integer():
        return f"{int(value):,}"

    return f"{value:,.3f}".rstrip("0").rstrip(".")


def build_display_unit_label(summary: dict[str, Any]) -> str:
    """
    Build a human-friendly chart unit label.

    Keep the raw SDMX unit in metadata, but make the chart label nicer.
    For UK national currency series, show pounds and the unit multiplier.
    """
    raw_unit = (summary.get("unit") or "").strip()
    unit_multiplier = str(summary.get("unit_multiplier") or "").strip()
    dataset_id = str(summary.get("dataset_id") or "")

    multiplier_labels = {
        "0": "",
        "3": "thousands",
        "6": "millions",
        "9": "billions",
        "12": "trillions",
    }

    multiplier_label = multiplier_labels.get(unit_multiplier)

    is_uk_series = dataset_id.endswith("_GBR")

    if raw_unit.lower() == "national currency" and is_uk_series:
        base_unit = "£"
    elif raw_unit:
        base_unit = raw_unit
    else:
        base_unit = "Value"

    if multiplier_label:
        return f"{base_unit} {multiplier_label}"

    return base_unit


def build_line_chart_data(
    observations: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Build labelled SVG line chart data from observations.

    Python prepares:
    - SVG coordinates
    - axis ticks
    - polyline string
    - per-point data for lightweight JavaScript hover interactions

    Jinja only renders the SVG.
    """
    values: list[dict[str, Any]] = []

    for observation in observations:
        time_period = observation.get("time_period")
        obs_value = observation.get("obs_value")

        if time_period is None or obs_value is None:
            continue

        try:
            numeric_value = float(obs_value)
        except (TypeError, ValueError):
            continue

        values.append(
            {
                "time_period": str(time_period),
                "value": numeric_value,
            }
        )

    values = sorted(values, key=lambda row: row["time_period"])

    width = 900
    height = 420

    plot_left = 86
    plot_right_margin = 32
    plot_top = 28
    plot_bottom_margin = 72

    plot_right = width - plot_right_margin
    plot_bottom = height - plot_bottom_margin

    plot_width = plot_right - plot_left
    plot_height = plot_bottom - plot_top

    if not values:
        return {
            "has_data": False,
            "width": width,
            "height": height,
            "point_objects": [],
        }

    min_value = min(row["value"] for row in values)
    max_value = max(row["value"] for row in values)

    if min_value == max_value:
        min_value = min_value - 1
        max_value = max_value + 1

    value_range = max_value - min_value

    def x_for_index(index: int) -> float:
        if len(values) == 1:
            return plot_left + (plot_width / 2)

        return plot_left + (index / (len(values) - 1)) * plot_width

    def y_for_value(value: float) -> float:
        return plot_top + ((max_value - value) / value_range) * plot_height

    points: list[str] = []
    point_objects: list[dict[str, Any]] = []

    for index, row in enumerate(values):
        x = x_for_index(index)
        y = y_for_value(row["value"])

        points.append(f"{x:.2f},{y:.2f}")

        point_objects.append(
            {
                "x": round(x, 2),
                "y": round(y, 2),
                "period": row["time_period"],
                "value": format_chart_readout_value(row["value"]),
                "raw_value": row["value"],
            }
        )

    middle_index = len(values) // 2

    x_ticks = [
        {
            "x": x_for_index(0),
            "label": values[0]["time_period"],
            "anchor": "start",
        },
        {
            "x": x_for_index(middle_index),
            "label": values[middle_index]["time_period"],
            "anchor": "middle",
        },
        {
            "x": x_for_index(len(values) - 1),
            "label": values[-1]["time_period"],
            "anchor": "end",
        },
    ]

    midpoint_value = min_value + (value_range / 2)

    y_ticks = [
        {
            "y": y_for_value(max_value),
            "label": format_chart_value(max_value),
        },
        {
            "y": y_for_value(midpoint_value),
            "label": format_chart_value(midpoint_value),
        },
        {
            "y": y_for_value(min_value),
            "label": format_chart_value(min_value),
        },
    ]

    latest_row = values[-1]

    return {
        "has_data": True,
        "width": width,
        "height": height,
        "plot_left": plot_left,
        "plot_right": plot_right,
        "plot_top": plot_top,
        "plot_bottom": plot_bottom,
        "points": " ".join(points),
        "point_objects": point_objects,
        "x_ticks": x_ticks,
        "y_ticks": y_ticks,
        "first_period": values[0]["time_period"],
        "latest_period": latest_row["time_period"],
        "latest_value": format_chart_readout_value(latest_row["value"]),
        "min_value": format_chart_value(min_value),
        "max_value": format_chart_value(max_value),
    }


