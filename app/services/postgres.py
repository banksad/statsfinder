from __future__ import annotations

import argparse
import json
import os
from urllib.parse import quote
from typing import Any

import psycopg
from psycopg.rows import dict_row

from app.services.series_sql import (
    OBSERVATION_SUMMARY_CTE,
    OBSERVATION_SUMMARY_SELECT,
    dataset_series_metadata_select,
    display_name_select,
    frequency_select,
    observation_summary_cte,
    parsed_metadata_select,
)


def get_dsn() -> str:
    """
    Return the database connection string from the environment.

    Local Docker Compose sets ONS_SDMX_DB_DSN directly. Cloud Run can do the
    same, or it can provide CLOUD_SQL_INSTANCE_CONNECTION_NAME plus database
    credentials so we connect through the Cloud SQL Unix socket mounted at
    /cloudsql/<INSTANCE_CONNECTION_NAME>.
    """
    dsn = os.environ.get("ONS_SDMX_DB_DSN")

    if dsn:
        return dsn

    cloud_sql_instance = os.environ.get("CLOUD_SQL_INSTANCE_CONNECTION_NAME")

    if cloud_sql_instance:
        database = os.environ.get("DB_NAME") or os.environ.get("POSTGRES_DB")
        user = os.environ.get("DB_USER") or os.environ.get("POSTGRES_USER")
        password = os.environ.get("DB_PASSWORD") or os.environ.get("POSTGRES_PASSWORD")

        missing = [
            name
            for name, value in {
                "DB_NAME or POSTGRES_DB": database,
                "DB_USER or POSTGRES_USER": user,
                "DB_PASSWORD or POSTGRES_PASSWORD": password,
            }.items()
            if not value
        ]

        if missing:
            raise RuntimeError(
                "Cloud SQL database configuration is incomplete. Missing: "
                + ", ".join(missing)
            )

        return (
            f"postgresql://{quote(user, safe='')}:{quote(password, safe='')}@/{quote(database, safe='')}"
            f"?host=/cloudsql/{quote(cloud_sql_instance, safe=':')}"
        )

    raise RuntimeError(
        "Database configuration is not set. Set ONS_SDMX_DB_DSN, or set "
        "CLOUD_SQL_INSTANCE_CONNECTION_NAME with DB_NAME, DB_USER, and DB_PASSWORD "
        "before connecting to Postgres."
    )


def get_connection() -> psycopg.Connection:
    """
    Open a connection to the Postgres database.

    row_factory=dict_row means query results behave like dictionaries,
    so we can use row["series_id"] instead of row[0].
    """
    return psycopg.connect(get_dsn(), row_factory=dict_row)


def get_database_health() -> dict[str, int]:
    queries = {
        "datasets": "SELECT COUNT(*) AS count FROM datasets",
        "series": "SELECT COUNT(*) AS count FROM series",
        "observations": "SELECT COUNT(*) AS count FROM observations",
    }

    counts: dict[str, int] = {}

    with get_connection() as conn:
        with conn.cursor() as cur:
            for label, query in queries.items():
                cur.execute(query)
                row = cur.fetchone()

                if row is None:
                    raise RuntimeError(f"Database health query returned no row for {label}")

                counts[label] = int(row["count"])

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
            d.data_domain_code,
            d.data_domain_label,
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
            return list(cur.fetchall())


def get_dataset(dataset_id: str) -> dict[str, Any] | None:
    """
    Return one dataset by public dataset_id.

    Browse uses curated navigation, but this page content is source-backed:
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
    sql = f"""
        WITH {OBSERVATION_SUMMARY_CTE}
        SELECT
{dataset_series_metadata_select("s", "d")},{display_name_select()},
{parsed_metadata_select()},
{frequency_select()},
{OBSERVATION_SUMMARY_SELECT.rstrip()}
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
            frequency_code,
            measure_type NULLS LAST,
            seasonal_adjustment NULLS LAST,
            indicator_code,
            s.series_id
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
    Search for series using source-backed metadata.

    This is currently literal metadata search. It searches the cleaned semantic
    keyword_text when available, falling back to the original series search_text.
    """
    terms = split_query_terms(query)

    if not terms:
        return []

    where_clauses = []
    params: list[Any] = []

    for term in terms:
        where_clauses.append("COALESCE(sd.keyword_text, s.search_text) ILIKE %s")
        params.append(f"%{term}%")

    if dataset_id:
        where_clauses.append("s.dataset_id = %s")
        params.append(dataset_id)

    where_sql = " AND ".join(where_clauses)

    sql = f"""
        WITH {OBSERVATION_SUMMARY_CTE}
        SELECT
{dataset_series_metadata_select()},{display_name_select(use_dataset_case=False)},
{parsed_metadata_select()},
{frequency_select()},
{OBSERVATION_SUMMARY_SELECT.rstrip()}
        FROM series s
        JOIN datasets d
            ON d.dataset_id = s.dataset_id
        LEFT JOIN series_search_documents sd
            ON sd.series_id = s.series_id
        LEFT JOIN observation_summary
            ON observation_summary.series_id = s.series_id
        WHERE {where_sql}
        ORDER BY
            observation_count DESC,
            display_name,
            frequency_code,
            s.series_id
        LIMIT %s;
    """

    params.append(limit)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return list(cur.fetchall())


def get_series_summary(series_id: int) -> dict[str, Any] | None:
    """
    Return one summary row for a series using its internal series_id.
    """
    sql = f"""
        WITH {OBSERVATION_SUMMARY_CTE}
        SELECT
{dataset_series_metadata_select(include_dimension_json=True)},{display_name_select(use_dataset_case=False)},
{parsed_metadata_select()},
{frequency_select()},
{OBSERVATION_SUMMARY_SELECT.rstrip()}
        FROM series s
        JOIN datasets d
            ON d.dataset_id = s.dataset_id
        LEFT JOIN series_search_documents sd
            ON sd.series_id = s.series_id
        LEFT JOIN observation_summary
            ON observation_summary.series_id = s.series_id
        WHERE s.series_id = %s;
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (series_id,))
            return cur.fetchone()


def get_series_summary_by_indicator(
    dataset_id: str,
    indicator_code: str,
    series_id: int | None = None,
) -> dict[str, Any] | None:
    """
    Return one detailed summary row for a series identified by dataset_id
    and indicator code.

    When series_id is supplied, it disambiguates exact annual/quarterly
    variants that share the same indicator code.
    """
    sql = f"""
        WITH selected_series AS (
            SELECT
                s.series_id
            FROM series s
            WHERE s.dataset_id = %s
              AND s.dimension_values ->> 'INDICATOR' = %s
              AND (%s::integer IS NULL OR s.series_id = %s)
            ORDER BY
                s.series_id
            LIMIT 1
        ),
        {observation_summary_cte(
            observations_alias="o",
            series_id_expression="o.series_id",
            join_clause="JOIN selected_series selected ON selected.series_id = o.series_id",
            group_by_expression="o.series_id",
        )}
        SELECT
{dataset_series_metadata_select(include_dimension_json=True)},{display_name_select(use_dataset_case=False)},
{parsed_metadata_select()},
{frequency_select()},
{OBSERVATION_SUMMARY_SELECT.rstrip()}
        FROM selected_series selected
        JOIN series s
            ON s.series_id = selected.series_id
        JOIN datasets d
            ON d.dataset_id = s.dataset_id
        LEFT JOIN series_search_documents sd
            ON sd.series_id = s.series_id
        LEFT JOIN observation_summary
            ON observation_summary.series_id = s.series_id;
    """

    params = (
        dataset_id,
        indicator_code,
        series_id,
        series_id,
    )

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()


def get_series_observations(
    series_id: int,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """
    Return observation rows for one exact series.
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
    series_id: int | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """
    Return observation rows for one series identified by dataset_id and
    indicator code.

    When series_id is supplied, it disambiguates exact annual/quarterly
    variants that share the same indicator code.
    """
    sql = """
        WITH selected_series AS (
            SELECT
                s.series_id
            FROM series s
            WHERE s.dataset_id = %s
              AND s.dimension_values ->> 'INDICATOR' = %s
              AND (%s::integer IS NULL OR s.series_id = %s)
            ORDER BY
                s.series_id
            LIMIT 1
        )
        SELECT
            o.time_period,
            o.obs_value
        FROM observations o
        JOIN selected_series selected
            ON selected.series_id = o.series_id
        ORDER BY
            o.time_period
        LIMIT %s;
    """

    params = (
        dataset_id,
        indicator_code,
        series_id,
        series_id,
        limit,
    )

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
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
    """
    Wrap observation rows for a public dataset/indicator identifier.
    """
    return {
        "dataset_id": dataset_id,
        "indicator_code": indicator_code,
        "limit": limit,
        "count": len(rows),
        "observations": rows,
    }


def print_search_results(rows: list[dict[str, Any]]) -> None:
    """
    Print search results in a readable terminal format.
    """
    if not rows:
        print("No matching series found.")
        return

    for row in rows:
        display_name = (
            row.get("display_name")
            or row.get("indicator_name")
            or row.get("indicator_code")
            or row.get("series_key")
        )

        print(
            f"{row['series_id']:>3} | "
            f"{row.get('indicator_code')} | "
            f"{row.get('frequency_name') or row.get('frequency_code')} | "
            f"{row.get('first_period')} to {row.get('latest_period')} | "
            f"{row.get('observation_count')} observations"
        )
        print(f"    {display_name}")


def print_summary(row: dict[str, Any] | None) -> None:
    """
    Print one series summary.
    """
    if row is None:
        print("Series not found.")
        return

    print(f"series_id:         {row['series_id']}")
    print(f"dataset_id:        {row['dataset_id']}")
    print(f"indicator_code:    {row['indicator_code']}")
    print(f"display_name:      {row.get('display_name')}")
    print(f"indicator_name:    {row['indicator_name']}")
    print(f"frequency_code:    {row['frequency_code']}")
    print(f"frequency_name:    {row['frequency_name']}")
    print(f"first_period:      {row['first_period']}")
    print(f"latest_period:     {row['latest_period']}")
    print(f"observation_count: {row['observation_count']}")


def print_observations(rows: list[dict[str, Any]]) -> None:
    """
    Print observations in a readable terminal format.
    """
    if not rows:
        print("No observations found.")
        return

    for row in rows:
        print(f"{row['time_period']}: {row['obs_value']}")


def build_parser() -> argparse.ArgumentParser:
    """
    Build the command-line interface.

    Examples:
        python -m scripts.db.query_postgres search "real gdp"
        python -m scripts.db.query_postgres search "real gdp" --json
        python -m scripts.db.query_postgres summary 11
        python -m scripts.db.query_postgres summary-by-indicator GGO_GBR GRT_G14_GG_XDC --series-id 123
        python -m scripts.db.query_postgres observations 11 --limit 5
        python -m scripts.db.query_postgres observations-by-indicator GGO_GBR GRT_G14_GG_XDC --series-id 123 --limit 5
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
    summary_by_indicator_parser.add_argument(
        "--series-id",
        type=int,
        default=None,
        help="Optional exact series ID to disambiguate annual/quarterly variants.",
    )
    summary_by_indicator_parser.add_argument("--json", action="store_true")

    observations_parser = subparsers.add_parser(
        "observations",
        help="Show observations for one exact series.",
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
    observations_by_indicator_parser.add_argument(
        "--series-id",
        type=int,
        default=None,
        help="Optional exact series ID to disambiguate annual/quarterly variants.",
    )
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

        if args.json:
            print_json(
                build_search_response(
                    args.query,
                    args.limit,
                    rows,
                    dataset_id=args.dataset_id,
                )
            )
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
            series_id=args.series_id,
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
            series_id=args.series_id,
            limit=args.limit,
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
