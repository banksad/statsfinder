from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET


BASE_DIR = Path(__file__).resolve().parents[2]
DATASETS_PATH = BASE_DIR / "config" / "datasets.json"


STRUCTURE_NAMES = [
    "CategoryScheme",
    "Category",
    "Hierarchy",
    "HierarchicalCodeList",
    "Codelist",
    "Codelists",
    "ConceptScheme",
    "Concepts",
    "DataStructure",
    "DataStructures",
    "Dataflow",
    "Dataflows",
    "DataflowRef",
    "DataStructureRef",
    "Structure",
    "Structures",
    "Series",
    "Obs",
]


def local_name(tag: str) -> str:
    """
    Strip an XML namespace from a tag name.

    Example:
        {http://example.com}Codelist -> Codelist
    """
    if "}" in tag:
        return tag.rsplit("}", 1)[1]

    return tag


def inspect_xml(xml_path: Path) -> tuple[dict[str, int], Counter[str]]:
    counts = {name: 0 for name in STRUCTURE_NAMES}
    all_tags: Counter[str] = Counter()

    for _event, element in ET.iterparse(xml_path, events=("end",)):
        name = local_name(element.tag)
        all_tags[name] += 1

        if name in counts:
            counts[name] += 1

        element.clear()

    return counts, all_tags


def main() -> None:
    datasets = json.loads(DATASETS_PATH.read_text())

    for dataset in datasets:
        dataset_id = dataset["dataset_id"]
        raw_file_path = BASE_DIR / dataset["raw_file_path"]

        print(dataset_id)
        print(f"  raw file: {dataset['raw_file_path']}")

        if not raw_file_path.exists():
            print("  status: missing raw file")
            print()
            continue

        counts, all_tags = inspect_xml(raw_file_path)

        print("  selected structure counts:")
        for name in STRUCTURE_NAMES:
            print(f"    {name}: {counts[name]}")

        print()
        print("  most common XML element names:")
        for name, count in all_tags.most_common(25):
            print(f"    {name}: {count}")

        print()


if __name__ == "__main__":
    main()
