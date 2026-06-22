from __future__ import annotations

import argparse
import json
import os
from typing import Any

import psycopg
from psycopg.rows import dict_row


DB_DSN = os.environ.get(
    "ONS_SDMX_DB_DSN",
    "postgresql://ons_sdmx_user:ons_sdmx_password@localhost:5433/ons_sdmx",
)


def get_dsn() -> str:
    dsn = os.environ.get("ONS_SDMX_DB_DSN")

    if not dsn:
        raise RuntimeError("ONS_SDMX_DB_DSN is not set")

    return dsn


def get_connection() -> psycopg.Connection:
    """
    Open a connection to the Postgres database.

    row_factory=dict_row means query results behave like dictionaries,
    so we can use row["series_id"] instead of row[0].
    """
    return psycopg.connect(DB_DSN, row_factory=dict_row)


def get_database_health() -> dict[str, int]:
    queries = {
        "datasets": "SELECT COUNT(*) FROM datasets",
        "series": "SELECT COUNT(*) FROM series",
        "observations": "SELECT COUNT(*) FROM observations",
    }

    counts: dict[str, int] = {}

    with psycopg.connect(get_dsn()) as conn:
        with conn.cursor() as cur:
            for label, query in queries.items():
                cur.execute(query)
                counts[label] = cur.fetchone()[0]

    return counts


def split_query_terms(query: str) -> list[str]:
    """
    Convert a user search query into simple lowercase search terms.

    Example:
        "real gdp" -> ["real", "gdp"]
    """
    return [
        term.strip().lower()
        for term in query.split()
        if term.strip()
    ]


def print_json(data: Any) -> None:
    """
    Print data as pretty JSON.

    default=str handles values like Decimal, which the standard JSON
    module cannot serialise automatically.
    """
    print(json.dumps(data, indent=2, default=str))


def list_datasets() -> list[dict[str, Any]]:
    """
    Return datasets currently loaded into the local database.

    This helps the API and homepage explain what data is available.
    """
    sql = """
        SELECT
            d.dataset_id,
            d.title AS dataset_title,
            d.data_domain_code,
            d.data_domain_label,
            d.source_url,
            d.documentation_url,
            d.metadata_url,
            d.structure_ref,
            COUNT(DISTINCT s.series_id) AS series_count,
            COUNT(o.observation_id) AS observation_count
        FROM datasets d
        LEFT JOIN series s
            ON s.dataset_id = d.dataset_id
        LEFT JOIN observations o
            ON o.series_id = s.series_id
        GROUP BY
            d.dataset_id,
            d.title,
            d.source_url,
            d.documentation_url,
            d.metadata_url,
            d.structure_ref
        ORDER BY
            d.dataset_id;
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            return cur.fetchall()


def get_dataset(dataset_id: str) -> dict[str, Any] | None:
    """
    Return one dataset by public dataset_id.

    Browse v1 uses curated navigation, but this page content is source-backed:
    dataset metadata and counts come from the database.
    """
    sql = """
        SELECT
            d.dataset_id,
            d.title AS dataset_title,
            d.data_domain_code,
            d.data_domain_label,
            d.source_url,
            d.documentation_url,
            d.metadata_url,
            d.structure_ref,
            COUNT(DISTINCT s.series_id) AS series_count,
            COUNT(o.observation_id) AS observation_count
        FROM datasets d
        LEFT JOIN series s
            ON s.dataset_id = d.dataset_id
        LEFT JOIN observations o
            ON o.series_id = s.series_id
        WHERE d.dataset_id = %s
        GROUP BY
            d.dataset_id,
            d.title,
            d.data_domain_code,
            d.data_domain_label,
            d.source_url,
            d.documentation_url,
            d.metadata_url,
            d.structure_ref;
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (dataset_id,))
            return cur.fetchone()


def list_series_for_dataset(
    dataset_id: str,
    limit: int = 500,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """
    Return series belonging to one dataset.

    This powers both:
    - /v1/datasets/{dataset_id}/series
    - /browse/datasets/{dataset_id}

    Where available, it uses the cleaned semantic-search document metadata
    to provide a friendlier display name and parsed fields.
    """
    sql = """
        WITH observation_summary AS (
            SELECT
                series_id,
                MIN(time_period) AS first_period,
                MAX(time_period) AS latest_period,
                COUNT(observation_id) AS observation_count
            FROM observations
            GROUP BY series_id
        )
        SELECT
            s.series_id,
            d.dataset_id,
            d.title AS dataset_title,
            d.source_url,
            d.documentation_url,
            d.metadata_url,
            d.structure_ref,
            s.series_key,
            s.dimension_values ->> 'INDICATOR' AS indicator_code,
            s.dimension_labels -> 'INDICATOR' ->> 'name' AS indicator_name,
            COALESCE(
                sd.primary_text,
                s.dimension_labels -> 'INDICATOR' ->> 'name',
                s.dimension_values ->> 'INDICATOR'
            ) AS display_name,
            sd.parsed_metadata ->> 'measure_type' AS measure_type,
            sd.parsed_metadata ->> 'seasonal_adjustment' AS seasonal_adjustment,
            sd.parsed_metadata ->> 'unit' AS unit,
            sd.parsed_metadata ->> 'base_period' AS base_period,
            sd.parsed_metadata ->> 'unit_multiplier' AS unit_multiplier,
            s.dimension_values ->> 'FREQ' AS frequency_code,
            s.dimension_labels -> 'FREQ' ->> 'name' AS frequency_name,
            observation_summary.first_period,
            observation_summary.latest_period,
            COALESCE(observation_summary.observation_count, 0) AS observation_count
        FROM series s
        JOIN datasets d
            ON d.dataset_id = s.dataset_id
        LEFT JOIN series_search_documents sd
            ON sd.series_id = s.series_id
        LEFT JOIN observation_summary
            ON observation_summary.series_id = s.series_id
        WHERE s.dataset_id = %s
        ORDER BY
            display_name,
            measure_type NULLS LAST,
            seasonal_adjustment NULLS LAST,
            indicator_code
        LIMIT %s
        OFFSET %s;
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (dataset_id, limit, offset))
            return list(cur.fetchall())


def search_series(
    query: str,
    limit: int = 10,
    dataset_id: str | None = None,
) -> list[dict[str, Any]]:
    """
    Search for series using search_text.

    This is currently literal metadata search: user terms must match the
    official parsed metadata text.

    If dataset_id is provided, restrict search to that dataset.
    """
    terms = split_query_terms(query)

    if not terms:
        return []

    where_clauses = []
    params: list[Any] = []

    for term in terms:
        where_clauses.append("s.search_text ILIKE %s")
        params.append(f"%{term}%")

    if dataset_id:
        where_clauses.append("s.dataset_id = %s")
        params.append(dataset_id)

    where_sql = " AND ".join(where_clauses)

    sql = f"""
        SELECT
            s.series_id,
            s.dataset_id,
            d.title AS dataset_title,
            d.source_url,
            d.documentation_url,
            d.metadata_url,
            d.structure_ref,
            s.dimension_values ->> 'INDICATOR' AS indicator_code,
            s.dimension_labels -> 'INDICATOR' ->> 'name' AS indicator_name,
            s.dimension_values ->> 'FREQ' AS frequency_code,
            s.dimension_labels -> 'FREQ' ->> 'name' AS frequency_name,
            MIN(o.time_period) AS first_period,
            MAX(o.time_period) AS latest_period,
            COUNT(o.observation_id) AS observation_count
        FROM series s
        JOIN datasets d
            ON d.dataset_id = s.dataset_id
        LEFT JOIN observations o
            ON o.series_id = s.series_id
        WHERE {where_sql}
        GROUP BY
            s.series_id,
            s.dataset_id,
            d.title,
            d.source_url,
            d.documentation_url,
            d.metadata_url,
            d.structure_ref,
            s.dimension_values ->> 'INDICATOR',
            s.dimension_labels -> 'INDICATOR' ->> 'name',
            s.dimension_values ->> 'FREQ',
            s.dimension_labels -> 'FREQ' ->> 'name'
        ORDER BY
            observation_count DESC,
            s.series_id
        LIMIT %s;
    """

    params.append(limit)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()


def get_series_summary(series_id: int) -> dict[str, Any] | None:
    """
    Return one summary row for a series.

    This is the kind of information a future API result page might show.
    """
    sql = """
        SELECT
            s.series_id,
            s.dataset_id,
            s.dimension_values ->> 'INDICATOR' AS indicator_code,
            s.dimension_labels -> 'INDICATOR' ->> 'name' AS indicator_name,
            s.dimension_values ->> 'FREQ' AS frequency_code,
            s.dimension_labels -> 'FREQ' ->> 'name' AS frequency_name,
            MIN(o.time_period) AS first_period,
            MAX(o.time_period) AS latest_period,
            COUNT(o.observation_id) AS observation_count
        FROM series s
        LEFT JOIN observations o
            ON o.series_id = s.series_id
        WHERE s.series_id = %s
        GROUP BY
            s.series_id,
            s.dataset_id,
            s.dimension_values ->> 'INDICATOR',
            s.dimension_labels -> 'INDICATOR' ->> 'name',
            s.dimension_values ->> 'FREQ',
            s.dimension_labels -> 'FREQ' ->> 'name';
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (series_id,))
            return cur.fetchone()

def get_series_summary_by_indicator(
    dataset_id: str,
    indicator_code: str,
) -> dict[str, Any] | None:
    """
    Return one detailed summary row for a series identified by dataset_id
    and indicator code.

    This is more public-user-friendly than requiring the internal series_id,
    while still exposing SDMX-derived metadata and source provenance.
    """
    sql = """
        SELECT
            s.series_id,
            s.dataset_id,
            d.title AS dataset_title,
            d.source_url,
            d.documentation_url,
            d.metadata_url,
            d.structure_ref,
            s.series_key,
            s.dimension_values,
            s.dimension_labels,
            s.dimension_values ->> 'INDICATOR' AS indicator_code,
            s.dimension_labels -> 'INDICATOR' ->> 'name' AS indicator_name,
            s.dimension_values ->> 'FREQ' AS frequency_code,
            s.dimension_labels -> 'FREQ' ->> 'name' AS frequency_name,
            MIN(o.time_period) AS first_period,
            MAX(o.time_period) AS latest_period,
            COUNT(o.observation_id) AS observation_count
        FROM series s
        JOIN datasets d
            ON d.dataset_id = s.dataset_id
        LEFT JOIN observations o
            ON o.series_id = s.series_id
        WHERE s.dataset_id = %s
          AND s.dimension_values ->> 'INDICATOR' = %s
        GROUP BY
            s.series_id,
            s.dataset_id,
            d.title,
            d.source_url,
            d.documentation_url,
            d.metadata_url,
            d.structure_ref,
            s.series_key,
            s.dimension_values,
            s.dimension_labels,
            s.dimension_values ->> 'INDICATOR',
            s.dimension_labels -> 'INDICATOR' ->> 'name',
            s.dimension_values ->> 'FREQ',
            s.dimension_labels -> 'FREQ' ->> 'name';
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (dataset_id, indicator_code))
            return cur.fetchone()

def get_series_observations(
    series_id: int,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """
    Return observation rows for one series.
    """
    sql = """
        SELECT
            time_period,
            obs_value
        FROM observations
        WHERE series_id = %s
        ORDER BY time_period
        LIMIT %s;
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (series_id, limit))
            return list(cur.fetchall())


def get_series_observations_by_indicator(
    dataset_id: str,
    indicator_code: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """
    Return observation rows for a series identified by dataset_id and indicator code.
    """
    sql = """
        SELECT
            o.time_period,
            o.obs_value
        FROM observations o
        JOIN series s
            ON o.series_id = s.series_id
        WHERE s.dataset_id = %s
          AND s.dimension_values ->> 'INDICATOR' = %s
        ORDER BY o.time_period
        LIMIT %s;
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (dataset_id, indicator_code, limit))
            return list(cur.fetchall())


def build_search_response(
    query: str,
    limit: int,
    rows: list[dict[str, Any]],
    dataset_id: str | None = None,
) -> dict[str, Any]:
    """
    Build the public API response for search results.
    """
    return {
        "query": query,
        "dataset_id": dataset_id,
        "limit": limit,
        "count": len(rows),
        "results": rows,
    }


def build_observations_response(
    series_id: int,
    limit: int,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Wrap observation rows in an API-like response shape.
    """
    return {
        "series_id": series_id,
        "limit": limit,
        "count": len(rows),
        "observations": rows,
    }


def build_observations_by_indicator_response(
    dataset_id: str,
    indicator_code: str,
    limit: int,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Wrap observation rows for a public dataset/indicator identifier."""
    return {
        "dataset_id": dataset_id,
        "indicator_code": indicator_code,
        "limit": limit,
        "count": len(rows),
        "observations": rows,
    }


def print_search_results(rows: list[dict[str, Any]]) -> None:
    """Print search results in a readable terminal format."""
    if not rows:
        print("No matching series found.")
        return

    for row in rows:
        print(
            f"{row['series_id']:>3} | "
            f"{row['indicator_code']} | "
            f"{row['frequency_name']} | "
            f"{row['first_period']} to {row['latest_period']} | "
            f"{row['observation_count']} observations"
        )
        print(f"    {row['indicator_name']}")


def print_summary(row: dict[str, Any] | None) -> None:
    """Print one series summary."""
    if row is None:
        print("Series not found.")
        return

    print(f"series_id:         {row['series_id']}")
    print(f"dataset_id:        {row['dataset_id']}")
    print(f"indicator_code:    {row['indicator_code']}")
    print(f"indicator_name:    {row['indicator_name']}")
    print(f"frequency_code:    {row['frequency_code']}")
    print(f"frequency_name:    {row['frequency_name']}")
    print(f"first_period:      {row['first_period']}")
    print(f"latest_period:     {row['latest_period']}")
    print(f"observation_count: {row['observation_count']}")


def print_observations(rows: list[dict[str, Any]]) -> None:
    """Print observations in a readable terminal format."""
    if not rows:
        print("No observations found.")
        return

    for row in rows:
        print(f"{row['time_period']}: {row['obs_value']}")


def build_parser() -> argparse.ArgumentParser:
    """
    Build the command-line interface.

    This lets us run:
        python3 scripts/query_postgres.py search "real gdp"
        python3 scripts/query_postgres.py search "real gdp" --json
        python3 scripts/query_postgres.py summary 11
        python3 scripts/query_postgres.py summary 11 --json
        python3 scripts/query_postgres.py observations 11 --limit 5
        python3 scripts/query_postgres.py observations 11 --limit 5 --json
    """
    parser = argparse.ArgumentParser(
        description="Query the local ONS SDMX Postgres database."
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    search_parser = subparsers.add_parser(
        "search",
        help="Search for series by text.",
    )
    search_parser.add_argument("query")
    search_parser.add_argument("--limit", type=int, default=10)
    search_parser.add_argument(
    "--dataset-id",
    help="Optional dataset ID to restrict search, for example CPI_GBR.",
    )
    search_parser.add_argument("--json", action="store_true")

    summary_parser = subparsers.add_parser(
        "summary",
        help="Show summary metadata for one series.",
    )
    summary_parser.add_argument("series_id", type=int)
    summary_parser.add_argument("--json", action="store_true")

    summary_by_indicator_parser = subparsers.add_parser(
        "summary-by-indicator",
        help="Show summary metadata using dataset_id and indicator code.",
    )
    summary_by_indicator_parser.add_argument("dataset_id")
    summary_by_indicator_parser.add_argument("indicator_code")
    summary_by_indicator_parser.add_argument("--json", action="store_true")

    observations_parser = subparsers.add_parser(
        "observations",
        help="Show observations for one series.",
    )
    observations_parser.add_argument("series_id", type=int)
    observations_parser.add_argument("--limit", type=int, default=10)
    observations_parser.add_argument("--json", action="store_true")

    observations_by_indicator_parser = subparsers.add_parser(
        "observations-by-indicator",
        help="Show observations using dataset_id and indicator code.",
    )
    observations_by_indicator_parser.add_argument("dataset_id")
    observations_by_indicator_parser.add_argument("indicator_code")
    observations_by_indicator_parser.add_argument("--limit", type=int, default=10)
    observations_by_indicator_parser.add_argument("--json", action="store_true")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "search":
        rows = search_series(
                args.query,
                args.limit,
                dataset_id=args.dataset_id,
            )

        response = build_search_response(
            args.query,
            args.limit,
            rows,
            dataset_id=args.dataset_id,
        )

        if args.json:
            print_json(build_search_response(args.query, args.limit, rows))
        else:
            print_search_results(rows)

    elif args.command == "summary":
        row = get_series_summary(args.series_id)

        if args.json:
            print_json(row)
        else:
            print_summary(row)

    elif args.command == "summary-by-indicator":
        row = get_series_summary_by_indicator(
            args.dataset_id,
            args.indicator_code,
        )

        if args.json:
            print_json(row)
        else:
            print_summary(row)

    elif args.command == "observations":
        rows = get_series_observations(args.series_id, args.limit)

        if args.json:
            print_json(
                build_observations_response(
                    args.series_id,
                    args.limit,
                    rows,
                )
            )
        else:
            print_observations(rows)

    elif args.command == "observations-by-indicator":
        rows = get_series_observations_by_indicator(
            args.dataset_id,
            args.indicator_code,
            args.limit,
        )

        if args.json:
            print_json(
                build_observations_by_indicator_response(
                    args.dataset_id,
                    args.indicator_code,
                    args.limit,
                    rows,
                )
            )
        else:
            print_observations(rows)


if __name__ == "__main__":
    main()
