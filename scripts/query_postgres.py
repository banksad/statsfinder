from __future__ import annotations

import argparse
import os
from typing import Any

import psycopg
from psycopg.rows import dict_row


DB_DSN = os.environ.get(
    "ONS_SDMX_DB_DSN",
    "postgresql://ons_sdmx_user:ons_sdmx_password@localhost:5433/ons_sdmx",
)


def get_connection() -> psycopg.Connection:
    """
    Open a connection to the Postgres database.

    row_factory=dict_row means query results behave like dictionaries,
    so we can use row["series_id"] instead of row[0].
    """
    return psycopg.connect(DB_DSN, row_factory=dict_row)


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


def search_series(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """
    Search for series whose search_text contains all query terms.

    This is still simple keyword search, but now it is backed by Postgres.
    """
    terms = split_query_terms(query)

    if not terms:
        return []

    where_clauses = ["s.search_text ILIKE %s" for _ in terms]
    where_sql = " AND ".join(where_clauses)

    params: list[Any] = [f"%{term}%" for term in terms]
    params.append(limit)

    sql = f"""
        SELECT
            s.series_id,
            s.dimension_values ->> 'INDICATOR' AS indicator_code,
            s.dimension_labels -> 'INDICATOR' ->> 'name' AS indicator_name,
            s.dimension_labels -> 'FREQ' ->> 'name' AS frequency_name,
            MIN(o.time_period) AS first_period,
            MAX(o.time_period) AS latest_period,
            COUNT(o.observation_id) AS observation_count
        FROM series s
        LEFT JOIN observations o
            ON o.series_id = s.series_id
        WHERE {where_sql}
        GROUP BY
            s.series_id,
            s.dimension_values ->> 'INDICATOR',
            s.dimension_labels -> 'INDICATOR' ->> 'name',
            s.dimension_labels -> 'FREQ' ->> 'name'
        ORDER BY
            s.series_id
        LIMIT %s;
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return list(cur.fetchall())


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
        python3 scripts/query_postgres.py summary 11
        python3 scripts/query_postgres.py observations 11 --limit 5
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

    summary_parser = subparsers.add_parser(
        "summary",
        help="Show summary metadata for one series.",
    )
    summary_parser.add_argument("series_id", type=int)

    observations_parser = subparsers.add_parser(
        "observations",
        help="Show observations for one series.",
    )
    observations_parser.add_argument("series_id", type=int)
    observations_parser.add_argument("--limit", type=int, default=10)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "search":
        rows = search_series(args.query, args.limit)
        print_search_results(rows)

    elif args.command == "summary":
        row = get_series_summary(args.series_id)
        print_summary(row)

    elif args.command == "observations":
        rows = get_series_observations(args.series_id, args.limit)
        print_observations(rows)


if __name__ == "__main__":
    main()
