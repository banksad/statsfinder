from __future__ import annotations

import argparse
from typing import Any

from psycopg.types.json import Jsonb

from app.services.postgres import get_connection
from scripts.semantic_search_documents import (
    build_search_document,
    fetch_series_rows,
)


def upsert_search_documents(documents: list[dict[str, Any]]) -> None:
    sql = """
        INSERT INTO series_search_documents (
            series_id,
            dataset_id,
            series_key,
            indicator_code,
            indicator_name,
            document_version,
            primary_text,
            embedding_text,
            keyword_text,
            parsed_metadata,
            content_hash,
            updated_at
        )
        VALUES (
            %(series_id)s,
            %(dataset_id)s,
            %(series_key)s,
            %(indicator_code)s,
            %(indicator_name)s,
            %(document_version)s,
            %(primary_text)s,
            %(embedding_text)s,
            %(keyword_text)s,
            %(parsed_metadata)s,
            %(content_hash)s,
            now()
        )
        ON CONFLICT (series_id)
        DO UPDATE SET
            dataset_id = EXCLUDED.dataset_id,
            series_key = EXCLUDED.series_key,
            indicator_code = EXCLUDED.indicator_code,
            indicator_name = EXCLUDED.indicator_name,
            document_version = EXCLUDED.document_version,
            primary_text = EXCLUDED.primary_text,
            embedding_text = EXCLUDED.embedding_text,
            keyword_text = EXCLUDED.keyword_text,
            parsed_metadata = EXCLUDED.parsed_metadata,
            content_hash = EXCLUDED.content_hash,
            updated_at = now();
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            for document in documents:
                params = {
                    **document,
                    "parsed_metadata": Jsonb(document["parsed_metadata"]),
                }
                cur.execute(sql, params)


def count_search_documents() -> int:
    sql = "SELECT COUNT(*) AS count FROM series_search_documents;"

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            row = cur.fetchone()
            return int(row["count"])


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build and store semantic-search documents for series metadata."
    )
    parser.add_argument(
        "--dataset-id",
        default=None,
        help="Optional dataset ID to process, for example NAG_GBR.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional maximum number of series to process.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build documents but do not write them to the database.",
    )

    args = parser.parse_args()

    rows = fetch_series_rows(
        dataset_id=args.dataset_id,
        limit=args.limit,
    )

    documents = [build_search_document(row) for row in rows]

    print(f"Built {len(documents)} search documents.")

    if documents:
        print()
        print("First document:")
        print(f"  dataset_id: {documents[0]['dataset_id']}")
        print(f"  indicator_code: {documents[0]['indicator_code']}")
        print(f"  primary_text: {documents[0]['primary_text']}")
        print(f"  content_hash: {documents[0]['content_hash']}")

    if args.dry_run:
        print()
        print("Dry run: not writing to database.")
        return 0

    upsert_search_documents(documents)

    total = count_search_documents()

    print()
    print(f"Upserted {len(documents)} search documents.")
    print(f"Total stored search documents: {total}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
