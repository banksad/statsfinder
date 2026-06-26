from __future__ import annotations

import os
from typing import Any

from app.services.gemini import embed_query, vector_literal
from app.services.postgres import get_connection


DEFAULT_REFERENCE_MODEL = os.environ.get(
    "REFERENCE_EMBEDDING_MODEL",
    "gemini-embedding-2",
)
DEFAULT_REFERENCE_DIMENSION = int(
    os.environ.get("REFERENCE_EMBEDDING_DIMENSION", "768")
)


def embed_reference_query(
    query: str,
    model: str = DEFAULT_REFERENCE_MODEL,
    embedding_dim: int = DEFAULT_REFERENCE_DIMENSION,
) -> list[float]:
    return embed_query(
        query=query,
        model=model,
        output_dimensionality=embedding_dim,
    )


def search_reference_chunks(
    query: str,
    limit: int = 3,
    source_id: str | None = "sna2008",
    model: str = DEFAULT_REFERENCE_MODEL,
    embedding_dim: int = DEFAULT_REFERENCE_DIMENSION,
) -> list[dict[str, Any]]:
    query_embedding = embed_reference_query(
        query=query,
        model=model,
        embedding_dim=embedding_dim,
    )

    sql = """
        SELECT
            c.chunk_id,
            c.source_id,
            c.source_title,
            c.source_url,
            c.page_number,
            c.chunk_index,
            c.chunk_text,
            e.embedding <=> %s::vector AS cosine_distance,
            1 - (e.embedding <=> %s::vector) AS similarity_score
        FROM reference_chunks c
        JOIN reference_chunk_embeddings e
            ON e.chunk_id = c.chunk_id
        WHERE e.model = %s
          AND e.embedding_dim = %s
          AND (%s::text IS NULL OR c.source_id = %s::text)
        ORDER BY
            e.embedding <=> %s::vector
        LIMIT %s;
    """

    embedding_literal = vector_literal(query_embedding)

    params = (
        embedding_literal,
        embedding_literal,
        model,
        embedding_dim,
        source_id,
        source_id,
        embedding_literal,
        limit,
    )

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return list(cur.fetchall())
