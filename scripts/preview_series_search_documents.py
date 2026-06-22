from __future__ import annotations

import argparse
import json
import re
from typing import Any

from scripts.query_postgres import get_connection


QUALIFIER_PHRASES = {
    "nominal": "measure_type",
    "real": "measure_type",
    "seasonally adjusted": "seasonal_adjustment",
    "seasonally adjusted.": "seasonal_adjustment",
    "not seasonally adjusted": "seasonal_adjustment",
    "national currency": "unit",
    "percentage change": "unit",
    "index": "unit",
}


CONTROLLED_ABBREVIATIONS = {
    "gross domestic product": "GDP",
    "consumer price index": "CPI",
    "consumer price indices": "CPI",
    "balance of payments": "BOP",
}


def clean_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def split_indicator_name(indicator_name: str | None) -> list[str]:
    """
    Split the official indicator label into comma-separated parts.

    SDMX labels often encode a hierarchy using commas. We keep that hierarchy,
    but later separate obvious qualifiers such as nominal, real, unit, and
    seasonal adjustment.
    """
    if not indicator_name:
        return []

    parts = [
        clean_whitespace(part)
        for part in indicator_name.split(",")
    ]

    return [part for part in parts if part]


def lower_key(value: str) -> str:
    return clean_whitespace(value).lower()


def classify_parts(parts: list[str]) -> dict[str, Any]:
    """
    Split a comma-separated SDMX-style label into hierarchy and qualifiers.

    This is deliberately conservative. Anything we do not recognise stays in
    the hierarchy. That is safer than over-cleaning official metadata.
    """
    hierarchy: list[str] = []
    measure_type: str | None = None
    seasonal_adjustment: str | None = None
    unit: str | None = None

    for part in parts:
        key = lower_key(part)
        classification = QUALIFIER_PHRASES.get(key)

        if classification == "measure_type":
            measure_type = key
        elif classification == "seasonal_adjustment":
            seasonal_adjustment = key.rstrip(".")
        elif classification == "unit":
            unit = key
        else:
            hierarchy.append(part)

    return {
        "hierarchy": hierarchy,
        "measure_type": measure_type,
        "seasonal_adjustment": seasonal_adjustment,
        "unit": unit,
    }


def final_topic_from_hierarchy(hierarchy: list[str]) -> str | None:
    """
    The last hierarchy part is usually the most specific indicator concept.

    Example:
      National Accounts > Expenditure > GDP > Exports of Goods and Services

    Primary topic:
      Exports of Goods and Services
    """
    if not hierarchy:
        return None

    return hierarchy[-1]


def safe_dimension_value(row: dict[str, Any], key: str) -> str | None:
    values = row.get("dimension_values") or {}
    value = values.get(key)

    if value in (None, "", "_Z"):
        return None

    return str(value)


def normalise_keyword_token(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9_]+", " ", value)
    return clean_whitespace(value)


def add_keyword_tokens(tokens: list[str], value: str | None) -> None:
    """
    Add useful keyword tokens from a phrase without trying to become a thesaurus.

    This is for future hybrid/exact search, not for semantic expansion.
    """
    if not value:
        return

    cleaned = normalise_keyword_token(value)

    if not cleaned:
        return

    tokens.extend(cleaned.split())


def controlled_abbreviations_for_text(text: str) -> list[str]:
    """
    Add a few stable official-statistics abbreviations.

    This is intentionally tiny. It is not a hand-curated synonym system.
    """
    text_lower = text.lower()
    abbreviations: list[str] = []

    for phrase, abbreviation in CONTROLLED_ABBREVIATIONS.items():
        if phrase in text_lower:
            abbreviations.append(abbreviation)

    return abbreviations


def dedupe_preserve_order(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()

    for value in values:
        key = value.lower()

        if key and key not in seen:
            deduped.append(value)
            seen.add(key)

    return deduped


def build_keyword_text(
    row: dict[str, Any],
    hierarchy: list[str],
    topic: str | None,
    measure_type: str | None,
    seasonal_adjustment: str | None,
    unit: str | None,
) -> str:
    """
    Build keyword-oriented text for later hybrid search.

    This is different from embedding_text:
    - embedding_text should be readable, compact, and high-signal
    - keyword_text should preserve exact terms, codes, and useful tokens
    """
    tokens: list[str] = []

    if row.get("indicator_code"):
        tokens.append(str(row["indicator_code"]))

    add_keyword_tokens(tokens, topic)
    add_keyword_tokens(tokens, row.get("indicator_name"))
    add_keyword_tokens(tokens, row.get("dataset_title"))
    add_keyword_tokens(tokens, row.get("data_domain_label"))

    for part in hierarchy:
        add_keyword_tokens(tokens, part)

    add_keyword_tokens(tokens, row.get("frequency_code"))
    add_keyword_tokens(tokens, row.get("frequency_name"))
    add_keyword_tokens(tokens, measure_type)
    add_keyword_tokens(tokens, seasonal_adjustment)
    add_keyword_tokens(tokens, unit)

    full_text = " ".join(
        [
            str(row.get("dataset_title") or ""),
            str(row.get("data_domain_label") or ""),
            str(row.get("indicator_name") or ""),
        ]
    )

    tokens.extend(controlled_abbreviations_for_text(full_text))

    return " ".join(dedupe_preserve_order(tokens))


def build_embedding_text(
    row: dict[str, Any],
    hierarchy: list[str],
    topic: str | None,
    measure_type: str | None,
    seasonal_adjustment: str | None,
    unit: str | None,
    base_period: str | None,
    unit_multiplier: str | None,
) -> str:
    """
    Build the text we expect to send to Gemini embeddings.

    Design choice:
      Put the indicator concept first.
      Keep repeated provenance out.
      Keep enough context to disambiguate the series.
    """
    dataset_title = row.get("dataset_title") or row.get("dataset_id")
    domain_label = row.get("data_domain_label")
    primary = topic or row.get("indicator_name") or row.get("indicator_code") or row["series_key"]

    lines = [
        f"{primary}.",
        "",
        f"This series measures {str(primary).lower()} in {dataset_title}.",
    ]

    if hierarchy:
        lines.append(f"Topic path: {' > '.join(hierarchy)}.")

    lines.append(f"Dataset: {dataset_title}.")

    if domain_label:
        lines.append(f"Domain: {domain_label}.")

    if row.get("frequency_name") or row.get("frequency_code"):
        lines.append(
            f"Frequency: {str(row.get('frequency_name') or row.get('frequency_code')).lower()}."
        )

    if measure_type:
        lines.append(f"Measure type: {measure_type}.")

    if seasonal_adjustment:
        lines.append(f"Seasonal adjustment: {seasonal_adjustment}.")

    if unit:
        lines.append(f"Unit: {unit}.")

    if base_period:
        lines.append(f"Base period: {base_period}.")

    if unit_multiplier:
        lines.append(f"Unit multiplier: {unit_multiplier}.")

    return "\n".join(lines)


def build_search_document(row: dict[str, Any]) -> dict[str, Any]:
    indicator_name = row.get("indicator_name")
    parts = split_indicator_name(indicator_name)
    classified = classify_parts(parts)

    hierarchy = classified["hierarchy"]
    topic = final_topic_from_hierarchy(hierarchy)

    measure_type = classified["measure_type"]
    seasonal_adjustment = classified["seasonal_adjustment"]
    unit = classified["unit"]

    base_period = safe_dimension_value(row, "BASE_PER")
    unit_multiplier = safe_dimension_value(row, "UNIT_MULT")

    primary_text = topic or indicator_name or row.get("indicator_code") or row["series_key"]

    embedding_text = build_embedding_text(
        row=row,
        hierarchy=hierarchy,
        topic=topic,
        measure_type=measure_type,
        seasonal_adjustment=seasonal_adjustment,
        unit=unit,
        base_period=base_period,
        unit_multiplier=unit_multiplier,
    )

    keyword_text = build_keyword_text(
        row=row,
        hierarchy=hierarchy,
        topic=topic,
        measure_type=measure_type,
        seasonal_adjustment=seasonal_adjustment,
        unit=unit,
    )

    parsed_metadata = {
        "parsed_topic": topic,
        "hierarchy": hierarchy,
        "measure_type": measure_type,
        "seasonal_adjustment": seasonal_adjustment,
        "unit": unit,
        "base_period": base_period,
        "unit_multiplier": unit_multiplier,
    }

    return {
        "series_id": row["series_id"],
        "dataset_id": row["dataset_id"],
        "series_key": row["series_key"],
        "indicator_code": row.get("indicator_code"),
        "indicator_name": indicator_name,
        "primary_text": primary_text,
        "embedding_text": embedding_text,
        "keyword_text": keyword_text,
        "parsed_metadata": parsed_metadata,
    }


def fetch_series_rows(dataset_id: str | None, limit: int) -> list[dict[str, Any]]:
    where_clause = ""
    params: list[Any] = []

    if dataset_id is not None:
        where_clause = "WHERE s.dataset_id = %s"
        params.append(dataset_id)

    params.append(limit)

    sql = f"""
        SELECT
            s.series_id,
            s.dataset_id,
            d.title AS dataset_title,
            d.data_domain_label,
            s.series_key,
            s.dimension_values,
            s.dimension_labels,
            s.dimension_values ->> 'INDICATOR' AS indicator_code,
            s.dimension_labels -> 'INDICATOR' ->> 'name' AS indicator_name,
            s.dimension_values ->> 'FREQ' AS frequency_code,
            s.dimension_labels -> 'FREQ' ->> 'name' AS frequency_name
        FROM series s
        JOIN datasets d
            ON d.dataset_id = s.dataset_id
        {where_clause}
        ORDER BY
            s.dataset_id,
            LOWER(
                COALESCE(
                    s.dimension_labels -> 'INDICATOR' ->> 'name',
                    s.dimension_values ->> 'INDICATOR',
                    s.series_key
                )
            )
        LIMIT %s;
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return list(cur.fetchall())


def print_readable_document(document: dict[str, Any]) -> None:
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
