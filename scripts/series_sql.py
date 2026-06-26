"""Reusable SQL fragments for series summary queries."""

from __future__ import annotations


OBSERVATION_SUMMARY_CTE = """
observation_summary AS (
    SELECT
        series_id,
        MIN(time_period) AS first_period,
        MAX(time_period) AS latest_period,
        COUNT(observation_id) AS observation_count
    FROM observations
    GROUP BY series_id
)
"""


def observation_summary_cte(
    observations_alias: str = "observations",
    series_id_expression: str = "series_id",
    join_clause: str | None = None,
    group_by_expression: str | None = None,
) -> str:
    """Build an observation_summary CTE with stable output aliases."""
    group_by = group_by_expression or series_id_expression
    join_sql = f"\n    {join_clause}" if join_clause else ""

    return f"""
observation_summary AS (
    SELECT
        {series_id_expression} AS series_id,
        MIN({observations_alias}.time_period) AS first_period,
        MAX({observations_alias}.time_period) AS latest_period,
        COUNT({observations_alias}.observation_id) AS observation_count
    FROM observations {observations_alias}{join_sql}
    GROUP BY
        {group_by}
)
"""


def dataset_series_metadata_select(
    series_alias: str = "s",
    dataset_alias: str = "d",
    include_dimension_json: bool = False,
) -> str:
    """Return the shared dataset/series metadata select list."""
    dimension_json = ""
    if include_dimension_json:
        dimension_json = f"""
    {series_alias}.dimension_values,
    {series_alias}.dimension_labels,"""

    return f"""
    {series_alias}.series_id,
    {series_alias}.dataset_id,
    {dataset_alias}.title AS dataset_title,
    {dataset_alias}.source_url,
    {dataset_alias}.documentation_url,
    {dataset_alias}.metadata_url,
    {dataset_alias}.structure_ref,
    {series_alias}.series_key,{dimension_json}
    {series_alias}.dimension_values ->> 'INDICATOR' AS indicator_code,
    {series_alias}.dimension_labels -> 'INDICATOR' ->> 'name' AS indicator_name"""


def display_name_case(
    dataset_id_expression: str,
    parsed_metadata_expression: str,
    primary_text_expression: str,
) -> str:
    """Return dataset-specific display-name cleanup CASE expression."""
    return f"""
CASE
    WHEN {dataset_id_expression} = 'BOP_GBR' THEN (
        SELECT string_agg(cleaned_part, ', ' ORDER BY ord)
        FROM (
            SELECT
                h.ord,
                NULLIF(
                    trim(
                        regexp_replace(
                            h.value,
                            '\\s*\\[BPM6\\]',
                            '',
                            'g'
                        )
                    ),
                    ''
                ) AS cleaned_part
            FROM jsonb_array_elements_text({parsed_metadata_expression} -> 'hierarchy')
                WITH ORDINALITY AS h(value, ord)
            WHERE h.ord > 1
              AND h.value <> 'Current Account'
        ) parts
        WHERE cleaned_part IS NOT NULL
    )

    WHEN {dataset_id_expression} = 'SBS_GBR' THEN (
        SELECT string_agg(h.value, ', ' ORDER BY h.ord)
        FROM jsonb_array_elements_text({parsed_metadata_expression} -> 'hierarchy')
            WITH ORDINALITY AS h(value, ord)
        WHERE h.ord > 2
    )

    WHEN {dataset_id_expression} = 'CPI_GBR' THEN (
        SELECT string_agg(h.value, ', ' ORDER BY h.ord)
        FROM jsonb_array_elements_text({parsed_metadata_expression} -> 'hierarchy')
            WITH ORDINALITY AS h(value, ord)
        WHERE h.ord > 1
    )

    ELSE
        {primary_text_expression}
END"""


def display_name_select(
    dataset_id_expression: str = "s.dataset_id",
    parsed_metadata_expression: str = "sd.parsed_metadata",
    primary_text_expression: str = "sd.primary_text",
    indicator_name_expression: str = "s.dimension_labels -> 'INDICATOR' ->> 'name'",
    indicator_code_expression: str = "s.dimension_values ->> 'INDICATOR'",
    use_dataset_case: bool = True,
) -> str:
    """Return the display_name select expression with the public alias."""
    expressions = []
    if use_dataset_case:
        expressions.append(
            display_name_case(
                dataset_id_expression,
                parsed_metadata_expression,
                primary_text_expression,
            )
        )
    expressions.extend([
        primary_text_expression,
        indicator_name_expression,
        indicator_code_expression,
    ])
    return "COALESCE(\n" + ",\n".join(expressions) + "\n) AS display_name"


def parsed_metadata_select(parsed_metadata_expression: str = "sd.parsed_metadata") -> str:
    """Return parsed metadata fields with stable aliases."""
    return f"""
    {parsed_metadata_expression} ->> 'measure_type' AS measure_type,
    {parsed_metadata_expression} ->> 'seasonal_adjustment' AS seasonal_adjustment,
    {parsed_metadata_expression} ->> 'unit' AS unit,
    {parsed_metadata_expression} ->> 'base_period' AS base_period,
    {parsed_metadata_expression} ->> 'unit_multiplier' AS unit_multiplier"""


def frequency_select(series_alias: str = "s") -> str:
    """Return frequency fields with stable aliases."""
    return f"""
    {series_alias}.dimension_values ->> 'FREQ' AS frequency_code,
    {series_alias}.dimension_labels -> 'FREQ' ->> 'name' AS frequency_name"""


OBSERVATION_SUMMARY_SELECT = """
    observation_summary.first_period,
    observation_summary.latest_period,
    COALESCE(observation_summary.observation_count, 0) AS observation_count
"""


def search_document_metadata_select(
    document_alias: str = "d",
    dataset_alias: str = "datasets",
) -> str:
    """Return metadata select list for series_search_documents-backed queries."""
    return f"""
    {document_alias}.series_id,
    {document_alias}.dataset_id,
    {dataset_alias}.title AS dataset_title,
    {dataset_alias}.source_url,
    {dataset_alias}.documentation_url,
    {dataset_alias}.metadata_url,
    {dataset_alias}.structure_ref,
    {document_alias}.series_key,
    {document_alias}.indicator_code,
    {document_alias}.indicator_name,
    {document_alias}.primary_text"""
