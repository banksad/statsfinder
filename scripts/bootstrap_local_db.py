from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import psycopg

from app.services.postgres import get_dsn


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = PROJECT_ROOT / "sql" / "001_create_core_tables.sql"
DATASETS_CONFIG_PATH = PROJECT_ROOT / "config" / "datasets.json"


def apply_schema(dsn: str) -> None:
    """
    Apply the core SQL schema.

    The SQL uses CREATE TABLE IF NOT EXISTS, so this is safe to run repeatedly.
    """
    print(f"Applying schema from {SCHEMA_PATH}")

    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(schema_sql)

    print("Schema applied.")


def get_dataset_ids() -> list[str]:
    """
    Read dataset IDs from config/datasets.json.
    """
    with DATASETS_CONFIG_PATH.open(encoding="utf-8") as file:
        datasets = json.load(file)

    return [dataset["dataset_id"] for dataset in datasets]


def load_dataset(dataset_id: str, dsn: str) -> None:
    """
    Run the existing generic dataset loader.

    We pass ONS_SDMX_DB_DSN into the subprocess explicitly so the loader uses
    the same database connection as this bootstrap script.
    """
    print(f"Loading dataset: {dataset_id}")

    env = os.environ.copy()
    env["ONS_SDMX_DB_DSN"] = dsn

    subprocess.run(
        [sys.executable, "-m", "scripts.load_dataset_to_postgres", dataset_id],
        cwd=PROJECT_ROOT,
        env=env,
        check=True,
    )

    print(f"Loaded dataset: {dataset_id}")


def print_counts(dsn: str) -> None:
    """
    Print simple database counts as a smoke test.
    """
    queries = {
        "datasets": "SELECT COUNT(*) FROM datasets",
        "series": "SELECT COUNT(*) FROM series",
        "observations": "SELECT COUNT(*) FROM observations",
    }

    print("\nDatabase counts:")

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            for label, query in queries.items():
                cur.execute(query)
                count = cur.fetchone()[0]
                print(f"- {label}: {count}")


def main() -> None:
    dsn = get_dsn()

    print("Bootstrapping local database")
    print(f"Project root: {PROJECT_ROOT}")
    print("Database DSN: loaded from ONS_SDMX_DB_DSN")

    apply_schema(dsn)

    dataset_ids = get_dataset_ids()

    for dataset_id in dataset_ids:
        load_dataset(dataset_id, dsn)

    print_counts(dsn)

    print("\nBootstrap complete.")


if __name__ == "__main__":
    main()
