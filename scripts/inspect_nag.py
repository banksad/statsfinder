from pathlib import Path
import xml.etree.ElementTree as ET

XML_PATH = Path("data/raw/NAG_GBR.xml")

def build_series_key(attributes: dict[str,str]) -> str:
    return "|".join(
            f"{key}={value}"
            for key, value in sorted(attributes.items())
            )

def main() -> None:
    tree = ET.parse(XML_PATH)
    root = tree.getroot()

    series_elements = root.findall(".//Series")
    observation_elements = root.findall(".//Obs")

    print(f"Root tag: {root.tag}")
    print(f"Number of series: {len(series_elements)}")
    print(f"Number of observations: {len(observation_elements)}")

    first_series = series_elements[0]
    first_series_key = build_series_key(first_series.attrib)

    print("\nFirst series key:")
    print(f" {first_series_key}")

    print("\nFirst series attributes:")
    for key, value in first_series.attrib.items():
        print(f"  {key}: {value}")

    print("\nFirst five observations in first series:")
    for obs in first_series.findall("Obs")[:5]:
        time_period = obs.attrib.get("TIME_PERIOD")
        obs_value = obs.attrib.get("OBS_VALUE")
        print(f"  {time_period}: {obs_value}")

    print("\nAll series keys:")
    for index, series in enumerate(series_elements, start=1):
        series_key = build_series_key(series.attrib)
        print(f"  {index:02d}. {series_key}")

if __name__ == "__main__":
    main()
