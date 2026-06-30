from pathlib import Path
import json
import xml.etree.ElementTree as ET

from scripts.common.structure_registry import get_structure_config


DEFAULT_STRUCTURE_REF = "IMF_ECOFIN_DSD_1_0"

XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"


def local_name(tag: str) -> str:
    """
    Convert an XML tag with a namespace into its local name.

    Example:
      {http://example.com/ns}Codelist -> Codelist
      Codelist -> Codelist
    """
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def get_text_by_local_name(element: ET.Element, child_name: str) -> str | None:
    """
    Find the first English child element with a given local name.

    For example, inside a Code element, find:
      <com:Name xml:lang="en">Quarterly</com:Name>

    If no English element exists, return the first matching element.
    """
    matches = [
        child
        for child in element
        if local_name(child.tag) == child_name
    ]

    if not matches:
        return None

    for child in matches:
        if child.attrib.get(XML_LANG) == "en":
            return child.text

    return matches[0].text


def parse_codelists(dsd_path: Path) -> dict:
    """
    Parse SDMX codelists from a full DSD XML file.

    Returns a nested dictionary:

    {
      "CL_FREQ": {
        "Q": {
          "name": "Quarterly",
          "description": null,
          "urn": "..."
        }
      }
    }
    """
    tree = ET.parse(dsd_path)
    root = tree.getroot()

    lookup = {}

    for element in root.iter():
        if local_name(element.tag) != "Codelist":
            continue

        codelist_id = element.attrib.get("id")
        agency_id = element.attrib.get("agencyID")
        version = element.attrib.get("version")

        if not codelist_id:
            continue

        lookup[codelist_id] = {
            "_meta": {
                "agency_id": agency_id,
                "version": version,
                "urn": element.attrib.get("urn"),
            },
            "codes": {},
        }

        for child in element:
            if local_name(child.tag) != "Code":
                continue

            code_id = child.attrib.get("id")
            if not code_id:
                continue

            name = get_text_by_local_name(child, "Name")
            description = get_text_by_local_name(child, "Description")

            lookup[codelist_id]["codes"][code_id] = {
                "name": name,
                "description": description,
                "urn": child.attrib.get("urn"),
            }

    return lookup


def build_codelist_lookup(dsd_path: Path, output_path: Path) -> dict:
    """
    Parse the DSD codelists and write the lookup JSON, returning the lookup.

    This is the reusable entry point used by the ingest pipeline. ``main`` wraps
    it with the structure registry and some illustrative prints.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    lookup = parse_codelists(dsd_path)

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(lookup, file, indent=2, ensure_ascii=False)

    return lookup


def _print_example(lookup: dict, codelist_id: str, code: str) -> None:
    """
    Print one example lookup, tolerating codes that are not present.
    """
    item = lookup.get(codelist_id, {}).get("codes", {}).get(code)
    print(f"\n{codelist_id} / {code}")

    if item is None:
        print("  (not present in this DSD)")
        return

    print(f"  Name: {item['name']}")
    print(f"  Description: {item['description']}")


def main() -> None:
    structure = get_structure_config(DEFAULT_STRUCTURE_REF)
    dsd_path = Path(structure["raw_file_path"])
    output_path = Path(structure["codelist_lookup_path"])

    lookup = build_codelist_lookup(dsd_path, output_path)

    print("Parsed codelists successfully.")
    print(f"Number of codelists: {len(lookup)}")
    print(f"Wrote lookup to: {output_path}")

    print("\nExample lookups:")
    _print_example(lookup, "CL_INDICATOR", "NGDP_SA_XDC")
    _print_example(lookup, "CL_FREQ", "Q")


if __name__ == "__main__":
    main()
