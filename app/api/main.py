from __future__ import annotations

import csv
import io
import re

from pathlib import Path as FilePath
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Path, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from scripts.query_postgres import (
    build_observations_by_indicator_response,
    build_search_response,
    get_database_health,
    get_dataset,
    get_series_observations_by_indicator,
    get_series_summary_by_indicator,
    list_datasets,
    list_series_for_dataset,
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

def safe_filename_component(value: str) -> str:
    """
    Convert a public identifier into a safe filename component.

    Dataset IDs and indicator codes are already controlled-looking strings,
    but this keeps the Content-Disposition filename robust.
    """
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value)
    cleaned = cleaned.strip("-")

    return cleaned or "series"


def build_observations_csv(
    summary: dict[str, Any],
    observations: list[dict[str, Any]],
) -> str:
    """
    Build a simple long-format CSV for one statistical series.

    The CSV repeats series metadata on each row. That makes the file easy to
    combine with other exported series later.
    """
    output = io.StringIO()

    fieldnames = [
        "dataset_id",
        "dataset_title",
        "series_key",
        "indicator_code",
        "indicator_name",
        "frequency_code",
        "frequency_name",
        "time_period",
        "obs_value",
        "source_url",
        "documentation_url",
        "metadata_url",
        "structure_ref",
    ]

    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()

    for observation in observations:
        writer.writerow(
            {
                "dataset_id": summary.get("dataset_id"),
                "dataset_title": summary.get("dataset_title"),
                "series_key": summary.get("series_key"),
                "indicator_code": summary.get("indicator_code"),
                "indicator_name": summary.get("indicator_name"),
                "frequency_code": summary.get("frequency_code"),
                "frequency_name": summary.get("frequency_name"),
                "time_period": observation.get("time_period"),
                "obs_value": observation.get("obs_value"),
                "source_url": summary.get("source_url"),
                "documentation_url": summary.get("documentation_url"),
                "metadata_url": summary.get("metadata_url"),
                "structure_ref": summary.get("structure_ref"),
            }
        )

    return output.getvalue()


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

@app.get("/browse/datasets/{dataset_id}", response_class=HTMLResponse)
def browse_dataset_page(
    request: Request,
    dataset_id: str = Path(
        ...,
        description="Dataset ID, for example NAG_GBR.",
    ),
) -> HTMLResponse:
    """
    Lightweight dataset Browse page.

    Browse v1 is deliberately simple:
    curated topic page -> source-backed dataset page -> existing series pages.
    """
    dataset = get_dataset(dataset_id)

    if dataset is None:
        raise HTTPException(
            status_code=404,
            detail=f"Dataset not found for dataset_id={dataset_id}.",
        )

    series = list_series_for_dataset(dataset_id, limit=500)

    return templates.TemplateResponse(
        request=request,
        name="browse_dataset.html",
        context={
            "dataset": dataset,
            "series": series,
            "series_count": len(series),
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
    observations_csv_url = f"{metadata_url}/observations.csv?limit=10000"

    return templates.TemplateResponse(
        request=request,
        name="series.html",
        context={
            "summary": summary,
            "observations": table_observations,
            "chart": chart,
            "metadata_url": metadata_url,
            "observations_url": observations_url,
            "observations_csv_url": observations_csv_url,
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

@app.get("/v1/datasets/{dataset_id}")
def get_dataset_endpoint(
    dataset_id: str = Path(
        ...,
        description="Dataset ID, for example NAG_GBR.",
    ),
) -> dict[str, Any]:
    """
    Return one dataset by public dataset_id.

    This is the machine-readable counterpart to /browse/datasets/{dataset_id}.
    """
    row = get_dataset(dataset_id)

    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"Dataset not found for dataset_id={dataset_id}.",
        )

    return row


@app.get("/v1/datasets/{dataset_id}/series")
def list_dataset_series_endpoint(
    dataset_id: str = Path(
        ...,
        description="Dataset ID, for example NAG_GBR.",
    ),
    limit: int = Query(
        100,
        ge=1,
        le=500,
        description="Maximum number of series to return.",
    ),
    offset: int = Query(
        0,
        ge=0,
        description="Number of series to skip.",
    ),
) -> dict[str, Any]:
    """
    Return series belonging to one dataset.

    This is the machine-readable counterpart to the dataset Browse page's
    series table.
    """
    dataset = get_dataset(dataset_id)

    if dataset is None:
        raise HTTPException(
            status_code=404,
            detail=f"Dataset not found for dataset_id={dataset_id}.",
        )

    rows = list_series_for_dataset(
        dataset_id,
        limit=limit,
        offset=offset,
    )

    return {
        "dataset_id": dataset_id,
        "limit": limit,
        "offset": offset,
        "count": len(rows),
        "total_series_count": dataset["series_count"],
        "series": rows,
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

@app.get(
    "/v1/datasets/{dataset_id}/series/by-indicator/{indicator_code}/observations.csv"
)
def get_series_observations_by_indicator_csv_endpoint(
    dataset_id: str = Path(
        ...,
        description="Dataset ID, for example NAG_GBR.",
    ),
    indicator_code: str = Path(
        ...,
        description="SDMX indicator code, for example NGDP_R_SA_XDC.",
    ),
    limit: int = Query(
        10000,
        ge=1,
        le=100000,
        description="Maximum number of observations to include in the CSV.",
    ),
) -> Response:
    """
    Return observations for one series as CSV.

    This is a lightweight export endpoint. It keeps the same source-backed
    identity model as the JSON observations endpoint.
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

    csv_text = build_observations_csv(summary, rows)

    safe_dataset_id = safe_filename_component(dataset_id)
    safe_indicator_code = safe_filename_component(indicator_code)
    filename = f"{safe_dataset_id}-{safe_indicator_code}-observations.csv"

    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )
