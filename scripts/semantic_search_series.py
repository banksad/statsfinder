from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from typing import Any

from google import genai
from google.genai.types import EmbedContentConfig

from app.services.postgres import get_connection


DEFAULT_MODEL = "gemini-embedding-2"
DEFAULT_DIMENSION = 768


def require_environment() -> None:
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
    client: genai.Client,
    query: str,
    model: str,
    output_dimensionality: int,
) -> list[float]:
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


def semantic_search(
    query_embedding: Sequence[float],
    model: str,
    embedding_dim: int,
    limit: int,
    dataset_id: str | None,
) -> list[dict[str, Any]]:
    where_parts = [
        "e.embedding_model = %(model)s",
        "e.embedding_dim = %(embedding_dim)s",
    ]

    params: dict[str, Any] = {
        "model": model,
        "embedding_dim": embedding_dim,
        "query_embedding": vector_literal(query_embedding),
        "limit": limit,
    }

    if dataset_id is not None:
        where_parts.append("d.dataset_id = %(dataset_id)s")
        params["dataset_id"] = dataset_id

    where_clause = "WHERE " + " AND ".join(where_parts)

    sql = f"""
        SELECT
            d.series_id,
            d.dataset_id,
            datasets.title AS dataset_title,
            d.indicator_code,
            d.indicator_name,
            d.primary_text,
            d.embedding_text,
            d.keyword_text,
            e.embedding <=> %(query_embedding)s::vector AS cosine_distance
        FROM series_embeddings e
        JOIN series_search_documents d
            ON d.series_id = e.series_id
        JOIN datasets
            ON datasets.dataset_id = d.dataset_id
        {where_clause}
        ORDER BY
            e.embedding <=> %(query_embedding)s::vector
        LIMIT %(limit)s;
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return list(cur.fetchall())


def print_results(query: str, rows: list[dict[str, Any]], show_text: bool) -> None:
    print(f"Query: {query}")
    print(f"Results: {len(rows)}")
    print()

    for index, row in enumerate(rows, start=1):
        distance = float(row["cosine_distance"])
        similarity = 1.0 - distance

        print("=" * 80)
        print(f"{index}. {row['dataset_id']} / {row['indicator_code']}")
        print("-" * 80)
        print(f"Primary text: {row['primary_text']}")
        print(f"Dataset: {row['dataset_title']}")
        print(f"Cosine distance: {distance:.4f}")
        print(f"Approx similarity: {similarity:.4f}")

        if row.get("indicator_name"):
            print()
            print("Official indicator name:")
            print(row["indicator_name"])

        if show_text:
            print()
            print("Embedding text:")
            print(row["embedding_text"])

            print()
            print("Keyword text:")
            print(row["keyword_text"])

        print()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run semantic search over stored series embeddings."
    )
    parser.add_argument(
        "query",
        help="Natural-language search query.",
    )
    parser.add_argument(
        "--dataset-id",
        default=None,
        help="Optional dataset filter, for example NAG_GBR.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of results.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Embedding model ID. Default: {DEFAULT_MODEL}.",
    )
    parser.add_argument(
        "--embedding-dim",
        type=int,
        default=DEFAULT_DIMENSION,
        help=f"Embedding dimensionality. Default: {DEFAULT_DIMENSION}.",
    )
    parser.add_argument(
        "--show-text",
        action="store_true",
        help="Print embedding_text and keyword_text for each result.",
    )

    args = parser.parse_args()

    require_environment()

    client = genai.Client()

    query_embedding = embed_query(
        client=client,
        query=args.query,
        model=args.model,
        output_dimensionality=args.embedding_dim,
    )

    rows = semantic_search(
        query_embedding=query_embedding,
        model=args.model,
        embedding_dim=args.embedding_dim,
        limit=args.limit,
        dataset_id=args.dataset_id,
    )

    print_results(
        query=args.query,
        rows=rows,
        show_text=args.show_text,
    )

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        raise SystemExit(1)
