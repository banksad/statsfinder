from __future__ import annotations

from pathlib import Path as FilePath
from typing import Any

from fastapi import APIRouter, HTTPException, Path, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.api.exports import build_series_resource_urls
from app.charts import build_display_unit_label, build_line_chart_data
from app.services.postgres import (
    get_dataset,
    get_series_observations_by_indicator,
    get_series_summary_by_indicator,
    list_datasets,
    list_series_for_dataset,
)
from app.services.semantic_search import (
    DEFAULT_SEMANTIC_DIMENSION,
    DEFAULT_SEMANTIC_MODEL,
    semantic_search_series,
)

BASE_DIR = FilePath(__file__).resolve().parents[2]
TEMPLATES_DIR = BASE_DIR / "templates"
templates = Jinja2Templates(directory=TEMPLATES_DIR)

router = APIRouter()


@router.get("/")
def home() -> RedirectResponse:
    """
    Redirect the product root to the canonical Search page.
    """
    return RedirectResponse(url="/search", status_code=307)


@router.get("/search", response_class=HTMLResponse)
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


@router.get("/browse", response_class=HTMLResponse)
def browse_page(request: Request) -> HTMLResponse:
    """
    Structured Browse page.
    """
    return templates.TemplateResponse(
        request=request,
        name="browse.html",
        context={
            "active_nav": "browse",
        },
    )


@router.get("/browse/datasets/{dataset_id}", response_class=HTMLResponse)
def browse_dataset_page(
    request: Request,
    dataset_id: str = Path(
        ...,
        description="Dataset ID, for example NAG_GBR.",
    ),
    q: str | None = Query(
        None,
        description="Optional semantic search query within this dataset.",
    ),
) -> HTMLResponse:
    """
    Lightweight dataset Browse page.

    Browse page:
    - shows source-backed dataset metadata
    - shows a full series table
    - optionally shows top semantic matches within the dataset
    """
    dataset = get_dataset(dataset_id)

    if dataset is None:
        raise HTTPException(
            status_code=404,
            detail=f"Dataset not found for dataset_id={dataset_id}.",
        )

    series = list_series_for_dataset(dataset_id, limit=500)

    search_query = q.strip() if q else ""
    search_results: list[dict[str, Any]] = []
    search_error: str | None = None

    if search_query:
        try:
            search_results = semantic_search_series(
                query=search_query,
                model=DEFAULT_SEMANTIC_MODEL,
                embedding_dim=DEFAULT_SEMANTIC_DIMENSION,
                limit=5,
                dataset_id=dataset_id,
                min_similarity=0.0,
                include_debug=False,
            )
        except RuntimeError as exc:
            search_error = str(exc)

    return templates.TemplateResponse(
        request=request,
        name="browse_dataset.html",
        context={
            "dataset": dataset,
            "series": series,
            "series_count": len(series),
            "search_query": search_query,
            "search_results": search_results,
            "search_error": search_error,
            "active_nav": "browse",
        },
    )


@router.get("/api", response_class=HTMLResponse)
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


@router.get("/series/{dataset_id}/{indicator_code}", response_class=HTMLResponse)
def series_page(
    request: Request,
    dataset_id: str,
    indicator_code: str,
    series_id: int | None = Query(
        None,
        description=(
            "Optional exact series ID. Use this when one indicator has annual "
            "and quarterly variants."
        ),
    ),
) -> HTMLResponse:
    """
    Friendly browser page for one exact series.

    Public URLs still use dataset_id and indicator_code, but series_id can be
    supplied to disambiguate annual/quarterly variants.
    """
    summary = get_series_summary_by_indicator(
        dataset_id,
        indicator_code,
        series_id=series_id,
    )

    if summary is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Series not found for dataset_id={dataset_id} "
                f"and indicator_code={indicator_code}."
            ),
        )

    resolved_series_id = summary.get("series_id") or series_id

    table_observations = get_series_observations_by_indicator(
        dataset_id,
        indicator_code,
        series_id=series_id,
        limit=20,
    )

    chart_observations = get_series_observations_by_indicator(
        dataset_id,
        indicator_code,
        series_id=series_id,
        limit=500,
    )

    chart = build_line_chart_data(chart_observations)

    urls = build_series_resource_urls(
        dataset_id=dataset_id,
        indicator_code=indicator_code,
        series_id=resolved_series_id,
    )

    return templates.TemplateResponse(
        request=request,
        name="series.html",
        context={
            "summary": summary,
            "observations": table_observations,
            "chart": chart,
            "display_unit": build_display_unit_label(summary),
            "metadata_url": urls["metadata_url"],
            "observations_url": urls["observations_url"],
            "observations_csv_url": urls["observations_csv_url"],
            "active_nav": "search",
        },
    )


