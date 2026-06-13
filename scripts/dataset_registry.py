from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REGISTRY_PATH = Path("config/datasets.json")


def load_dataset_registry() -> list[dict[str, Any]]:
    """
    Load the local dataset registry.

    The registry describes datasets that this prototype knows how to
    download, parse, load, and expose.
    """
    with REGISTRY_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def get_dataset_config(dataset_id: str) -> dict[str, Any]:
    """
    Return one dataset config by dataset_id.
    """
    datasets = load_dataset_registry()

    for dataset in datasets:
        if dataset["dataset_id"] == dataset_id:
            return dataset

    raise ValueError(f"Dataset not found in registry: {dataset_id}")
