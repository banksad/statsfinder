from __future__ import annotations

import csv
import io
import re
from typing import Any
from urllib.parse import quote


def safe_filename_component(value: str) -> str:
    """
    Convert a public identifier into a safe filename component.

    Dataset IDs and indicator codes are already controlled-looking strings,
    but this keeps the Content-Disposition filename robust.
    """
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value)
    cleaned = cleaned.strip("-")

    return cleaned or "series"


def optional_series_id_query(
    series_id: Any | None,
    separator: str,
) -> str:
    """
    Build an optional series_id query-string fragment.

    Example:
      optional_series_id_query(123, "?") -> "?series_id=123"
      optional_series_id_query(123, "&") -> "&series_id=123"
      optional_series_id_query(None, "&") -> ""
    """
    if series_id in (None, ""):
        return ""

    return f"{separator}series_id={quote(str(series_id), safe='')}"


def build_series_resource_urls(
    dataset_id: str,
    indicator_code: str,
    series_id: Any | None = None,
) -> dict[str, str]:
    """
    Build internal API URLs for one series.

    When series_id is present, the URLs point to an exact series row rather
    than only an indicator code. This matters when one indicator exists at
    multiple frequencies, such as annual and quarterly GGO series.
    """
    encoded_dataset_id = quote(dataset_id, safe="")
    encoded_indicator_code = quote(indicator_code, safe="")

    metadata_base_url = (
        f"/v1/datasets/{encoded_dataset_id}"
        f"/series/by-indicator/{encoded_indicator_code}"
    )

    return {
        "metadata_url": metadata_base_url
        + optional_series_id_query(series_id, separator="?"),
        "observations_url": f"{metadata_base_url}/observations?limit=20"
        + optional_series_id_query(series_id, separator="&"),
        "observations_csv_url": f"{metadata_base_url}/observations.csv?limit=10000"
        + optional_series_id_query(series_id, separator="&"),
    }


def build_observations_csv(
    summary: dict[str, Any],
    observations: list[dict[str, Any]],
) -> str:
    """
    Build a simple long-format CSV for one statistical series.

    The CSV repeats series metadata on each row. That makes the file easy to
    combine with other exported series later.
    """
    output = io.StringIO()

    fieldnames = [
        "series_id",
        "dataset_id",
        "dataset_title",
        "series_key",
        "indicator_code",
        "indicator_name",
        "frequency_code",
        "frequency_name",
        "time_period",
        "obs_value",
        "source_url",
        "documentation_url",
        "metadata_url",
        "structure_ref",
    ]

    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()

    for observation in observations:
        writer.writerow(
            {
                "series_id": summary.get("series_id"),
                "dataset_id": summary.get("dataset_id"),
                "dataset_title": summary.get("dataset_title"),
                "series_key": summary.get("series_key"),
                "indicator_code": summary.get("indicator_code"),
                "indicator_name": summary.get("indicator_name"),
                "frequency_code": summary.get("frequency_code"),
                "frequency_name": summary.get("frequency_name"),
                "time_period": observation.get("time_period"),
                "obs_value": observation.get("obs_value"),
                "source_url": summary.get("source_url"),
                "documentation_url": summary.get("documentation_url"),
                "metadata_url": summary.get("metadata_url"),
                "structure_ref": summary.get("structure_ref"),
            }
        )

    return output.getvalue()


