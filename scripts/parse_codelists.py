from pathlib import Path
import json
import xml.etree.ElementTree as ET


DSD_PATH = Path("data/structure/ECOFIN_DSD.full.xml")
OUTPUT_PATH = Path("data/processed/ecofin_codelist_lookup.json")

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


def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    lookup = parse_codelists(DSD_PATH)

    with OUTPUT_PATH.open("w", encoding="utf-8") as file:
        json.dump(lookup, file, indent=2, ensure_ascii=False)

    print("Parsed codelists successfully.")
    print(f"Number of codelists: {len(lookup)}")
    print(f"Wrote lookup to: {OUTPUT_PATH}")

    print("\nExample lookups:")

    indicator = lookup["CL_INDICATOR"]["codes"]["NGDP_SA_XDC"]
    print("\nCL_INDICATOR / NGDP_SA_XDC")
    print(f"  Name: {indicator['name']}")
    print(f"  Description: {indicator['description']}")

    freq = lookup["CL_FREQ"]["codes"]["Q"]
    print("\nCL_FREQ / Q")
    print(f"  Name: {freq['name']}")
    print(f"  Description: {freq['description']}")


if __name__ == "__main__":
    main()
