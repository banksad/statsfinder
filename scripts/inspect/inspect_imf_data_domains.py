from __future__ import annotations

import json
from pathlib import Path
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[2]
DATASETS_PATH = BASE_DIR / "config" / "datasets.json"

CL_DATADOMAIN_URL = (
    "https://sdmxcentral.imf.org/sdmx/v2/structure/"
    "codelist/IMF/CL_DATADOMAIN/1.0"
)


def local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]

    return tag


def fetch_xml(url: str) -> bytes:
    request = Request(
        url,
        headers={
            "User-Agent": "StatsFinder/0.1",
            "Accept": "application/xml,text/xml,*/*",
        },
    )

    with urlopen(request, timeout=30) as response:
        return response.read()


def parse_codelist(xml_bytes: bytes) -> dict[str, str]:
    root = ET.fromstring(xml_bytes)
    codes: dict[str, str] = {}

    for element in root.iter():
        if local_name(element.tag) != "Code":
            continue

        code_id = element.attrib.get("id")

        if not code_id:
            continue

        name = None

        for child in element:
            if local_name(child.tag) == "Name" and child.text:
                name = child.text.strip()
                break

        codes[code_id] = name or ""

    return codes


def dataset_domain_code(dataset: dict[str, Any]) -> str:
    configured_code = dataset.get("data_domain_code")

    if configured_code:
        return configured_code

    return dataset["dataset_id"].rsplit("_", 1)[0]


def main() -> None:
    datasets = json.loads(DATASETS_PATH.read_text())

    print("Fetching IMF CL_DATADOMAIN...")
    xml_bytes = fetch_xml(CL_DATADOMAIN_URL)
    domain_codes = parse_codelist(xml_bytes)

    print(f"Loaded {len(domain_codes)} data-domain codes")
    print()

    for dataset in datasets:
        dataset_id = dataset["dataset_id"]
        domain_code = dataset_domain_code(dataset)
        domain_label = domain_codes.get(domain_code)

        print(dataset_id)
        print(f"  data domain code: {domain_code}")

        if domain_label:
            print(f"  data domain label: {domain_label}")
        else:
            print("  data domain label: not found")

        print()


if __name__ == "__main__":
    main()
