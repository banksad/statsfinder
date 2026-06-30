from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REGISTRY_PATH = Path("config/structures.json")


def load_structure_registry() -> list[dict[str, Any]]:
    """
    Load the local SDMX structure registry.

    Structures describe the shared SDMX artefacts (data structure definitions and
    their codelists) that datasets reference via their ``structure_ref``. Keeping
    the structure source URL and on-disk paths here means the ingest pipeline is
    fully declarative rather than hard-coding URLs in scripts.
    """
    with REGISTRY_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def get_structure_config(structure_ref: str) -> dict[str, Any]:
    """
    Return one structure config by structure_ref.
    """
    for structure in load_structure_registry():
        if structure["structure_ref"] == structure_ref:
            return structure

    raise ValueError(f"Structure not found in registry: {structure_ref}")
