"""
Refresh every registered dataset end to end, in one command.

This is the single entry point intended for automated ingest (for example a
Cloud Run Job triggered by Cloud Scheduler). It is declarative: it reads the
dataset and structure registries and runs

    apply schema
      -> fetch structure DSD        (unless --skip-fetch)
      -> build codelist lookup
      -> for each dataset:
           fetch source             (unless --skip-fetch)
           parse  -> series/observation JSON
           enrich -> codelist labels + search_text
           load   -> upsert into Postgres

Loading is idempotent (upserts + CREATE TABLE IF NOT EXISTS), so the job is safe
to run on a schedule and safe to retry. Each dataset is isolated: one bad source
fails only that dataset, and the run reports which succeeded and which failed,
exiting non-zero if any failed so a scheduler can alert.

Semantic-search embeddings are intentionally out of scope here; they need Gemini
and are refreshed by the separate embedding scripts.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.services.postgres import get_dsn
from scripts.common.dataset_registry import get_dataset_config, load_dataset_registry
from scripts.common.structure_registry import get_structure_config
from scripts.db.bootstrap_local_db import apply_schema
from scripts.ingest.fetch_sources import fetch_dataset_source, fetch_structure_source
from scripts.ingest.parse_dataset_to_records import parse_sdmx_dataset, write_json
from scripts.ingest.enrich_dataset_series import enrich_series_records
from scripts.ingest.load_dataset_to_postgres import load_dataset_to_postgres
from scripts.inspect.parse_codelists import build_codelist_lookup


DEFAULT_STRUCTURE_REF = "IMF_ECOFIN_DSD_1_0"


def _parse(dataset_id: str) -> None:
    config = get_dataset_config(dataset_id)
    series_records, observation_records = parse_sdmx_dataset(dataset_id)
    write_json(Path(config["series_raw_json_path"]), series_records)
    write_json(Path(config["observations_json_path"]), observation_records)


def _enrich(dataset_id: str) -> None:
    config = get_dataset_config(dataset_id)
    enriched_records = enrich_series_records(dataset_id)
    write_json(Path(config["series_json_path"]), enriched_records)


def refresh_all(
    only: list[str] | None = None,
    skip_fetch: bool = False,
    structure_ref: str = DEFAULT_STRUCTURE_REF,
) -> int:
    """
    Run the full refresh. Returns the number of failed datasets.
    """
    dsn = get_dsn()

    print("== apply schema ==")
    apply_schema(dsn)

    print("\n== structure / codelists ==")
    structure = get_structure_config(structure_ref)
    if not skip_fetch:
        fetch_structure_source(structure_ref)
    build_codelist_lookup(
        Path(structure["raw_file_path"]),
        Path(structure["codelist_lookup_path"]),
    )
    print(f"  codelist lookup ready: {structure['codelist_lookup_path']}")

    datasets = load_dataset_registry()
    if only:
        wanted = set(only)
        datasets = [d for d in datasets if d["dataset_id"] in wanted]
        missing = wanted - {d["dataset_id"] for d in datasets}
        if missing:
            raise SystemExit(f"unknown dataset id(s): {', '.join(sorted(missing))}")

    print(f"\n== refreshing {len(datasets)} dataset(s) ==")
    succeeded: list[str] = []
    failed: list[tuple[str, str]] = []

    for dataset in datasets:
        dataset_id = dataset["dataset_id"]
        print(f"\n-- {dataset_id} --")
        try:
            if not skip_fetch:
                fetch_dataset_source(dataset_id)
            _parse(dataset_id)
            _enrich(dataset_id)
            load_dataset_to_postgres(dataset_id)
            succeeded.append(dataset_id)
        except Exception as exc:  # isolate one dataset's failure from the rest
            print(f"  ERROR {dataset_id}: {exc!r}", file=sys.stderr)
            failed.append((dataset_id, repr(exc)))

    print("\n== summary ==")
    print(f"  succeeded ({len(succeeded)}): {', '.join(succeeded) or '-'}")
    print(f"  failed ({len(failed)}): " + (", ".join(f"{i} {e}" for i, e in failed) or "-"))

    return len(failed)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch, parse, enrich, and load every registered dataset."
    )
    parser.add_argument(
        "--only",
        help="Comma-separated dataset ids to refresh instead of all.",
    )
    parser.add_argument(
        "--skip-fetch",
        action="store_true",
        help="Use source files already on disk instead of downloading.",
    )
    parser.add_argument(
        "--structure-ref",
        default=DEFAULT_STRUCTURE_REF,
        help="Structure to use for codelist enrichment.",
    )

    args = parser.parse_args()
    only = [s.strip() for s in args.only.split(",")] if args.only else None

    failures = refresh_all(
        only=only,
        skip_fetch=args.skip_fetch,
        structure_ref=args.structure_ref,
    )

    if failures:
        sys.exit(1)

    print("\nRefresh complete.")


if __name__ == "__main__":
    main()
