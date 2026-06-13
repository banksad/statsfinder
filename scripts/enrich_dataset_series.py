from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scripts.dataset_registry import get_dataset_config


CODELIST_LOOKUP_PATH = Path("data/processed/ecofin_codelist_lookup.json")


DIMENSION_TO_CODELIST = {
    "DATA_DOMAIN": "CL_DATADOMAIN",
    "REF_AREA": "CL_REF_AREA",
    "INDICATOR": "CL_INDICATOR",
    "COUNTERPART_AREA": "CL_COUNTERPART_AREA",
    "FREQ": "CL_FREQ",
    "UNIT_MULT": "CL_UNIT_MULT",
}


SPECIAL_CODE_LABELS = {
    "_Z": "Not applicable or not specified",
}


def load_json(path: Path) -> Any:
    """
    Load JSON from disk.
    """
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def write_json(path: Path, data: Any) -> None:
    """
    Write JSON to disk.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)


def get_code_items(codelist: dict[str, Any]) -> dict[str, Any]:
    """
    Return the code dictionary from a codelist object.

    This is intentionally tolerant because our parsed codelist JSON may evolve.
    """
    for key in ("codes", "items", "code_items"):
        value = codelist.get(key)

        if isinstance(value, dict):
            return value

    return codelist


def lookup_code_label(
    codelist_lookup: dict[str, Any],
    codelist_id: str | None,
    code: str,
) -> dict[str, Any]:
    """
    Look up one code in the parsed codelist lookup.
    """
    if codelist_id is None:
        return {
            "code": code,
            "name": SPECIAL_CODE_LABELS.get(code),
            "found": False,
            "reason": "no_dimension_to_codelist_mapping",
            "codelist_id": None,
            "description": None,
        }

    codelist = codelist_lookup.get(codelist_id)

    if not isinstance(codelist, dict):
        return {
            "code": code,
            "name": SPECIAL_CODE_LABELS.get(code),
            "found": False,
            "reason": "codelist_not_found",
            "codelist_id": codelist_id,
            "description": None,
        }

    code_items = get_code_items(codelist)
    item = code_items.get(code)

    if not isinstance(item, dict):
        return {
            "code": code,
            "name": SPECIAL_CODE_LABELS.get(code),
            "found": False,
            "reason": "code_not_found",
            "codelist_id": codelist_id,
            "description": None,
        }

    return {
        "urn": item.get("urn"),
        "code": code,
        "name": item.get("name"),
        "found": True,
        "codelist_id": codelist_id,
        "description": item.get("description"),
    }


def build_dimension_labels(
    dimension_values: dict[str, str],
    codelist_lookup: dict[str, Any],
) -> dict[str, Any]:
    """
    Resolve each dimension code to a label where possible.
    """
    labels = {}

    for dimension_name, code in dimension_values.items():
        codelist_id = DIMENSION_TO_CODELIST.get(dimension_name)

        labels[dimension_name] = lookup_code_label(
            codelist_lookup=codelist_lookup,
            codelist_id=codelist_id,
            code=code,
        )

    return labels


def build_search_text(
    dataset_config: dict[str, Any],
    series_record: dict[str, Any],
    dimension_labels: dict[str, Any],
) -> str:
    """
    Build simple searchable text from official metadata.

    This is not authoritative metadata. It is a search helper derived from
    official codes and labels.
    """
    parts = [
        dataset_config["dataset_id"],
        dataset_config["title"],
        series_record["series_key"],
    ]

    for dimension_name, code in series_record["dimension_values"].items():
        parts.append(dimension_name)
        parts.append(code)

    for label_info in dimension_labels.values():
        name = label_info.get("name")
        description = label_info.get("description")

        if name:
            parts.append(name)

        if description:
            parts.append(description)

    return " ".join(parts)


def enrich_series_records(dataset_id: str) -> list[dict[str, Any]]:
    """
    Enrich one registered dataset's raw series records.
    """
    dataset_config = get_dataset_config(dataset_id)

    raw_series_path = Path(dataset_config["series_raw_json_path"])
    codelist_lookup = load_json(CODELIST_LOOKUP_PATH)
    raw_series_records = load_json(raw_series_path)

    enriched_records = []

    for record in raw_series_records:
        dimension_labels = build_dimension_labels(
            dimension_values=record["dimension_values"],
            codelist_lookup=codelist_lookup,
        )

        enriched_record = {
            **record,
            "dimension_labels": dimension_labels,
            "search_text": build_search_text(
                dataset_config=dataset_config,
                series_record=record,
                dimension_labels=dimension_labels,
            ),
        }

        enriched_records.append(enriched_record)

    return enriched_records


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Enrich parsed SDMX series records with codelist labels."
    )
    parser.add_argument(
        "dataset_id",
        help="Dataset ID from config/datasets.json, for example CPI_GBR.",
    )

    args = parser.parse_args()
    dataset_config = get_dataset_config(args.dataset_id)

    output_path = Path(dataset_config["series_json_path"])

    print(f"Enriching dataset: {args.dataset_id}")

    enriched_records = enrich_series_records(args.dataset_id)
    write_json(output_path, enriched_records)

    print(f"Enriched series written: {output_path}")
    print(f"Series count: {len(enriched_records)}")

    if enriched_records:
        print()
        print("First enriched series:")
        print(json.dumps(enriched_records[0], indent=2))


if __name__ == "__main__":
    main()
