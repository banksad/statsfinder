from __future__ import annotations

import json
import os
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg
from psycopg.types.json import Jsonb


DB_DSN = os.environ.get(
    "ONS_SDMX_DB_DSN",
    "postgresql://ons_sdmx_user:ons_sdmx_password@localhost:5433/ons_sdmx",
)

SERIES_JSON_PATH = Path("data/processed/nag_series_enriched.json")
OBSERVATIONS_JSON_PATH = Path("data/processed/nag_observation_records.json")

DATASET_ID = "NAG_GBR"
DATASET_TITLE = "UK National Accounts"
SOURCE_URL = "https://static.ons.gov.uk/imf/NAG_GBR.xml"
STRUCTURE_REF = "IMF_ECOFIN_DSD_1_0"
RAW_FILE_PATH = "data/raw/NAG_GBR.xml"


def load_json(path: Path) -> list[dict[str, Any]]:
    """Load a JSON file that contains a list of objects."""
    if not path.exists():
        raise FileNotFoundError(f"Could not find expected file: {path}")

    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, list):
        raise ValueError(f"Expected {path} to contain a JSON list.")

    return data


def parse_obs_value(value: Any) -> Decimal | None:
    """Convert an observation value into a Decimal, preserving exactness."""
    if value is None or value == "":
        return None

    return Decimal(str(value))


def insert_dataset(cur: psycopg.Cursor) -> None:
    """Insert or update the one dataset record for NAG_GBR."""
    cur.execute(
        """
        INSERT INTO datasets (
            dataset_id,
            title,
            source_url,
            structure_ref,
            raw_file_path
        )
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (dataset_id)
        DO UPDATE SET
            title = EXCLUDED.title,
            source_url = EXCLUDED.source_url,
            structure_ref = EXCLUDED.structure_ref,
            raw_file_path = EXCLUDED.raw_file_path;
        """,
        (
            DATASET_ID,
            DATASET_TITLE,
            SOURCE_URL,
            STRUCTURE_REF,
            RAW_FILE_PATH,
        ),
    )


def insert_series_records(
    cur: psycopg.Cursor,
    series_records: list[dict[str, Any]],
) -> dict[str, int]:
    """
    Insert series rows and return a lookup from series_key to database series_id.

    The observations JSON refers to series_key, but the observations table stores
    series_id. So we need this mapping.
    """
    series_key_to_id: dict[str, int] = {}

    for record in series_records:
        series_key = record["series_key"]
        dimension_values = record["dimension_values"]
        dimension_labels = record.get("dimension_labels")
        search_text = record.get("search_text")

        if not isinstance(dimension_values, dict):
            raise ValueError(f"dimension_values must be a dict for {series_key}")

        cur.execute(
            """
            INSERT INTO series (
                dataset_id,
                series_key,
                dimension_values,
                dimension_labels,
                search_text
            )
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (dataset_id, series_key)
            DO UPDATE SET
                dimension_values = EXCLUDED.dimension_values,
                dimension_labels = EXCLUDED.dimension_labels,
                search_text = EXCLUDED.search_text
            RETURNING series_id;
            """,
            (
                DATASET_ID,
                series_key,
                Jsonb(dimension_values),
                Jsonb(dimension_labels) if dimension_labels is not None else None,
                search_text,
            ),
        )

        result = cur.fetchone()

        if result is None:
            raise RuntimeError(f"Could not get series_id for {series_key}")

        series_id = result[0]
        series_key_to_id[series_key] = series_id

    return series_key_to_id


def insert_observation_records(
    cur: psycopg.Cursor,
    observation_records: list[dict[str, Any]],
    series_key_to_id: dict[str, int],
) -> None:
    """Insert observation rows linked to their parent series."""
    for record in observation_records:
        series_key = record["series_key"]

        if series_key not in series_key_to_id:
            raise KeyError(f"Observation refers to unknown series_key: {series_key}")

        series_id = series_key_to_id[series_key]
        time_period = record["time_period"]
        obs_value = parse_obs_value(record.get("obs_value"))

        cur.execute(
            """
            INSERT INTO observations (
                series_id,
                time_period,
                obs_value
            )
            VALUES (%s, %s, %s)
            ON CONFLICT (series_id, time_period)
            DO UPDATE SET
                obs_value = EXCLUDED.obs_value;
            """,
            (
                series_id,
                time_period,
                obs_value,
            ),
        )


def print_row_counts(cur: psycopg.Cursor) -> None:
    """Print row counts after loading."""
    cur.execute(
        """
        SELECT 'datasets' AS table_name, COUNT(*) FROM datasets
        UNION ALL
        SELECT 'series', COUNT(*) FROM series
        UNION ALL
        SELECT 'observations', COUNT(*) FROM observations
        UNION ALL
        SELECT 'codelists', COUNT(*) FROM codelists
        UNION ALL
        SELECT 'codelist_items', COUNT(*) FROM codelist_items;
        """
    )

    print("\nRow counts:")
    for table_name, count in cur.fetchall():
        print(f"  {table_name}: {count}")


def main() -> None:
    print("Loading processed JSON files...")
    series_records = load_json(SERIES_JSON_PATH)
    observation_records = load_json(OBSERVATIONS_JSON_PATH)

    print(f"Series records found: {len(series_records)}")
    print(f"Observation records found: {len(observation_records)}")

    print("\nConnecting to Postgres...")
    with psycopg.connect(DB_DSN) as conn:
        with conn.cursor() as cur:
            print("Inserting dataset...")
            insert_dataset(cur)

            print("Inserting series...")
            series_key_to_id = insert_series_records(cur, series_records)

            print("Inserting observations...")
            insert_observation_records(cur, observation_records, series_key_to_id)

            print_row_counts(cur)

    print("\nLoad complete.")


if __name__ == "__main__":
    main()
