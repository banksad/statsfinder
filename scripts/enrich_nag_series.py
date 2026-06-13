from pathlib import Path
import json


SERIES_INPUT_PATH = Path("data/processed/nag_series_records.json")
CODELIST_LOOKUP_PATH = Path("data/processed/ecofin_codelist_lookup.json")
OUTPUT_PATH = Path("data/processed/nag_series_enriched.json")


DIMENSION_TO_CODELIST = {
    "DATA_DOMAIN": "CL_DATADOMAIN",
    "REF_AREA": "CL_REF_AREA",
    "INDICATOR": "CL_INDICATOR",
    "COUNTERPART_AREA": "CL_COUNTERPART_AREA",
    "FREQ": "CL_FREQ",
    "UNIT_MULT": "CL_UNIT_MULT",
    # BASE_PER is a little different: it may be a base year like 2008
    # or a special value such as _Z. We will handle it manually for now.
}


SPECIAL_CODE_LABELS = {
    "_Z": "Not applicable or not specified",
}


def load_json(path: Path):
    """
    Load a JSON file and return the parsed Python object.
    """
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def lookup_code_label(
    codelist_lookup: dict,
    codelist_id: str,
    code: str,
) -> dict:
    """
    Look up a code in a codelist.

    Returns a small dictionary with:
      - code
      - codelist_id
      - name
      - description
      - found

    We return structured information instead of just the label because
    that gives us better debugging and database-ready metadata.
    """
    codelist = codelist_lookup.get(codelist_id)

    if codelist is None:
        return {
            "code": code,
            "codelist_id": codelist_id,
            "name": SPECIAL_CODE_LABELS.get(code),
            "description": None,
            "found": False,
            "reason": "codelist_not_found",
        }

    code_record = codelist.get("codes", {}).get(code)

    if code_record is None:
        return {
            "code": code,
            "codelist_id": codelist_id,
            "name": SPECIAL_CODE_LABELS.get(code),
            "description": None,
            "found": False,
            "reason": "code_not_found",
        }

    return {
        "code": code,
        "codelist_id": codelist_id,
        "name": code_record.get("name"),
        "description": code_record.get("description"),
        "urn": code_record.get("urn"),
        "found": True,
    }


def enrich_dimension_values(
    dimension_values: dict[str, str],
    codelist_lookup: dict,
) -> dict:
    """
    Convert dimension codes into labelled dimension metadata.

    Example input:
      {"FREQ": "Q"}

    Example output:
      {
        "FREQ": {
          "code": "Q",
          "codelist_id": "CL_FREQ",
          "name": "Quarterly",
          "description": "To be used for data collected or disseminated every quarter.",
          "found": true
        }
      }
    """
    enriched = {}

    for dimension_name, code in dimension_values.items():
        codelist_id = DIMENSION_TO_CODELIST.get(dimension_name)

        if codelist_id is None:
            enriched[dimension_name] = {
                "code": code,
                "codelist_id": None,
                "name": SPECIAL_CODE_LABELS.get(code),
                "description": None,
                "found": False,
                "reason": "no_dimension_to_codelist_mapping",
            }
            continue

        enriched[dimension_name] = lookup_code_label(
            codelist_lookup=codelist_lookup,
            codelist_id=codelist_id,
            code=code,
        )

    return enriched


def build_search_text(series_record: dict, enriched_dimensions: dict) -> str:
    """
    Build simple search text for semantic/keyword search.

    This is not LLM-generated yet. It is deterministic text built from
    official metadata.
    """
    parts = [
        series_record.get("dataset_id"),
        series_record.get("structure_ref"),
    ]

    for dimension_name, dimension_info in enriched_dimensions.items():
        code = dimension_info.get("code")
        name = dimension_info.get("name")
        description = dimension_info.get("description")

        parts.append(dimension_name)
        parts.append(code)
        parts.append(name)
        parts.append(description)

    return " ".join(
        str(part)
        for part in parts
        if part not in (None, "")
    )


def enrich_series_records(series_records: list[dict], codelist_lookup: dict) -> list[dict]:
    """
    Add official codelist labels to every series record.
    """
    enriched_records = []

    for series_record in series_records:
        dimension_values = series_record["dimension_values"]

        enriched_dimensions = enrich_dimension_values(
            dimension_values=dimension_values,
            codelist_lookup=codelist_lookup,
        )

        enriched_record = {
            **series_record,
            "dimension_labels": enriched_dimensions,
            "search_text": build_search_text(series_record, enriched_dimensions),
        }

        enriched_records.append(enriched_record)

    return enriched_records


def print_example(enriched_records: list[dict]) -> None:
    """
    Print a readable example for the first enriched series.
    """
    first = enriched_records[0]

    print("\nFirst enriched series")
    print("---------------------")
    print(f"Dataset ID: {first['dataset_id']}")
    print(f"Series key: {first['series_key']}")

    print("\nDimensions:")
    for dimension_name, info in first["dimension_labels"].items():
        print(f"  {dimension_name}")
        print(f"    Code: {info.get('code')}")
        print(f"    Codelist: {info.get('codelist_id')}")
        print(f"    Name: {info.get('name')}")
        print(f"    Found: {info.get('found')}")

    print("\nSearch text preview:")
    print(first["search_text"][:1000])


def main() -> None:
    series_records = load_json(SERIES_INPUT_PATH)
    codelist_lookup = load_json(CODELIST_LOOKUP_PATH)

    enriched_records = enrich_series_records(
        series_records=series_records,
        codelist_lookup=codelist_lookup,
    )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT_PATH.open("w", encoding="utf-8") as file:
        json.dump(enriched_records, file, indent=2, ensure_ascii=False)

    print("Enriched series records successfully.")
    print(f"Input series records: {len(series_records)}")
    print(f"Output enriched records: {len(enriched_records)}")
    print(f"Wrote enriched records to: {OUTPUT_PATH}")

    print_example(enriched_records)


if __name__ == "__main__":
    main()
