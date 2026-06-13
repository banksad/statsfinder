from pathlib import Path
import argparse
import json
import re


ENRICHED_SERIES_PATH = Path("data/processed/nag_series_enriched.json")


def normalise_text(text: str) -> str:
    """
    Convert text into a simpler form for matching.

    Example:
      "Quarterly Nominal GDP!" -> "quarterly nominal gdp"
    """
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def tokenise(text: str) -> list[str]:
    """
    Split normalised text into simple word tokens.
    """
    normalised = normalise_text(text)

    if not normalised:
        return []

    return normalised.split(" ")


def load_series_records(path: Path) -> list[dict]:
    """
    Load enriched series records from JSON.
    """
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def score_record(query_tokens: list[str], record: dict) -> tuple[int, list[str]]:
    """
    Score a series record against the query.

    Returns:
      score, matched_tokens

    This is deliberately simple:
      - each query token found in the search text gets 1 point
      - exact phrase match gets a bonus
      - matched tokens are returned so we can debug why a result appeared

    Later, embeddings and/or Postgres full-text search will replace or augment this.
    """
    search_text = record.get("search_text", "")
    normalised_search_text = normalise_text(search_text)

    score = 0
    matched_tokens = []

    for token in query_tokens:
        if token in normalised_search_text:
            score += 1
            matched_tokens.append(token)

    query_phrase = " ".join(query_tokens)

    if query_phrase and query_phrase in normalised_search_text:
        score += 5

    return score, matched_tokens


def get_dimension_label(record: dict, dimension_name: str) -> str | None:
    """
    Safely get the official label for a dimension.

    Example:
      dimension_name="FREQ" -> "Quarterly"
    """
    dimension_labels = record.get("dimension_labels", {})
    dimension = dimension_labels.get(dimension_name, {})
    return dimension.get("name")


def get_dimension_code(record: dict, dimension_name: str) -> str | None:
    """
    Safely get the raw code for a dimension.

    Example:
      dimension_name="FREQ" -> "Q"
    """
    dimension_values = record.get("dimension_values", {})
    return dimension_values.get(dimension_name)


def format_result(
    rank: int,
    score: int,
    matched_tokens: list[str],
    record: dict,
) -> str:
    """
    Format one search result for terminal output.
    """
    indicator_code = get_dimension_code(record, "INDICATOR")
    indicator_label = get_dimension_label(record, "INDICATOR")
    frequency_label = get_dimension_label(record, "FREQ")
    reference_area_label = get_dimension_label(record, "REF_AREA")
    unit_multiplier_label = get_dimension_label(record, "UNIT_MULT")
    base_period_code = get_dimension_code(record, "BASE_PER")

    matched_tokens_text = ", ".join(matched_tokens) if matched_tokens else "None"

    lines = [
        f"{rank}. {indicator_code}",
        f"   Score: {score}",
        f"   Matched tokens: {matched_tokens_text}",
        f"   Indicator: {indicator_label}",
        f"   Geography: {reference_area_label}",
        f"   Frequency: {frequency_label}",
        f"   Unit multiplier: {unit_multiplier_label}",
        f"   Base period: {base_period_code}",
        f"   Series key: {record.get('series_key')}",
    ]

    return "\n".join(lines)


def search_series(
    query: str,
    records: list[dict],
    limit: int,
) -> list[tuple[int, list[str], dict]]:
    """
    Search enriched series records and return ranked matches.
    """
    query_tokens = tokenise(query)

    scored_records = []

    for record in records:
        score, matched_tokens = score_record(query_tokens, record)

        if score > 0:
            scored_records.append((score, matched_tokens, record))

    scored_records.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    return scored_records[:limit]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Search enriched SDMX series metadata."
    )

    parser.add_argument(
        "query",
        help="Plain-English search query, for example: 'quarterly nominal GDP'",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Maximum number of results to show. Default: 5.",
    )

    args = parser.parse_args()

    records = load_series_records(ENRICHED_SERIES_PATH)

    results = search_series(
        query=args.query,
        records=records,
        limit=args.limit,
    )

    print(f"Query: {args.query}")
    print(f"Records searched: {len(records)}")
    print(f"Results found: {len(results)}")

    if not results:
        print("\nNo matching series found.")
        return

    print("\nTop results")
    print("-----------")

    for rank, (score, matched_tokens, record) in enumerate(results, start=1):
        print(format_result(rank, score, matched_tokens, record))
        print()


if __name__ == "__main__":
    main()
