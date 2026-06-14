from __future__ import annotations

from html import escape
from pathlib import Path as FilePath
from typing import Any

from fastapi import FastAPI, HTTPException, Path, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from scripts.query_postgres import (
    build_observations_by_indicator_response,
    build_search_response,
    get_series_observations_by_indicator,
    get_series_summary_by_indicator,
    list_datasets,
    search_series,
)


BASE_DIR = FilePath(__file__).resolve().parents[2]
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"


app = FastAPI(
    title="ONS StatsChat Lite API",
    description="A lightweight API for discovering public ONS/IMF SDMX series.",
    version="0.1.0",
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def read_template(template_name: str) -> str:
    return (TEMPLATES_DIR / template_name).read_text(encoding="utf-8")


@app.get("/", response_class=HTMLResponse)
def home_page() -> str:
    """
    Tiny browser UI for searching series metadata.

    This is intentionally simple: one HTML page calling our JSON API.
    """
    return read_template("index.html")


def render_series_page(
    summary: dict[str, Any],
    observations: list[dict[str, Any]],
) -> str:
    rows_html = "".join(
        "<tr>"
        f"<td>{escape(str(row.get('time_period', '')))}</td>"
        f"<td>{escape(str(row.get('obs_value', '')))}</td>"
        "</tr>"
        for row in observations
    )

    if not rows_html:
        rows_html = '<tr><td colspan="2">No observations found.</td></tr>'

    template = read_template("series.html")

    replacements = {
        "{{ dataset_id }}": escape(str(summary.get("dataset_id", ""))),
        "{{ dataset_title }}": escape(str(summary.get("dataset_title", "") or "")),
        "{{ indicator_code }}": escape(str(summary.get("indicator_code", ""))),
        "{{ indicator_name }}": escape(str(summary.get("indicator_name", ""))),
        "{{ frequency_name }}": escape(str(summary.get("frequency_name", "") or "")),
        "{{ first_period }}": escape(str(summary.get("first_period", "") or "")),
        "{{ latest_period }}": escape(str(summary.get("latest_period", "") or "")),
        "{{ observation_count }}": escape(
            str(summary.get("observation_count", "") or "")
        ),
        "{{ metadata_url }}": escape(
            f"/v1/datasets/{summary.get('dataset_id', '')}"
            f"/series/by-indicator/{summary.get('indicator_code', '')}",
            quote=True,
        ),
        "{{ observations_url }}": escape(
            f"/v1/datasets/{summary.get('dataset_id', '')}"
            f"/series/by-indicator/{summary.get('indicator_code', '')}"
            "/observations?limit=20",
            quote=True,
        ),
        "{{ observations_rows }}": rows_html,
    }

    for placeholder, value in replacements.items():
        template = template.replace(placeholder, value)

    return template


@app.get("/series/{dataset_id}/{indicator_code}", response_class=HTMLResponse)
def series_page(
    dataset_id: str = Path(
        ...,
        description="Dataset ID, for example NAG_GBR.",
    ),
    indicator_code: str = Path(
        ...,
        description="SDMX indicator code, for example NGDP_R_SA_XDC.",
    ),
) -> str:
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

    observations = get_series_observations_by_indicator(
        dataset_id,
        indicator_code,
        20,
    )

    return render_series_page(summary, observations)


@app.get("/health")
def health_check() -> dict[str, str]:
    """
    Simple health check endpoint.

    This proves the API server is running.
    """
    return {"status": "ok"}


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
