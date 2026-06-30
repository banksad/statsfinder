from __future__ import annotations

import argparse
import urllib.request
from pathlib import Path

from scripts.common.dataset_registry import get_dataset_config, load_dataset_registry
from scripts.common.structure_registry import get_structure_config


USER_AGENT = "StatsFinder/0.1 (+https://statsfinder.uk)"


def _download(url: str, dest: Path, timeout: int = 180) -> int:
    """
    Download ``url`` to ``dest``, returning the number of bytes written.

    Uses the standard library only so this can run anywhere the rest of the
    pipeline runs, without adding a request-library dependency.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/xml,text/xml,*/*",
        },
    )

    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = response.read()

    dest.write_bytes(data)
    return len(data)


def fetch_dataset_source(dataset_id: str) -> Path:
    """
    Download one registered dataset's official SDMX source file to its
    configured ``raw_file_path``.
    """
    config = get_dataset_config(dataset_id)
    dest = Path(config["raw_file_path"])

    size = _download(config["source_url"], dest)
    print(f"  {dataset_id}: {size:,} bytes -> {dest}")
    return dest


def fetch_structure_source(structure_ref: str) -> Path:
    """
    Download one registered SDMX structure (DSD with codelists) to its
    configured ``raw_file_path``. These files are large, so allow more time.
    """
    config = get_structure_config(structure_ref)
    dest = Path(config["raw_file_path"])

    size = _download(config["source_url"], dest, timeout=300)
    print(f"  {structure_ref}: {size:,} bytes -> {dest}")
    return dest


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download official source files into data/raw and data/structure."
    )
    parser.add_argument(
        "dataset_id",
        nargs="?",
        help="A single dataset id to fetch, for example CPI_GBR.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Fetch every registered dataset.",
    )
    parser.add_argument(
        "--structure",
        metavar="STRUCTURE_REF",
        help="Also fetch this structure, for example IMF_ECOFIN_DSD_1_0.",
    )

    args = parser.parse_args()

    if not (args.all or args.dataset_id or args.structure):
        parser.error("provide a dataset_id, --all, or --structure")

    if args.all:
        print("Fetching all dataset sources...")
        for dataset in load_dataset_registry():
            fetch_dataset_source(dataset["dataset_id"])
    elif args.dataset_id:
        print("Fetching dataset source...")
        fetch_dataset_source(args.dataset_id)

    if args.structure:
        print("Fetching structure source...")
        fetch_structure_source(args.structure)


if __name__ == "__main__":
    main()
