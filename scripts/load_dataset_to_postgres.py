from __future__ import annotations

import argparse
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from scripts.dataset_registry import get_dataset_config
from app.services.postgres import get_dsn


def load_json(path: Path) -> Any:
    """
    Load JSON from disk.
    """
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def parse_obs_value(value: str | None) -> Decimal | None:
    """
    Convert an observation value string to Decimal.

    We use Decimal rather than float to avoid accidental rounding surprises.
    """
    if value is None:
        return None

    return Decimal(value)


def insert_dataset(cur, dataset_config: dict[str, Any]) -> None:
    """
    Insert or update the dataset metadata row.
    """
    sql = """
        INSERT INTO datasets (
            dataset_id,
            title,
            data_domain_code,
            data_domain_label,
            source_url,
            documentation_url,
            metadata_url,
            structure_ref,
            raw_file_path
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (dataset_id)
        DO UPDATE SET
            title = EXCLUDED.title,
            data_domain_code = EXCLUDED.data_domain_code,
            data_domain_label = EXCLUDED.data_domain_label,
            source_url = EXCLUDED.source_url,
            documentation_url = EXCLUDED.documentation_url,
            metadata_url = EXCLUDED.metadata_url,
            structure_ref = EXCLUDED.structure_ref,
            raw_file_path = EXCLUDED.raw_file_path;
    """

    cur.execute(
        sql,
        (
            dataset_config["dataset_id"],
            dataset_config["title"],
            dataset_config["data_domain_code"],
            dataset_config["data_domain_label"],
            dataset_config["source_url"],
            dataset_config.get("documentation_url"),
            dataset_config.get("metadata_url"),
            dataset_config["structure_ref"],
            dataset_config["raw_file_path"],
        ),
    )


def insert_series_records(
    cur,
    dataset_id: str,
    series_records: list[dict[str, Any]],
) -> dict[str, int]:
    """
    Insert or update series records.

    Returns a mapping:

        series_key -> database series_id
    """
    series_key_to_id: dict[str, int] = {}

    sql = """
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
    """

    for record in series_records:
        if record["dataset_id"] != dataset_id:
            raise ValueError(
                f"Series record dataset_id mismatch: expected {dataset_id}, "
                f"got {record['dataset_id']}"
            )

        cur.execute(
            sql,
            (
                record["dataset_id"],
                record["series_key"],
                Jsonb(record["dimension_values"]),
                Jsonb(record.get("dimension_labels")),
                record.get("search_text"),
            ),
        )

        series_id = cur.fetchone()[0]
        series_key_to_id[record["series_key"]] = series_id

    return series_key_to_id


def insert_observation_records(
    cur,
    dataset_id: str,
    observation_records: list[dict[str, Any]],
    series_key_to_id: dict[str, int],
) -> None:
    """
    Insert or update observation records.
    """
    sql = """
        INSERT INTO observations (
            series_id,
            time_period,
            obs_value
        )
        VALUES (%s, %s, %s)
        ON CONFLICT (series_id, time_period)
        DO UPDATE SET
            obs_value = EXCLUDED.obs_value;
    """

    for record in observation_records:
        if record["dataset_id"] != dataset_id:
            raise ValueError(
                f"Observation record dataset_id mismatch: expected {dataset_id}, "
                f"got {record['dataset_id']}"
            )

        series_key = record["series_key"]
        series_id = series_key_to_id.get(series_key)

        if series_id is None:
            raise ValueError(f"No series_id found for series_key: {series_key}")

        cur.execute(
            sql,
            (
                series_id,
                record["time_period"],
                parse_obs_value(record["obs_value"]),
            ),
        )


def print_row_counts(cur, dataset_id: str) -> None:
    """
    Print useful database row counts.
    """
    print()
    print("Dataset-specific row counts:")

    cur.execute(
        """
        SELECT COUNT(*)
        FROM series
        WHERE dataset_id = %s;
        """,
        (dataset_id,),
    )
    print(f"  series for {dataset_id}: {cur.fetchone()[0]}")

    cur.execute(
        """
        SELECT COUNT(*)
        FROM observations o
        JOIN series s
            ON s.series_id = o.series_id
        WHERE s.dataset_id = %s;
        """,
        (dataset_id,),
    )
    print(f"  observations for {dataset_id}: {cur.fetchone()[0]}")

    print()
    print("Total database row counts:")

    for table_name in ["datasets", "series", "observations"]:
        cur.execute(f"SELECT COUNT(*) FROM {table_name};")
        count = cur.fetchone()[0]
        print(f"  {table_name}: {count}")


def load_dataset_to_postgres(dataset_id: str) -> None:
    """
    Load one registered dataset into Postgres.
    """
    dataset_config = get_dataset_config(dataset_id)

    series_json_path = Path(dataset_config["series_json_path"])
    observations_json_path = Path(dataset_config["observations_json_path"])

    print(f"Loading dataset: {dataset_id}")
    print(f"Series JSON: {series_json_path}")
    print(f"Observations JSON: {observations_json_path}")

    series_records = load_json(series_json_path)
    observation_records = load_json(observations_json_path)

    print()
    print(f"Series records found: {len(series_records)}")
    print(f"Observation records found: {len(observation_records)}")

    print()
    print("Connecting to Postgres...")

    with psycopg.connect(get_dsn()) as conn:
        with conn.cursor() as cur:
            print("Inserting dataset...")
            insert_dataset(cur, dataset_config)

            print("Inserting series...")
            series_key_to_id = insert_series_records(
                cur,
                dataset_id,
                series_records,
            )

            print("Inserting observations...")
            insert_observation_records(
                cur,
                dataset_id,
                observation_records,
                series_key_to_id,
            )

            print_row_counts(cur, dataset_id)

        conn.commit()

    print()
    print("Load complete.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load one registered dataset into Postgres."
    )
    parser.add_argument(
        "dataset_id",
        help="Dataset ID from config/datasets.json, for example CPI_GBR.",
    )

    args = parser.parse_args()
    load_dataset_to_postgres(args.dataset_id)


if __name__ == "__main__":
    main()
