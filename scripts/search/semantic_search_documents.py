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
    "general government operations": "GGO",
    "general government debt": "GGD",
    "special drawing rights": "SDR",
}


GGO_LABEL_DROP_PARTS = {
    "government and public sector finance",
    "fiscal",
    "2014 manual",
    "national currency",
}


GGD_LABEL_DROP_PARTS = {
    "government and public sector finance",
    "stocks in assets and liabilities",
    "fiscal",
    "assets and liabilities",
    "classification of the stocks of assets and liabilities",
    "2001 manual",
    "national currency",
}


def clean_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def normalise_ggd_label_part(part: str) -> str:
    """
    Normalise GGD label fragments without inventing new concepts.

    The official labels are useful but verbose. We keep source-backed wording,
    while removing typography/noise that hurts display and semantic matching.
    """
    part = clean_whitespace(part)
    part = part.replace("Debt  by", "Debt by")
    part = part.replace("Debt (at Nominal Value)", "Debt at Nominal Value")
    part = part.replace("Domestic Debt (at Nominal Value)", "Domestic Debt at Nominal Value")
    part = part.replace("Foreign Debt (at Nominal Value)", "Foreign Debt at Nominal Value")
    return clean_whitespace(part)


def dedupe_preserve_order(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()

    for value in values:
        cleaned = clean_whitespace(value)
        key = cleaned.lower()

        if key and key not in seen:
            deduped.append(cleaned)
            seen.add(key)

    return deduped


def order_general_government_first(parts: list[str]) -> list[str]:
    """
    Put General Government first when it exists in the official label.

    This gives stable user-facing labels such as:
      General Government, Liabilities, Loans
    rather than:
      Liabilities, General Government, Loans
    """
    has_general_government = any(
        clean_whitespace(part).lower() == "general government"
        for part in parts
    )

    ordered_parts: list[str] = []

    if has_general_government:
        ordered_parts.append("General Government")

    for part in parts:
        if clean_whitespace(part).lower() == "general government":
            continue

        ordered_parts.append(part)

    return dedupe_preserve_order(ordered_parts)


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

    ordered_parts = order_general_government_first(cleaned_parts)

    if not ordered_parts:
        return None

    return ", ".join(ordered_parts)


def split_ggd_indicator_label(indicator_name: str) -> list[str]:
    """
    Split a GGD official SDMX indicator label into source-backed hierarchy parts.

    GGD labels are generally comma-separated, but include bracketed methodology
    and occasional spacing noise such as "Debt  by Currency". We normalise those
    without interpreting the compact indicator code.
    """
    label = clean_whitespace(indicator_name)

    # Convert bracketed methodology into a comma-separated part.
    label = re.sub(r"\s*\[([^\]]+)\]", r", \1", label)

    raw_parts = [
        normalise_ggd_label_part(part)
        for part in label.split(",")
        if clean_whitespace(part)
    ]

    return dedupe_preserve_order(raw_parts)


def build_ggd_primary_text(indicator_name: str) -> str | None:
    """
    Build a source-backed, human-friendly GGD series name from the official
    SDMX indicator label.

    Examples:
      General Government, Debt at Nominal Value
      General Government, Liabilities, Loans
      General Government, Debt by Currency, Debt denominated in domestic currency
    """
    parts = split_ggd_indicator_label(indicator_name)

    cleaned_parts = [
        part
        for part in parts
        if clean_whitespace(part).lower() not in GGD_LABEL_DROP_PARTS
    ]

    ordered_parts = order_general_government_first(cleaned_parts)

    if not ordered_parts:
        return None

    return ", ".join(ordered_parts)


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


def apply_dataset_specific_label_cleanup(
    dataset_id: str,
    indicator_name: str,
    parsed_metadata: dict[str, Any],
) -> tuple[str | None, list[str] | None, dict[str, Any]]:
    """
    Return dataset-specific primary text and hierarchy when a dataset needs
    official-label cleanup.

    This keeps generic datasets generic while allowing known verbose IMF/SDMX
    labels to be made usable for search, browse, and Chat.
    """
    if dataset_id == "GGO_GBR":
        ggo_parts = split_ggo_indicator_label(indicator_name)
        ggo_primary_text = build_ggo_primary_text(indicator_name)

        if not ggo_primary_text:
            return None, None, parsed_metadata

        ggo_hierarchy_raw = [
            part
            for part in ggo_parts
            if clean_whitespace(part).lower() not in GGO_LABEL_DROP_PARTS
        ]
        ggo_hierarchy = order_general_government_first(ggo_hierarchy_raw)

        parsed_metadata["parsed_topic"] = ggo_primary_text
        parsed_metadata["hierarchy"] = ggo_hierarchy
        parsed_metadata["ggo_label_parts"] = ggo_parts

        return ggo_primary_text, ggo_hierarchy, parsed_metadata

    if dataset_id == "GGD_GBR":
        ggd_parts = split_ggd_indicator_label(indicator_name)
        ggd_primary_text = build_ggd_primary_text(indicator_name)

        if not ggd_primary_text:
            return None, None, parsed_metadata

        ggd_hierarchy_raw = [
            part
            for part in ggd_parts
            if clean_whitespace(part).lower() not in GGD_LABEL_DROP_PARTS
        ]
        ggd_hierarchy = order_general_government_first(ggd_hierarchy_raw)

        parsed_metadata["parsed_topic"] = ggd_primary_text
        parsed_metadata["hierarchy"] = ggd_hierarchy
        parsed_metadata["ggd_label_parts"] = ggd_parts

        return ggd_primary_text, ggd_hierarchy, parsed_metadata

    return None, None, parsed_metadata


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

    if indicator_name:
        cleaned_primary_text, cleaned_hierarchy, parsed_metadata = (
            apply_dataset_specific_label_cleanup(
                dataset_id=dataset_id,
                indicator_name=indicator_name,
                parsed_metadata=parsed_metadata,
            )
        )

        if cleaned_primary_text:
            primary_text = cleaned_primary_text
            topic = cleaned_primary_text

        if cleaned_hierarchy is not None:
            hierarchy = cleaned_hierarchy

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
