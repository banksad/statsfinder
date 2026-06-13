from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from scripts.dataset_registry import get_dataset_config


def local_name(tag: str) -> str:
    """
    Return the local part of an XML tag.

    Example:
        {namespace}Series -> Series
        Series -> Series
    """
    if "}" in tag:
        return tag.split("}", 1)[1]

    return tag


def build_series_key(dimension_values: dict[str, str]) -> str:
    """
    Build a stable series key from dimension values.

    Sorting keys means the same dimensions always produce the same string,
    regardless of XML attribute order.
    """
    parts = []

    for key in sorted(dimension_values):
        parts.append(f"{key}={dimension_values[key]}")

    return "|".join(parts)


def parse_sdmx_dataset(dataset_id: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Parse one registered SDMX XML dataset into series and observation records.
    """
    dataset_config = get_dataset_config(dataset_id)

    xml_path = Path(dataset_config["raw_file_path"])
    source_url = dataset_config["source_url"]
    structure_ref = dataset_config["structure_ref"]

    tree = ET.parse(xml_path)
    root = tree.getroot()

    series_records: list[dict[str, Any]] = []
    observation_records: list[dict[str, Any]] = []

    for element in root.iter():
        if local_name(element.tag) != "Series":
            continue

        dimension_values = dict(element.attrib)
        series_key = build_series_key(dimension_values)

        series_records.append(
            {
                "dataset_id": dataset_id,
                "source_url": source_url,
                "structure_ref": structure_ref,
                "series_key": series_key,
                "dimension_values": dimension_values,
            }
        )

        for child in element:
            if local_name(child.tag) != "Obs":
                continue

            observation_records.append(
                {
                    "dataset_id": dataset_id,
                    "series_key": series_key,
                    "time_period": child.attrib.get("TIME_PERIOD"),
                    "obs_value": child.attrib.get("OBS_VALUE"),
                }
            )

    return series_records, observation_records


def write_json(path: Path, records: list[dict[str, Any]]) -> None:
    """
    Write JSON records to disk.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        json.dump(records, file, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Parse a registered SDMX XML dataset into JSON records."
    )
    parser.add_argument(
        "dataset_id",
        help="Dataset ID from config/datasets.json, for example CPI_GBR.",
    )

    args = parser.parse_args()
    dataset_config = get_dataset_config(args.dataset_id)

    series_output_path = Path(dataset_config["series_raw_json_path"])
    observations_output_path = Path(dataset_config["observations_json_path"])

    print(f"Parsing dataset: {args.dataset_id}")
    print(f"Raw XML: {dataset_config['raw_file_path']}")

    series_records, observation_records = parse_sdmx_dataset(args.dataset_id)

    write_json(series_output_path, series_records)
    write_json(observations_output_path, observation_records)

    print()
    print(f"Series records written: {series_output_path}")
    print(f"Observation records written: {observations_output_path}")
    print()
    print(f"Series count: {len(series_records)}")
    print(f"Observation count: {len(observation_records)}")

    if series_records:
        print()
        print("First series key:")
        print(series_records[0]["series_key"])


if __name__ == "__main__":
    main()
