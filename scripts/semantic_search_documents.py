from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from app.services.postgres import get_connection


DOCUMENT_VERSION = "semantic-document-v1"


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

GGO_LABEL_DROP_PARTS = {
    "government and public sector finance",
    "fiscal",
    "2014 manual",
    "national currency",
}


def split_ggo_indicator_label(indicator_name: str) -> list[str]:
    """
    Split a GGO official SDMX indicator label into hierarchy parts.

    Some labels use:
      "Revenue  General Government [2014 Manual]"

    rather than:
      "Revenue, General Government, 2014 Manual"

    so we normalise bracketed methodology and the missing comma around
    General Government.
    """
    label = clean_whitespace(indicator_name)

    # Convert bracketed methodology into a comma-separated part.
    label = re.sub(r"\s*\[([^\]]+)\]", r", \1", label)

    raw_parts = [
        clean_whitespace(part)
        for part in label.split(",")
        if clean_whitespace(part)
    ]

    parts: list[str] = []

    for part in raw_parts:
        if part != "General Government" and "General Government" in part:
            before = clean_whitespace(part.replace("General Government", ""))

            if before:
                parts.append(before)

            parts.append("General Government")
        else:
            parts.append(part)

    return dedupe_preserve_order(parts)


def build_ggo_primary_text(indicator_name: str) -> str | None:
    """
    Build a source-backed, human-friendly GGO series name from the official
    SDMX indicator label.

    This deliberately avoids parsing the compact indicator code. It keeps the
    useful hierarchy and removes only dataset-wide prefixes and trailing
    qualifiers.
    """
    parts = split_ggo_indicator_label(indicator_name)

    cleaned_parts = [
        part
        for part in parts
        if clean_whitespace(part).lower() not in GGO_LABEL_DROP_PARTS
    ]

    has_general_government = any(
        clean_whitespace(part).lower() == "general government"
        for part in cleaned_parts
    )

    ordered_parts: list[str] = []

    if has_general_government:
        ordered_parts.append("General Government")

    for part in cleaned_parts:
        if clean_whitespace(part).lower() == "general government":
            continue

        ordered_parts.append(part)

    ordered_parts = dedupe_preserve_order(ordered_parts)

    if not ordered_parts:
        return None

    return ", ".join(ordered_parts)


def clean_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def split_indicator_name(indicator_name: str | None) -> list[str]:
    if not indicator_name:
        return []

    parts = [clean_whitespace(part) for part in indicator_name.split(",")]
    return [part for part in parts if part]


def lower_key(value: str) -> str:
    return clean_whitespace(value).lower()


def classify_parts(parts: list[str]) -> dict[str, Any]:
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
    if not value:
        return

    cleaned = normalise_keyword_token(value)

    if not cleaned:
        return

    tokens.extend(cleaned.split())


def controlled_abbreviations_for_text(text: str) -> list[str]:
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


def build_content_hash(
    document_version: str,
    primary_text: str,
    embedding_text: str,
    keyword_text: str,
    parsed_metadata: dict[str, Any],
) -> str:
    payload = {
        "document_version": document_version,
        "primary_text": primary_text,
        "embedding_text": embedding_text,
        "keyword_text": keyword_text,
        "parsed_metadata": parsed_metadata,
    }

    encoded = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
    ).encode("utf-8")

    return hashlib.sha256(encoded).hexdigest()


def build_search_document(row: dict[str, Any]) -> dict[str, Any]:
    dataset_id = row.get("dataset_id", "")
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

    parsed_metadata = {
        "parsed_topic": topic,
        "hierarchy": hierarchy,
        "measure_type": measure_type,
        "seasonal_adjustment": seasonal_adjustment,
        "unit": unit,
        "base_period": base_period,
        "unit_multiplier": unit_multiplier,
    }

    if dataset_id == "GGO_GBR" and indicator_name:
        ggo_parts = split_ggo_indicator_label(indicator_name)
        ggo_primary_text = build_ggo_primary_text(indicator_name)

        if ggo_primary_text:
            primary_text = ggo_primary_text

            ggo_hierarchy_raw = [
                part
                for part in ggo_parts
                if clean_whitespace(part).lower() not in GGO_LABEL_DROP_PARTS
            ]

            has_general_government = any(
                clean_whitespace(part).lower() == "general government"
                for part in ggo_hierarchy_raw
            )

            ggo_hierarchy: list[str] = []

            if has_general_government:
                ggo_hierarchy.append("General Government")

            for part in ggo_hierarchy_raw:
                if clean_whitespace(part).lower() == "general government":
                    continue

                ggo_hierarchy.append(part)

            ggo_hierarchy = dedupe_preserve_order(ggo_hierarchy)

            topic = ggo_primary_text
            hierarchy = ggo_hierarchy

            parsed_metadata["parsed_topic"] = ggo_primary_text
            parsed_metadata["hierarchy"] = ggo_hierarchy
            parsed_metadata["ggo_label_parts"] = ggo_parts

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

    content_hash = build_content_hash(
        document_version=DOCUMENT_VERSION,
        primary_text=primary_text,
        embedding_text=embedding_text,
        keyword_text=keyword_text,
        parsed_metadata=parsed_metadata,
    )

    return {
        "series_id": row["series_id"],
        "dataset_id": row["dataset_id"],
        "series_key": row["series_key"],
        "indicator_code": row.get("indicator_code"),
        "indicator_name": indicator_name,
        "document_version": DOCUMENT_VERSION,
        "primary_text": primary_text,
        "embedding_text": embedding_text,
        "keyword_text": keyword_text,
        "parsed_metadata": parsed_metadata,
        "content_hash": content_hash,
    }


def fetch_series_rows(
    dataset_id: str | None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    where_clause = ""
    params: list[Any] = []

    if dataset_id is not None:
        where_clause = "WHERE s.dataset_id = %s"
        params.append(dataset_id)

    limit_clause = ""

    if limit is not None:
        limit_clause = "LIMIT %s"
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
        {limit_clause};
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return list(cur.fetchall())
