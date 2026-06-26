from __future__ import annotations

import argparse
import os
import sys
import time
from collections.abc import Sequence
from typing import Any

from google import genai
from google.genai.types import EmbedContentConfig

from app.services.postgres import get_connection


DEFAULT_MODEL = "gemini-embedding-2"
DEFAULT_DIMENSION = 768
DEFAULT_TASK_TYPE = "RETRIEVAL_DOCUMENT"


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
    """
    Convert a Python sequence of floats into pgvector literal syntax.

    Example:
      [0.1, 0.2, 0.3]
      -> "[0.1,0.2,0.3]"
    """
    return "[" + ",".join(str(float(value)) for value in values) + "]"


def fetch_documents_to_embed(
    dataset_id: str | None,
    model: str,
    embedding_dim: int,
    limit: int,
    force: bool,
) -> list[dict[str, Any]]:
    where_parts: list[str] = []
    params: dict[str, Any] = {
        "model": model,
        "embedding_dim": embedding_dim,
        "limit": limit,
    }

    if dataset_id is not None:
        where_parts.append("d.dataset_id = %(dataset_id)s")
        params["dataset_id"] = dataset_id

    if not force:
        where_parts.append(
            """
            (
                e.series_id IS NULL
                OR e.document_content_hash <> d.content_hash
                OR e.document_version <> d.document_version
            )
            """
        )

    where_clause = ""

    if where_parts:
        where_clause = "WHERE " + " AND ".join(where_parts)

    sql = f"""
        SELECT
            d.series_id,
            d.dataset_id,
            d.indicator_code,
            d.primary_text,
            d.embedding_text,
            d.document_version,
            d.content_hash
        FROM series_search_documents d
        LEFT JOIN series_embeddings e
            ON e.series_id = d.series_id
            AND e.embedding_model = %(model)s
            AND e.embedding_dim = %(embedding_dim)s
        {where_clause}
        ORDER BY
            d.dataset_id,
            d.indicator_code NULLS LAST,
            d.series_id
        LIMIT %(limit)s;
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return list(cur.fetchall())


def embed_text(
    client: genai.Client,
    model: str,
    text: str,
    title: str | None,
    output_dimensionality: int,
) -> list[float]:
    response = client.models.embed_content(
        model=model,
        contents=[text],
        config=EmbedContentConfig(
            task_type=DEFAULT_TASK_TYPE,
            output_dimensionality=output_dimensionality,
            title=title,
        ),
    )

    if not response.embeddings:
        raise RuntimeError("Gemini returned no embeddings.")

    values = response.embeddings[0].values

    if values is None:
        raise RuntimeError("Gemini returned an embedding with no values.")

    return [float(value) for value in values]


def upsert_embedding(
    document: dict[str, Any],
    model: str,
    embedding_dim: int,
    embedding_values: Sequence[float],
) -> None:
    if len(embedding_values) != embedding_dim:
        raise ValueError(
            f"Expected {embedding_dim} embedding values, "
            f"got {len(embedding_values)}."
        )

    sql = """
        INSERT INTO series_embeddings (
            series_id,
            embedding_model,
            embedding_dim,
            document_version,
            document_content_hash,
            embedding,
            updated_at
        )
        VALUES (
            %(series_id)s,
            %(embedding_model)s,
            %(embedding_dim)s,
            %(document_version)s,
            %(document_content_hash)s,
            %(embedding)s::vector,
            now()
        )
        ON CONFLICT (series_id, embedding_model, embedding_dim)
        DO UPDATE SET
            document_version = EXCLUDED.document_version,
            document_content_hash = EXCLUDED.document_content_hash,
            embedding = EXCLUDED.embedding,
            updated_at = now();
    """

    params = {
        "series_id": document["series_id"],
        "embedding_model": model,
        "embedding_dim": embedding_dim,
        "document_version": document["document_version"],
        "document_content_hash": document["content_hash"],
        "embedding": vector_literal(embedding_values),
    }

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)


def count_embeddings(model: str, embedding_dim: int) -> int:
    sql = """
        SELECT COUNT(*) AS count
        FROM series_embeddings
        WHERE embedding_model = %s
          AND embedding_dim = %s;
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (model, embedding_dim))
            row = cur.fetchone()
            return int(row["count"])


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate Gemini embeddings for stored series search documents."
    )
    parser.add_argument(
        "--dataset-id",
        default=None,
        help="Optional dataset ID to process, for example NAG_GBR.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Maximum number of documents to process.",
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
        help=f"Embedding output dimensionality. Default: {DEFAULT_DIMENSION}.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-embed documents even when an up-to-date embedding already exists.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List documents that would be embedded, but do not call Gemini.",
    )
    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=0.2,
        help="Delay between Gemini calls.",
    )

    args = parser.parse_args()

    require_environment()

    documents = fetch_documents_to_embed(
        dataset_id=args.dataset_id,
        model=args.model,
        embedding_dim=args.embedding_dim,
        limit=args.limit,
        force=args.force,
    )

    print(f"Found {len(documents)} documents to embed.")
    print(f"Model: {args.model}")
    print(f"Embedding dimension: {args.embedding_dim}")

    if documents:
        print()
        print("First document:")
        print(f"  dataset_id: {documents[0]['dataset_id']}")
        print(f"  indicator_code: {documents[0]['indicator_code']}")
        print(f"  primary_text: {documents[0]['primary_text']}")
        print(f"  content_hash: {documents[0]['content_hash']}")

    if args.dry_run:
        print()
        print("Dry run: not calling Gemini and not writing embeddings.")
        return 0

    client = genai.Client()

    for index, document in enumerate(documents, start=1):
        print(
            f"[{index}/{len(documents)}] Embedding "
            f"{document['dataset_id']} / {document['indicator_code']}"
        )

        values = embed_text(
            client=client,
            model=args.model,
            text=document["embedding_text"],
            title=document["primary_text"],
            output_dimensionality=args.embedding_dim,
        )

        upsert_embedding(
            document=document,
            model=args.model,
            embedding_dim=args.embedding_dim,
            embedding_values=values,
        )

        if args.sleep_seconds > 0:
            time.sleep(args.sleep_seconds)

    total = count_embeddings(args.model, args.embedding_dim)

    print()
    print(f"Upserted {len(documents)} embeddings.")
    print(f"Total stored embeddings for {args.model}/{args.embedding_dim}: {total}")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        raise SystemExit(1)
