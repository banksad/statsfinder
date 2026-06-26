from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Path, Query
from fastapi.responses import Response

from app.api.exports import build_observations_csv, safe_filename_component
from app.services.postgres import (
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
from app.services.semantic_search import (
    DEFAULT_SEMANTIC_DIMENSION,
    DEFAULT_SEMANTIC_MODEL,
    semantic_search_series,
)

router = APIRouter()


@router.get("/health")
def health_check() -> dict[str, str]:
    """
    Simple health check endpoint.

    This proves the API server is running.
    """
    return {"status": "ok"}


@router.get("/health/db")
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


@router.get("/v1/datasets")
def list_datasets_endpoint() -> dict[str, Any]:
    """
    Return datasets currently available in this prototype.
    """
    rows = list_datasets()

    return {
        "count": len(rows),
        "datasets": rows,
    }


@router.get("/v1/datasets/{dataset_id}")
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


@router.get("/v1/datasets/{dataset_id}/series")
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


@router.get("/v1/series/search")
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


@router.get("/v1/series/search/semantic")
def semantic_search_series_endpoint(
    q: str = Query(
        ...,
        min_length=2,
        description="Natural-language search query.",
    ),
    dataset_id: str | None = Query(
        None,
        description="Optional dataset filter, for example NAG_GBR.",
    ),
    limit: int = Query(
        10,
        ge=1,
        le=50,
        description="Maximum number of semantic search results to return.",
    ),
    min_similarity: float = Query(
        0.0,
        ge=0.0,
        le=1.0,
        description=(
            "Minimum similarity score. Similarity is approximately "
            "1 - cosine distance."
        ),
    ),
    include_debug: bool = Query(
        False,
        description=(
            "Include retrieval debug fields such as embedding_text "
            "and keyword_text."
        ),
    ),
) -> dict[str, Any]:
    """
    Semantic search over source-backed series metadata.

    The query is embedded with Gemini Embedding 2, then compared with stored
    series metadata embeddings in Postgres using pgvector. The returned
    series metadata and observations are still database-backed.
    """
    try:
        rows = semantic_search_series(
            query=q,
            model=DEFAULT_SEMANTIC_MODEL,
            embedding_dim=DEFAULT_SEMANTIC_DIMENSION,
            limit=limit,
            dataset_id=dataset_id,
            min_similarity=min_similarity,
            include_debug=include_debug,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Semantic search is not available: {exc}",
        ) from exc

    return {
        "query": q,
        "search_type": "semantic",
        "model": DEFAULT_SEMANTIC_MODEL,
        "embedding_dim": DEFAULT_SEMANTIC_DIMENSION,
        "dataset_id": dataset_id,
        "limit": limit,
        "min_similarity": min_similarity,
        "include_debug": include_debug,
        "count": len(rows),
        "results": rows,
    }


@router.get("/v1/datasets/{dataset_id}/series/by-indicator/{indicator_code}")
def get_series_by_indicator_endpoint(
    dataset_id: str = Path(
        ...,
        description="Dataset ID, for example NAG_GBR.",
    ),
    indicator_code: str = Path(
        ...,
        description="SDMX indicator code, for example NGDP_R_SA_XDC.",
    ),
    series_id: int | None = Query(
        None,
        description=(
            "Optional exact series ID. Use this when one indicator has annual "
            "and quarterly variants."
        ),
    ),
) -> dict[str, Any]:
    """
    Return summary metadata for one series using public identifiers.

    Public users can use dataset_id and indicator_code. When that pair is
    ambiguous, series_id can disambiguate the exact annual or quarterly series.
    """
    row = get_series_summary_by_indicator(
        dataset_id,
        indicator_code,
        series_id=series_id,
    )

    if row is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Series not found for dataset_id={dataset_id} "
                f"and indicator_code={indicator_code}."
            ),
        )

    return row


@router.get(
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
    series_id: int | None = Query(
        None,
        description=(
            "Optional exact series ID. Use this when one indicator has annual "
            "and quarterly variants."
        ),
    ),
) -> dict[str, Any]:
    """
    Return observations for one series using public identifiers.

    Example:
        /v1/datasets/NAG_GBR/series/by-indicator/NGDP_R_SA_XDC/observations?limit=5
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

    rows = get_series_observations_by_indicator(
        dataset_id,
        indicator_code,
        series_id=series_id,
        limit=limit,
    )

    response = build_observations_by_indicator_response(
        dataset_id,
        indicator_code,
        limit,
        rows,
    )

    response["series_id"] = summary.get("series_id")

    return response


@router.get(
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
    series_id: int | None = Query(
        None,
        description=(
            "Optional exact series ID. Use this when one indicator has annual "
            "and quarterly variants."
        ),
    ),
) -> Response:
    """
    Return observations for one series as CSV.

    This is a lightweight export endpoint. It keeps the same source-backed
    identity model as the JSON observations endpoint.
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

    rows = get_series_observations_by_indicator(
        dataset_id,
        indicator_code,
        series_id=series_id,
        limit=limit,
    )

    csv_text = build_observations_csv(summary, rows)

    safe_dataset_id = safe_filename_component(dataset_id)
    safe_indicator_code = safe_filename_component(indicator_code)

    resolved_series_id = summary.get("series_id") or series_id

    if resolved_series_id is not None:
        safe_series_id = safe_filename_component(str(resolved_series_id))
        filename = (
            f"{safe_dataset_id}-{safe_indicator_code}"
            f"-series-{safe_series_id}-observations.csv"
        )
    else:
        filename = f"{safe_dataset_id}-{safe_indicator_code}-observations.csv"

    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


