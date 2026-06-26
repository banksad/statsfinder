from __future__ import annotations

import argparse
import json

from scripts.search.semantic_search_documents import (
    build_search_document,
    fetch_series_rows,
)


def print_readable_document(document: dict) -> None:
    print("=" * 80)
    print(f"{document['dataset_id']} / {document['indicator_code']}")
    print("-" * 80)

    print("Primary text:")
    print(document["primary_text"])
    print()

    print("Embedding text:")
    print(document["embedding_text"])
    print()

    print("Keyword text:")
    print(document["keyword_text"])
    print()

    print("Parsed metadata:")
    print(json.dumps(document["parsed_metadata"], indent=2, ensure_ascii=False))
    print()

    print("Content hash:")
    print(document["content_hash"])
    print()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Preview indicator-first semantic-search documents for series metadata."
    )
    parser.add_argument(
        "--dataset-id",
        default=None,
        help="Optional dataset ID to preview, for example NAG_GBR.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Number of series to preview.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print full JSON records instead of readable text blocks.",
    )

    args = parser.parse_args()

    rows = fetch_series_rows(
        dataset_id=args.dataset_id,
        limit=args.limit,
    )

    documents = [build_search_document(row) for row in rows]

    if args.json:
        print(json.dumps(documents, indent=2, ensure_ascii=False))
        return 0

    for document in documents:
        print_readable_document(document)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
