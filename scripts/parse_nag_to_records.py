from pathlib import Path
import json
import xml.etree.ElementTree as ET


DATASET_ID = "NAG_GBR"
SOURCE_URL = "https://static.ons.gov.uk/imf/NAG_GBR.xml"
STRUCTURE_REF = "IMF_ECOFIN_DSD_1_0"

XML_PATH = Path("data/raw/NAG_GBR.xml")
OUTPUT_DIR = Path("data/processed")

SERIES_OUTPUT_PATH = OUTPUT_DIR / "nag_series_records.json"
OBSERVATIONS_OUTPUT_PATH = OUTPUT_DIR / "nag_observation_records.json"


def build_series_key(attributes: dict[str, str]) -> str:
    """
    Build a stable text key for a Series element.

    The XML attributes identify the statistical series. We sort them so that
    the key is stable even if the XML attribute order changes.
    """
    return "|".join(
        f"{key}={value}"
        for key, value in sorted(attributes.items())
    )


def parse_sdmx_file(xml_path: Path) -> tuple[list[dict], list[dict]]:
    """
    Parse one SDMX XML file into two database-shaped lists:

    1. series_records:
       one record per <Series>

    2. observation_records:
       one record per <Obs>
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()

    series_records = []
    observation_records = []

    series_elements = root.findall(".//Series")

    for series_element in series_elements:
        dimension_values = dict(series_element.attrib)
        series_key = build_series_key(dimension_values)

        series_record = {
            "dataset_id": DATASET_ID,
            "source_url": SOURCE_URL,
            "structure_ref": STRUCTURE_REF,
            "series_key": series_key,
            "dimension_values": dimension_values,
        }

        series_records.append(series_record)

        obs_elements = series_element.findall("Obs")

        for obs_element in obs_elements:
            observation_record = {
                "dataset_id": DATASET_ID,
                "series_key": series_key,
                "time_period": obs_element.attrib.get("TIME_PERIOD"),
                "obs_value": obs_element.attrib.get("OBS_VALUE"),
            }

            observation_records.append(observation_record)

    return series_records, observation_records


def write_json(path: Path, records: list[dict]) -> None:
    """
    Write records to a JSON file with nice indentation.
    """
    with path.open("w", encoding="utf-8") as file:
        json.dump(records, file, indent=2)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    series_records, observation_records = parse_sdmx_file(XML_PATH)

    if not series_records:
        raise ValueError("No series records found. Check the XML structure.")

    if not observation_records:
        raise ValueError("No observation records found. Check the XML structure.")

    write_json(SERIES_OUTPUT_PATH, series_records)
    write_json(OBSERVATIONS_OUTPUT_PATH, observation_records)

    print("Parsed SDMX file successfully.")
    print(f"Series records: {len(series_records)}")
    print(f"Observation records: {len(observation_records)}")
    print()
    print(f"Wrote series records to: {SERIES_OUTPUT_PATH}")
    print(f"Wrote observation records to: {OBSERVATIONS_OUTPUT_PATH}")

    print("\nFirst series record:")
    print(json.dumps(series_records[0], indent=2))

    print("\nFirst observation record:")
    print(json.dumps(observation_records[0], indent=2))


if __name__ == "__main__":
    main()
