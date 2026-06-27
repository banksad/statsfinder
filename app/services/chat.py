from __future__ import annotations

import json
import os
import re
from typing import Any
from urllib.parse import quote

from google.genai import types

from app.services.gemini import get_genai_client
from app.services.reference_search import search_reference_chunks
from app.services.semantic_search import (
    DEFAULT_SEMANTIC_DIMENSION,
    DEFAULT_SEMANTIC_MODEL,
    semantic_search_series,
)


DEFAULT_CHAT_MODEL = os.environ.get("GEMINI_CHAT_MODEL", "gemini-2.5-pro")


def normalise_query(value: str) -> str:
    return " ".join(value.strip().split())


def build_series_url(row: dict[str, Any]) -> str:
    dataset_id = quote(str(row["dataset_id"]), safe="")
    indicator_code = quote(str(row["indicator_code"]), safe="")
    series_id = row.get("series_id")

    url = f"/series/{dataset_id}/{indicator_code}"

    if series_id is not None:
        url += f"?series_id={quote(str(series_id), safe='')}"

    return url


def extract_comparison_terms(question: str) -> list[str]:
    cleaned = normalise_query(question)

    match = re.search(
        r"\bdifference between (?P<left>.+?) and (?P<right>.+?)(?:\?|$)",
        cleaned,
        flags=re.IGNORECASE,
    )

    if not match:
        return []

    left = match.group("left").strip(" .?")
    right = match.group("right").strip(" .?")

    terms = [left, right]
    expanded: list[str] = []

    for term in terms:
        lower_term = term.lower()

        if "net lending" in lower_term and "borrowing" not in lower_term:
            expanded.append(f"{term} borrowing")
        elif "revenue" in lower_term and "government" not in lower_term:
            expanded.append(f"government {term}")
        else:
            expanded.append(term)

    return expanded


def build_retrieval_queries(question: str) -> list[str]:
    cleaned = normalise_query(question)

    queries = []
    queries.extend(extract_comparison_terms(cleaned))
    queries.append(cleaned)

    # Small fiscal-domain expansions for this first prototype.
    lower_question = cleaned.lower()

    if "net lending" in lower_question:
        queries.append("general government net lending borrowing fiscal balance")

    if "revenue" in lower_question:
        queries.append("general government revenue taxes")

    if (
        "government debt" in lower_question
        or "general government debt" in lower_question
    ):
        queries.append("general government debt at nominal value")
        queries.append("general government gross debt liabilities stock")
        queries.append("general government debt by currency residual maturity")

    deduped: list[str] = []

    for query in queries:
        query = normalise_query(query)

        if query and query not in deduped:
            deduped.append(query)

    return deduped


def retrieve_sdmx_series(
    question: str,
    dataset_id: str | None = None,
    limit_per_query: int = 5,
    max_results: int = 12,
    protected_per_query: int = 2,
) -> tuple[list[dict[str, Any]], list[str]]:
    retrieval_queries = build_retrieval_queries(question)
    by_series_id: dict[int, dict[str, Any]] = {}
    per_query_results: list[list[dict[str, Any]]] = []

    for retrieval_query in retrieval_queries:
        rows = semantic_search_series(
            query=retrieval_query,
            model=DEFAULT_SEMANTIC_MODEL,
            embedding_dim=DEFAULT_SEMANTIC_DIMENSION,
            limit=limit_per_query,
            dataset_id=dataset_id,
            min_similarity=0.0,
            include_debug=False,
        )

        per_query_rows: list[dict[str, Any]] = []

        for row in rows:
            series_id = row.get("series_id")

            if series_id is None:
                continue

            if series_id not in by_series_id:
                row["series_url"] = build_series_url(row)
                row["matched_retrieval_queries"] = [retrieval_query]
                by_series_id[series_id] = row
            else:
                by_series_id[series_id]["matched_retrieval_queries"].append(
                    retrieval_query
                )

                existing_score = by_series_id[series_id].get("similarity_score") or 0
                new_score = row.get("similarity_score") or 0

                if new_score > existing_score:
                    by_series_id[series_id]["similarity_score"] = new_score

            per_query_rows.append(by_series_id[series_id])

        per_query_results.append(per_query_rows)

    protected: list[dict[str, Any]] = []

    for rows in per_query_results:
        for row in rows[:protected_per_query]:
            if row not in protected:
                protected.append(row)

            if len(protected) >= max_results:
                return protected[:max_results], retrieval_queries

    ranked = list(by_series_id.values())

    ranked.sort(
        key=lambda row: (
            row.get("similarity_score") or 0,
            row.get("observation_count") or 0,
        ),
        reverse=True,
    )

    results = protected[:]

    for row in ranked:
        if row not in results:
            results.append(row)

        if len(results) >= max_results:
            break

    return results[:max_results], retrieval_queries




def retrieve_reference_passages(
    question: str,
    limit: int = 3,
) -> list[dict[str, Any]]:
    return search_reference_chunks(
        query=question,
        limit=limit,
        source_id="sna2008",
    )


def build_chat_retrieval_bundle(
    question: str,
    dataset_id: str | None = None,
) -> dict[str, Any]:
    series_matches, retrieval_queries = retrieve_sdmx_series(
        question=question,
        dataset_id=dataset_id,
    )

    reference_matches = retrieve_reference_passages(
        question=question,
        limit=3,
    )

    return {
        "question": question,
        "dataset_id": dataset_id,
        "retrieval_queries": retrieval_queries,
        "series_matches": series_matches,
        "reference_matches": reference_matches,
    }


def slim_series(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "series_id": row.get("series_id"),
        "dataset_id": row.get("dataset_id"),
        "dataset_title": row.get("dataset_title"),
        "indicator_code": row.get("indicator_code"),
        "display_name": (
            row.get("display_name")
            or row.get("primary_text")
            or row.get("indicator_name")
            or row.get("indicator_code")
        ),
        "indicator_name": row.get("indicator_name"),
        "frequency_name": row.get("frequency_name"),
        "first_period": row.get("first_period"),
        "latest_period": row.get("latest_period"),
        "observation_count": row.get("observation_count"),
        "similarity_score": row.get("similarity_score"),
        "series_url": row.get("series_url"),
    }


def slim_reference(row: dict[str, Any]) -> dict[str, Any]:
    text = row.get("chunk_text") or ""

    return {
        "chunk_id": row.get("chunk_id"),
        "source_id": row.get("source_id"),
        "source_title": row.get("source_title"),
        "source_url": row.get("source_url"),
        "page_number": row.get("page_number"),
        "similarity_score": row.get("similarity_score"),
        "chunk_text": text[:1800],
    }


def build_generation_prompt(bundle: dict[str, Any]) -> str:
    question = bundle["question"]

    candidate_series = [
        candidate_series_for_prompt(row)
        for row in bundle.get("series_matches", [])[:12]
    ]

    candidate_references = [
        candidate_reference_for_prompt(row)
        for row in bundle.get("reference_matches", [])[:5]
    ]

    context = {
        "question": question,
        "candidate_series": candidate_series,
        "candidate_references": candidate_references,
    }

    return f"""
You are StatsFinder Chat, a source-grounded assistant for official statistics.

You are given:
1. A user question.
2. Candidate SDMX data series retrieved from the database.
3. Candidate reference passages retrieved from statistical manuals or methodology documents.

Your job:
- Answer the user's question using only the supplied candidate series and reference passages.
- Select up to 4 directly relevant SDMX series by series_id.
- Select up to 3 directly relevant reference passages by chunk_id.
- Prefer exact conceptual matches over merely related macroeconomic concepts.
- Prefer broad headline series over components unless the user asks for components.
- Do not invent dataset IDs, indicator codes, URLs, values, periods, page numbers, or series IDs.
- Do not claim a data value unless it appears in the supplied context.
- Keep the answer concise and useful.
- Quote at most 25 words from any one reference passage.

Return ONLY valid JSON with this exact shape:

{{
  "answer": "A concise answer in plain text. Include a short reference quote if useful.",
  "selected_series_ids": [123, 456],
  "selected_reference_chunk_ids": [789],
  "caveat": "One sentence explaining what should be checked in the linked series or sources."
}}

Context JSON:
{json.dumps(context, ensure_ascii=False, indent=2)}
""".strip()


def extract_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()

    if cleaned.startswith("```"):
        cleaned = re.sub(
            r"^```(?:json)?", "", cleaned.strip(), flags=re.IGNORECASE
        ).strip()
        cleaned = re.sub(r"```$", "", cleaned.strip()).strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)

        if not match:
            raise

        parsed = json.loads(match.group(0))

    if not isinstance(parsed, dict):
        raise ValueError("Gemini response JSON was not an object")

    return parsed


def candidate_series_for_prompt(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "series_id": row.get("series_id"),
        "display_name": row.get("display_name"),
        "dataset_id": row.get("dataset_id"),
        "dataset_title": row.get("dataset_title"),
        "indicator_code": row.get("indicator_code"),
        "indicator_name": row.get("indicator_name"),
        "frequency_name": row.get("frequency_name"),
        "frequency_code": row.get("frequency_code"),
        "unit": row.get("unit"),
        "first_period": row.get("first_period"),
        "latest_period": row.get("latest_period"),
        "observation_count": row.get("observation_count"),
        "similarity_score": row.get("similarity_score"),
    }


def candidate_reference_for_prompt(row: dict[str, Any]) -> dict[str, Any]:
    chunk_text = row.get("chunk_text") or ""

    return {
        "chunk_id": row.get("chunk_id"),
        "source_title": row.get("source_title"),
        "source_url": row.get("source_url"),
        "page_number": row.get("page_number"),
        "chunk_text": chunk_text[:1600],
        "similarity_score": row.get("similarity_score"),
    }


def generate_chat_answer(bundle: dict[str, Any]) -> dict[str, Any]:
    prompt = build_generation_prompt(bundle)

    client = get_genai_client()

    response = client.models.generate_content(
        model=DEFAULT_CHAT_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.1,
            max_output_tokens=2000,
        ),
    )

    response_text = response.text or ""

    try:
        parsed = extract_json_object(response_text)
    except Exception:
        parsed = {
            "answer": response_text.strip(),
            "selected_series_ids": [],
            "selected_reference_chunk_ids": [],
            "caveat": "The generated answer could not be parsed as structured JSON, so no series were selected.",
        }

    answer = str(parsed.get("answer") or "").strip()
    caveat = str(parsed.get("caveat") or "").strip()

    selected_series_ids = parsed.get("selected_series_ids") or []
    selected_reference_chunk_ids = parsed.get("selected_reference_chunk_ids") or []

    if not isinstance(selected_series_ids, list):
        selected_series_ids = []

    if not isinstance(selected_reference_chunk_ids, list):
        selected_reference_chunk_ids = []

    return {
        "answer": answer,
        "selected_series_ids": selected_series_ids,
        "selected_reference_chunk_ids": selected_reference_chunk_ids,
        "caveat": caveat,
        "raw_model_response": response_text,
    }


def normalise_int_id(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def validate_selected_series(
    candidate_series: list[dict[str, Any]],
    selected_series_ids: list[Any],
    fallback_limit: int = 3,
) -> list[dict[str, Any]]:
    candidate_by_id: dict[int, dict[str, Any]] = {}

    for row in candidate_series:
        series_id = normalise_int_id(row.get("series_id"))

        if series_id is not None:
            candidate_by_id[series_id] = row

    selected: list[dict[str, Any]] = []

    for raw_id in selected_series_ids:
        series_id = normalise_int_id(raw_id)

        if series_id is None:
            continue

        row = candidate_by_id.get(series_id)

        if row and row not in selected:
            selected.append(row)

    if selected:
        return selected

    return candidate_series[:fallback_limit]


def validate_selected_references(
    candidate_references: list[dict[str, Any]],
    selected_reference_chunk_ids: list[Any],
    fallback_limit: int = 2,
) -> list[dict[str, Any]]:
    candidate_by_id: dict[int, dict[str, Any]] = {}

    for row in candidate_references:
        chunk_id = normalise_int_id(row.get("chunk_id"))

        if chunk_id is not None:
            candidate_by_id[chunk_id] = row

    selected: list[dict[str, Any]] = []

    for raw_id in selected_reference_chunk_ids:
        chunk_id = normalise_int_id(raw_id)

        if chunk_id is None:
            continue

        row = candidate_by_id.get(chunk_id)

        if row and row not in selected:
            selected.append(row)

    if selected:
        return selected

    return candidate_references[:fallback_limit]


def ask_chat(
    question: str,
    dataset_id: str | None = None,
) -> dict[str, Any]:
    bundle = build_chat_retrieval_bundle(
        question=question,
        dataset_id=dataset_id,
    )

    generation = generate_chat_answer(bundle)

    selected_series = validate_selected_series(
        candidate_series=bundle.get("series_matches", []),
        selected_series_ids=generation.get("selected_series_ids", []),
    )

    selected_references = validate_selected_references(
        candidate_references=bundle.get("reference_matches", []),
        selected_reference_chunk_ids=generation.get("selected_reference_chunk_ids", []),
    )

    answer_parts = []

    if generation.get("answer"):
        answer_parts.append(generation["answer"])

    if generation.get("caveat"):
        answer_parts.append(f"Caveat: {generation['caveat']}")

    return {
        "question": question,
        "dataset_id": dataset_id,
        "model": DEFAULT_CHAT_MODEL,
        "answer": "\n\n".join(answer_parts).strip(),
        "selected_series": selected_series,
        "selected_references": selected_references,
        "debug": {
            "retrieval_queries": bundle.get("retrieval_queries", []),
            "candidate_series": bundle.get("series_matches", []),
            "candidate_references": bundle.get("reference_matches", []),
            "selected_series_ids": generation.get("selected_series_ids", []),
            "selected_reference_chunk_ids": generation.get(
                "selected_reference_chunk_ids", []
            ),
            "raw_model_response": generation.get("raw_model_response"),
        },
    }
