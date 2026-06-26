from __future__ import annotations

import argparse
import time
import csv
import io
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass
class HttpResult:
    status: int
    content_type: str
    body: str


def fetch(
    base_url: str,
    path: str,
    timeout: float = 5.0,
    attempts: int = 5,
    delay_seconds: float = 1.0,
) -> HttpResult:
    """
    Fetch a URL from the StatsFinder app.

    Retries connection-level failures because Docker/Cloud Run services can
    take a few seconds to become ready after startup.
    """
    url = base_url.rstrip("/") + path
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:
                body = response.read().decode("utf-8")
                return HttpResult(
                    status=response.status,
                    content_type=response.headers.get("content-type", ""),
                    body=body,
                )
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8")
            return HttpResult(
                status=error.code,
                content_type=error.headers.get("content-type", ""),
                body=body,
            )
        except (urllib.error.URLError, ConnectionResetError) as error:
            last_error = error

            if attempt < attempts:
                time.sleep(delay_seconds)
                continue

    raise AssertionError(f"Could not connect to {url}: {last_error}")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def require_status(result: HttpResult, expected_status: int, label: str) -> None:
    require(
        result.status == expected_status,
        f"{label}: expected HTTP {expected_status}, got HTTP {result.status}\n{result.body}",
    )


def parse_json(result: HttpResult, label: str) -> dict[str, Any]:
    try:
        parsed = json.loads(result.body)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"{label}: response was not valid JSON\n{result.body}") from exc

    require(isinstance(parsed, dict), f"{label}: expected JSON object")
    return parsed


def test_health(base_url: str) -> None:
    result = fetch(base_url, "/health")
    require_status(result, 200, "health")

    data = parse_json(result, "health")
    require("status" in data, "health: expected a status field")


def test_database_health(base_url: str) -> None:
    result = fetch(base_url, "/health/db")
    require_status(result, 200, "database health")

    data = parse_json(result, "database health")
    require("status" in data, "database health: expected a status field")


def test_datasets(base_url: str) -> None:
    result = fetch(base_url, "/v1/datasets")
    require_status(result, 200, "list datasets")

    data = parse_json(result, "list datasets")
    require("datasets" in data, "list datasets: expected datasets field")
    require(isinstance(data["datasets"], list), "list datasets: datasets should be a list")
    require(len(data["datasets"]) > 0, "list datasets: expected at least one dataset")


def test_single_dataset(base_url: str) -> None:
    result = fetch(base_url, "/v1/datasets/NAG_GBR")
    require_status(result, 200, "single dataset")

    data = parse_json(result, "single dataset")
    require(data.get("dataset_id") == "NAG_GBR", "single dataset: expected dataset_id=NAG_GBR")
    require(data.get("series_count", 0) > 0, "single dataset: expected series_count > 0")
    require(data.get("observation_count", 0) > 0, "single dataset: expected observation_count > 0")


def test_dataset_series(base_url: str) -> None:
    result = fetch(base_url, "/v1/datasets/NAG_GBR/series?limit=5")
    require_status(result, 200, "dataset series")

    data = parse_json(result, "dataset series")
    require(data.get("dataset_id") == "NAG_GBR", "dataset series: expected dataset_id=NAG_GBR")
    require(data.get("limit") == 5, "dataset series: expected limit=5")
    require(len(data.get("series", [])) > 0, "dataset series: expected at least one series")


def test_search(base_url: str) -> None:
    path = "/v1/series/search?" + urllib.parse.urlencode(
        {
            "q": "exports",
            "dataset_id": "NAG_GBR",
            "limit": 5,
        }
    )

    result = fetch(base_url, path)
    require_status(result, 200, "series search")

    data = parse_json(result, "series search")
    require(data.get("query") == "exports", "series search: expected query=exports")
    require("results" in data, "series search: expected results field")


def test_series_metadata(base_url: str) -> None:
    path = "/v1/datasets/NAG_GBR/series/by-indicator/NGDP_R_SA_XDC"

    result = fetch(base_url, path)
    require_status(result, 200, "series metadata")

    data = parse_json(result, "series metadata")
    require(data.get("dataset_id") == "NAG_GBR", "series metadata: expected dataset_id=NAG_GBR")
    require(
        data.get("indicator_code") == "NGDP_R_SA_XDC",
        "series metadata: expected indicator_code=NGDP_R_SA_XDC",
    )


def test_observations_json(base_url: str) -> None:
    path = "/v1/datasets/NAG_GBR/series/by-indicator/NGDP_R_SA_XDC/observations?limit=5"

    result = fetch(base_url, path)
    require_status(result, 200, "observations JSON")

    data = parse_json(result, "observations JSON")
    require("observations" in data, "observations JSON: expected observations field")
    require(len(data["observations"]) == 5, "observations JSON: expected 5 observations")


def test_observations_csv(base_url: str) -> None:
    path = "/v1/datasets/NAG_GBR/series/by-indicator/NGDP_R_SA_XDC/observations.csv?limit=5"

    result = fetch(base_url, path)
    require_status(result, 200, "observations CSV")

    require(
        result.content_type.startswith("text/csv"),
        f"observations CSV: expected text/csv content type, got {result.content_type}",
    )

    rows = list(csv.DictReader(io.StringIO(result.body)))
    require(len(rows) == 5, "observations CSV: expected 5 CSV rows")
    require(rows[0]["dataset_id"] == "NAG_GBR", "observations CSV: expected dataset_id=NAG_GBR")
    require(
        rows[0]["indicator_code"] == "NGDP_R_SA_XDC",
        "observations CSV: expected indicator_code=NGDP_R_SA_XDC",
    )
    require("time_period" in rows[0], "observations CSV: expected time_period column")
    require("obs_value" in rows[0], "observations CSV: expected obs_value column")


def test_missing_dataset_404(base_url: str) -> None:
    result = fetch(base_url, "/v1/datasets/DOES_NOT_EXIST")
    require_status(result, 404, "missing dataset")


def run_smoke_tests(base_url: str) -> None:
    tests = [
        ("health", test_health),
        ("database health", test_database_health),
        ("list datasets", test_datasets),
        ("single dataset", test_single_dataset),
        ("dataset series", test_dataset_series),
        ("series search", test_search),
        ("series metadata", test_series_metadata),
        ("observations JSON", test_observations_json),
        ("observations CSV", test_observations_csv),
        ("missing dataset 404", test_missing_dataset_404),
    ]

    print(f"Running smoke tests against {base_url}")

    for label, test_function in tests:
        test_function(base_url)
        print(f"PASS {label}")

    print("All smoke tests passed.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run smoke tests against a local StatsFinder app."
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="Base URL for the running StatsFinder app.",
    )

    args = parser.parse_args()

    try:
        run_smoke_tests(args.base_url)
    except AssertionError as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(f"FAIL Could not connect to {args.base_url}: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
