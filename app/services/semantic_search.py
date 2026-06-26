from __future__ import annotations

import os
from collections.abc import Sequence
from typing import Any

from google import genai
from google.genai.types import EmbedContentConfig

from app.services.postgres import get_connection
from scripts.series_sql import (
    OBSERVATION_SUMMARY_CTE,
    OBSERVATION_SUMMARY_SELECT,
    display_name_select,
    frequency_select,
    parsed_metadata_select,
    search_document_metadata_select,
)


DEFAULT_SEMANTIC_MODEL = "gemini-embedding-2"
DEFAULT_SEMANTIC_DIMENSION = 768


def require_gemini_environment() -> None:
    required_names = [
        "GOOGLE_CLOUD_PROJECT",
        "GOOGLE_CLOUD_LOCATION",
        "GOOGLE_GENAI_USE_ENTERPRISE",
    ]

    missing = [name for name in required_names if not os.getenv(name)]

    if missing:
        raise RuntimeError(
            "Missing required environment variables: "
            + ", ".join(missing)
        )


def vector_literal(values: Sequence[float]) -> str:
    return "[" + ",".join(str(float(value)) for value in values) + "]"


def embed_query(
    query: str,
    model: str = DEFAULT_SEMANTIC_MODEL,
    output_dimensionality: int = DEFAULT_SEMANTIC_DIMENSION,
) -> list[float]:
    """
    Embed a user query for retrieval.

    Stored series documents were embedded with RETRIEVAL_DOCUMENT.
    User queries should be embedded with RETRIEVAL_QUERY.
    """
    require_gemini_environment()

    client = genai.Client()

    response = client.models.embed_content(
        model=model,
        contents=[query],
        config=EmbedContentConfig(
            task_type="RETRIEVAL_QUERY",
            output_dimensionality=output_dimensionality,
        ),
    )

    if not response.embeddings:
        raise RuntimeError("Gemini returned no embeddings.")

    values = response.embeddings[0].values

    if values is None:
        raise RuntimeError("Gemini returned an embedding with no values.")

    return [float(value) for value in values]


def search_series_by_embedding(
    query_embedding: Sequence[float],
    model: str = DEFAULT_SEMANTIC_MODEL,
    embedding_dim: int = DEFAULT_SEMANTIC_DIMENSION,
    limit: int = 10,
    dataset_id: str | None = None,
    min_similarity: float = 0.0,
    include_debug: bool = False,
) -> list[dict[str, Any]]:
    """
    Search stored series embeddings using cosine distance.

    pgvector's <=> operator returns cosine distance for vector values.
    Lower distance is better. We expose similarity as 1 - distance for
    easier API/UI interpretation.
    """
    where_parts = [
        "e.embedding_model = %(model)s",
        "e.embedding_dim = %(embedding_dim)s",
    ]

    params: dict[str, Any] = {
        "model": model,
        "embedding_dim": embedding_dim,
        "query_embedding": vector_literal(query_embedding),
        "limit": limit,
        "min_similarity": min_similarity,
    }

    if dataset_id is not None:
        where_parts.append("d.dataset_id = %(dataset_id)s")
        params["dataset_id"] = dataset_id

    where_clause = "WHERE " + " AND ".join(where_parts)

    sql = f"""
        WITH {OBSERVATION_SUMMARY_CTE},
        ranked AS (
            SELECT
{search_document_metadata_select("d", "datasets")},
                {display_name_select(
                    dataset_id_expression="d.dataset_id",
                    parsed_metadata_expression="d.parsed_metadata",
                    primary_text_expression="d.primary_text",
                    indicator_name_expression="d.indicator_name",
                    indicator_code_expression="d.indicator_code",
                )},
{parsed_metadata_select("d.parsed_metadata")},
                d.embedding_text,
                d.keyword_text,
{frequency_select('s')},
                e.embedding <=> %(query_embedding)s::vector AS cosine_distance
            FROM series_embeddings e
            JOIN series_search_documents d
                ON d.series_id = e.series_id
            JOIN series s
                ON s.series_id = d.series_id
            JOIN datasets
                ON datasets.dataset_id = d.dataset_id
            {where_clause}
        )
        SELECT
            ranked.series_id,
            ranked.dataset_id,
            ranked.dataset_title,
            ranked.source_url,
            ranked.documentation_url,
            ranked.metadata_url,
            ranked.structure_ref,
            ranked.series_key,
            ranked.indicator_code,
            ranked.indicator_name,
            ranked.primary_text,
            ranked.display_name,
            ranked.measure_type,
            ranked.seasonal_adjustment,
            ranked.unit,
            ranked.base_period,
            ranked.unit_multiplier,
            ranked.embedding_text,
            ranked.keyword_text,
            ranked.frequency_code,
            ranked.frequency_name,
{OBSERVATION_SUMMARY_SELECT.rstrip()},
            ranked.cosine_distance,
            1.0 - ranked.cosine_distance AS similarity_score
        FROM ranked
        LEFT JOIN observation_summary
            ON observation_summary.series_id = ranked.series_id
        WHERE 1.0 - ranked.cosine_distance >= %(min_similarity)s
        ORDER BY
            ranked.cosine_distance
        LIMIT %(limit)s;
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = list(cur.fetchall())

    if include_debug:
        return rows

    for row in rows:
        row.pop("embedding_text", None)
        row.pop("keyword_text", None)

    return rows


def semantic_search_series(
    query: str,
    model: str = DEFAULT_SEMANTIC_MODEL,
    embedding_dim: int = DEFAULT_SEMANTIC_DIMENSION,
    limit: int = 10,
    dataset_id: str | None = None,
    min_similarity: float = 0.0,
    include_debug: bool = False,
) -> list[dict[str, Any]]:
    query_embedding = embed_query(
        query=query,
        model=model,
        output_dimensionality=embedding_dim,
    )

    return search_series_by_embedding(
        query_embedding=query_embedding,
        model=model,
        embedding_dim=embedding_dim,
        limit=limit,
        dataset_id=dataset_id,
        min_similarity=min_similarity,
        include_debug=include_debug,
    )
