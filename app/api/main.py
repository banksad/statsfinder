from __future__ import annotations

from pathlib import Path as FilePath
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Path, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

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
templates = Jinja2Templates(directory=TEMPLATES_DIR)


@app.get("/", response_class=HTMLResponse)
def home_page(request: Request) -> HTMLResponse:
    """
    Tiny browser UI for searching series metadata.

    This is intentionally simple: one HTML page calling our JSON API.
    """
    return templates.TemplateResponse("index.html", {"request": request})


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

    observations = get_series_observations_by_indicator(
        dataset_id,
        indicator_code,
        20,
    )

    encoded_dataset_id = quote(dataset_id, safe="")
    encoded_indicator_code = quote(indicator_code, safe="")
    metadata_url = (
        f"/v1/datasets/{encoded_dataset_id}"
        f"/series/by-indicator/{encoded_indicator_code}"
    )
    observations_url = f"{metadata_url}/observations?limit=20"

    return templates.TemplateResponse(
        "series.html",
        {
            "request": request,
            "summary": summary,
            "observations": observations,
            "metadata_url": metadata_url,
            "observations_url": observations_url,
        },
    )


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
