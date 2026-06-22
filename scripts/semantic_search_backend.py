from __future__ import annotations

import os
from collections.abc import Sequence
from typing import Any

from google import genai
from google.genai.types import EmbedContentConfig

from scripts.query_postgres import get_connection


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
        WITH ranked AS (
            SELECT
                d.series_id,
                d.dataset_id,
                datasets.title AS dataset_title,
                datasets.source_url,
                datasets.documentation_url,
                datasets.metadata_url,
                datasets.structure_ref,
                d.series_key,
                d.indicator_code,
                d.indicator_name,
                d.primary_text,
                COALESCE(
                    CASE
                        WHEN d.dataset_id = 'BOP_GBR' THEN (
                            SELECT string_agg(cleaned_part, ', ' ORDER BY ord)
                            FROM (
                                SELECT
                                    h.ord,
                                    NULLIF(
                                        trim(
                                            regexp_replace(
                                                h.value,
                                                '\\s*\\[BPM6\\]',
                                                '',
                                                'g'
                                            )
                                        ),
                                        ''
                                    ) AS cleaned_part
                                FROM jsonb_array_elements_text(
                                    d.parsed_metadata -> 'hierarchy'
                                ) WITH ORDINALITY AS h(value, ord)
                                WHERE h.ord > 1
                                  AND h.value <> 'Current Account'
                            ) parts
                            WHERE cleaned_part IS NOT NULL
                        )

                        WHEN d.dataset_id = 'SBS_GBR' THEN (
                            SELECT string_agg(h.value, ', ' ORDER BY h.ord)
                            FROM jsonb_array_elements_text(
                                d.parsed_metadata -> 'hierarchy'
                            ) WITH ORDINALITY AS h(value, ord)
                            WHERE h.ord > 2
                        )

                        WHEN d.dataset_id = 'CPI_GBR' THEN (
                            SELECT string_agg(h.value, ', ' ORDER BY h.ord)
                            FROM jsonb_array_elements_text(
                                d.parsed_metadata -> 'hierarchy'
                            ) WITH ORDINALITY AS h(value, ord)
                            WHERE h.ord > 1
                        )

                        ELSE
                            d.primary_text
                    END,
                    d.primary_text,
                    d.indicator_name,
                    d.indicator_code
                ) AS display_name,
                d.parsed_metadata ->> 'measure_type' AS measure_type,
                d.parsed_metadata ->> 'seasonal_adjustment' AS seasonal_adjustment,
                d.parsed_metadata ->> 'unit' AS unit,
                d.parsed_metadata ->> 'base_period' AS base_period,
                d.parsed_metadata ->> 'unit_multiplier' AS unit_multiplier,
                d.embedding_text,
                d.keyword_text,
                s.dimension_values ->> 'FREQ' AS frequency_code,
                s.dimension_labels -> 'FREQ' ->> 'name' AS frequency_name,
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
            MIN(o.time_period) AS first_period,
            MAX(o.time_period) AS latest_period,
            COUNT(o.observation_id) AS observation_count,
            ranked.cosine_distance,
            1.0 - ranked.cosine_distance AS similarity_score
        FROM ranked
        LEFT JOIN observations o
            ON o.series_id = ranked.series_id
        WHERE 1.0 - ranked.cosine_distance >= %(min_similarity)s
        GROUP BY
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
            ranked.cosine_distance
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
