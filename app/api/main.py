from __future__ import annotations

from pathlib import Path as FilePath
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Path, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from scripts.query_postgres import (
    build_observations_by_indicator_response,
    build_search_response,
    get_database_health,
    get_series_observations_by_indicator,
    get_series_summary_by_indicator,
    list_datasets,
    search_series,
)


BASE_DIR = FilePath(__file__).resolve().parents[2]
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"


app = FastAPI(
    title="Stats Finder API",
    description=(
        "A lightweight API for discovering official statistical series "
        "grounded in published SDMX data."
    ),
    version="0.1.0",
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)


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


def build_line_chart_data(
    observations: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Build labelled SVG line chart data from observations.

    Python prepares the coordinates and tick labels.
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

    width = 720
    height = 320

    plot_left = 72
    plot_right = 24
    plot_top = 24
    plot_bottom = 56

    plot_width = width - plot_left - plot_right
    plot_height = height - plot_top - plot_bottom

    if not values:
        return {
            "has_data": False,
            "width": width,
            "height": height,
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

    points = [
        f"{x_for_index(index):.2f},{y_for_value(row['value']):.2f}"
        for index, row in enumerate(values)
    ]

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

    return {
        "has_data": True,
        "width": width,
        "height": height,
        "plot_left": plot_left,
        "plot_right": width - plot_right,
        "plot_top": plot_top,
        "plot_bottom": height - plot_bottom,
        "points": " ".join(points),
        "x_ticks": x_ticks,
        "y_ticks": y_ticks,
        "first_period": values[0]["time_period"],
        "latest_period": values[-1]["time_period"],
        "min_value": format_chart_value(min_value),
        "max_value": format_chart_value(max_value),
    }


@app.get("/")
def home() -> RedirectResponse:
    """
    Redirect the product root to the canonical Search page.
    """
    return RedirectResponse(url="/search", status_code=307)


@app.get("/search", response_class=HTMLResponse)
def search_page(request: Request) -> HTMLResponse:
    """
    Browser UI for searching series metadata.
    """
    datasets = list_datasets()

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "datasets": datasets,
            "active_nav": "search",
        },
    )


@app.get("/browse", response_class=HTMLResponse)
def browse_page(request: Request) -> HTMLResponse:
    """
    Placeholder Browse page.

    This will become the structured discovery tree.
    """
    return templates.TemplateResponse(
        request=request,
        name="browse.html",
        context={
            "active_nav": "browse",
        },
    )


@app.get("/api", response_class=HTMLResponse)
def api_page(request: Request) -> HTMLResponse:
    """
    Human-friendly API landing page.
    """
    return templates.TemplateResponse(
        request=request,
        name="api.html",
        context={
            "active_nav": "api",
        },
    )


@app.get("/series/{dataset_id}/{indicator_code}", response_class=HTMLResponse)
def series_page(
    request: Request,
    dataset_id: str = Path(
        ...,
        description="Dataset ID, for example NAG_GBR.",
    ),
    indicator_code: str = Path(
        ...,
        description="SDMX indicator code, for example NGDP_R_SA_XDC.",
    ),
) -> HTMLResponse:
    """
    Friendly browser page for one series.
    """
    summary = get_series_summary_by_indicator(dataset_id, indicator_code)

    if summary is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Series not found for dataset_id={dataset_id} "
                f"and indicator_code={indicator_code}."
            ),
        )

    table_observations = get_series_observations_by_indicator(
        dataset_id,
        indicator_code,
        20,
    )

    chart_observations = get_series_observations_by_indicator(
        dataset_id,
        indicator_code,
        500,
    )

    chart = build_line_chart_data(chart_observations)

    encoded_dataset_id = quote(dataset_id, safe="")
    encoded_indicator_code = quote(indicator_code, safe="")
    metadata_url = (
        f"/v1/datasets/{encoded_dataset_id}"
        f"/series/by-indicator/{encoded_indicator_code}"
    )
    observations_url = f"{metadata_url}/observations?limit=20"

    return templates.TemplateResponse(
        request=request,
        name="series.html",
        context={
            "summary": summary,
            "observations": table_observations,
            "chart": chart,
            "metadata_url": metadata_url,
            "observations_url": observations_url,
            "active_nav": "search",
        },
    )


@app.get("/health")
def health_check() -> dict[str, str]:
    """
    Simple health check endpoint.

    This proves the API server is running.
    """
    return {"status": "ok"}


@app.get("/health/db")
def database_health_check() -> dict[str, Any]:
    """
    Database-aware health check.

    This proves the API can reach Postgres and query the core tables.
    """
    try:
        counts = get_database_health()
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "error",
                "database": "unreachable",
                "error": str(exc),
            },
        ) from exc

    return {
        "status": "ok",
        "database": "reachable",
        **counts,
    }


@app.get("/v1/datasets")
def list_datasets_endpoint() -> dict[str, Any]:
    """
    Return datasets currently available in this prototype.
    """
    rows = list_datasets()

    return {
        "count": len(rows),
        "datasets": rows,
    }


@app.get("/v1/series/search")
def search_series_endpoint(
    q: str = Query(
        ...,
        min_length=1,
        description="Search query, for example 'real gdp'.",
    ),
    limit: int = Query(
        10,
        ge=1,
        le=50,
        description="Maximum number of series results to return.",
    ),
    dataset_id: str | None = Query(
        None,
        description="Optional dataset ID to restrict search, for example CPI_GBR.",
    ),
) -> dict[str, Any]:
    """
    Search for statistical series.

    Examples:
        /v1/series/search?q=real%20gdp&limit=3
        /v1/series/search?q=price&dataset_id=CPI_GBR
    """
    rows = search_series(
        q,
        limit,
        dataset_id=dataset_id,
    )

    return build_search_response(
        q,
        limit,
        rows,
        dataset_id=dataset_id,
    )


@app.get("/v1/datasets/{dataset_id}/series/by-indicator/{indicator_code}")
def get_series_by_indicator_endpoint(
    dataset_id: str = Path(
        ...,
        description="Dataset ID, for example NAG_GBR.",
    ),
    indicator_code: str = Path(
        ...,
        description="SDMX indicator code, for example NGDP_R_SA_XDC.",
    ),
) -> dict[str, Any]:
    """
    Return summary metadata for one series using public identifiers.

    This endpoint avoids requiring public users to know the internal series_id.
    """
    row = get_series_summary_by_indicator(dataset_id, indicator_code)

    if row is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Series not found for dataset_id={dataset_id} "
                f"and indicator_code={indicator_code}."
            ),
        )

    return row


@app.get(
    "/v1/datasets/{dataset_id}/series/by-indicator/{indicator_code}/observations"
)
def get_series_observations_by_indicator_endpoint(
    dataset_id: str = Path(
        ...,
        description="Dataset ID, for example NAG_GBR.",
    ),
    indicator_code: str = Path(
        ...,
        description="SDMX indicator code, for example NGDP_R_SA_XDC.",
    ),
    limit: int = Query(
        10,
        ge=1,
        le=500,
        description="Maximum number of observations to return.",
    ),
) -> dict[str, Any]:
    """
    Return observations for one series using public identifiers.

    Example:
        /v1/datasets/NAG_GBR/series/by-indicator/NGDP_R_SA_XDC/observations?limit=5
    """
    summary = get_series_summary_by_indicator(dataset_id, indicator_code)

    if summary is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Series not found for dataset_id={dataset_id} "
                f"and indicator_code={indicator_code}."
            ),
        )

    rows = get_series_observations_by_indicator(
        dataset_id,
        indicator_code,
        limit,
    )

    return build_observations_by_indicator_response(
        dataset_id,
        indicator_code,
        limit,
        rows,
    )
