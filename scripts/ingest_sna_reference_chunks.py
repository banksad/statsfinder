from __future__ import annotations

import argparse
import hashlib
import os
import re
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types
from pypdf import PdfReader

from app.services.postgres import get_connection


SOURCE_ID = "sna2008"
SOURCE_TITLE = "System of National Accounts 2008"
SOURCE_URL = "https://unstats.un.org/unsd/nationalaccount/docs/sna2008.pdf"

DEFAULT_EMBEDDING_MODEL = os.environ.get(
    "REFERENCE_EMBEDDING_MODEL",
    "gemini-embedding-2",
)
DEFAULT_EMBEDDING_DIMENSION = int(
    os.environ.get("REFERENCE_EMBEDDING_DIMENSION", "768")
)


def clean_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def content_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def vector_literal(values: list[float]) -> str:
    return "[" + ",".join(str(float(value)) for value in values) + "]"


def get_genai_client() -> genai.Client:
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "global")

    if not project:
        raise RuntimeError("GOOGLE_CLOUD_PROJECT is not set")

    return genai.Client(
        vertexai=True,
        project=project,
        location=location,
    )


def embed_text(
    client: genai.Client,
    text: str,
    model: str,
    embedding_dim: int,
    task_type: str,
) -> list[float]:
    response = client.models.embed_content(
        model=model,
        contents=text,
        config=types.EmbedContentConfig(
            output_dimensionality=embedding_dim,
            task_type=task_type,
        ),
    )

    return list(response.embeddings[0].values)


def chunk_words(
    text: str,
    max_words: int = 450,
    overlap_words: int = 60,
) -> list[str]:
    words = text.split()

    if not words:
        return []

    chunks: list[str] = []
    start = 0

    while start < len(words):
        end = min(start + max_words, len(words))
        chunk = " ".join(words[start:end])
        chunk = clean_whitespace(chunk)

        if chunk:
            chunks.append(chunk)

        if end == len(words):
            break

        start = max(0, end - overlap_words)

    return chunks


def extract_pdf_chunks(
    pdf_path: Path,
    start_page: int | None = None,
    end_page: int | None = None,
) -> list[dict[str, Any]]:
    reader = PdfReader(str(pdf_path))
    chunks: list[dict[str, Any]] = []

    first_index = 0 if start_page is None else max(0, start_page - 1)
    last_index = len(reader.pages) if end_page is None else min(len(reader.pages), end_page)

    for page_index in range(first_index, last_index):
        page = reader.pages[page_index]
        page_text = page.extract_text() or ""
        page_text = clean_whitespace(page_text)

        if len(page_text) < 80:
            continue

        page_number = page_index + 1

        for chunk_index, chunk_text in enumerate(chunk_words(page_text)):
            chunks.append(
                {
                    "source_id": SOURCE_ID,
                    "source_title": SOURCE_TITLE,
                    "source_url": SOURCE_URL,
                    "page_number": page_number,
                    "chunk_index": chunk_index,
                    "chunk_text": chunk_text,
                    "content_hash": content_hash(
                        f"{SOURCE_ID}|{page_number}|{chunk_index}|{chunk_text}"
                    ),
                }
            )

    return chunks


def upsert_reference_chunk(chunk: dict[str, Any]) -> int:
    sql = """
        INSERT INTO reference_chunks (
            source_id,
            source_title,
            source_url,
            page_number,
            chunk_index,
            chunk_text,
            content_hash
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (content_hash)
        DO UPDATE SET
            source_id = EXCLUDED.source_id,
            source_title = EXCLUDED.source_title,
            source_url = EXCLUDED.source_url,
            page_number = EXCLUDED.page_number,
            chunk_index = EXCLUDED.chunk_index,
            chunk_text = EXCLUDED.chunk_text
        RETURNING chunk_id;
    """

    params = (
        chunk["source_id"],
        chunk["source_title"],
        chunk["source_url"],
        chunk["page_number"],
        chunk["chunk_index"],
        chunk["chunk_text"],
        chunk["content_hash"],
    )

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            conn.commit()

    return int(row["chunk_id"])


def embedding_exists(
    chunk_id: int,
    model: str,
    embedding_dim: int,
    hash_value: str,
) -> bool:
    sql = """
        SELECT 1
        FROM reference_chunk_embeddings
        WHERE chunk_id = %s
          AND model = %s
          AND embedding_dim = %s
          AND content_hash = %s
        LIMIT 1;
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (chunk_id, model, embedding_dim, hash_value))
            return cur.fetchone() is not None


def upsert_reference_embedding(
    chunk_id: int,
    model: str,
    embedding_dim: int,
    hash_value: str,
    embedding: list[float],
) -> None:
    sql = """
        INSERT INTO reference_chunk_embeddings (
            chunk_id,
            model,
            embedding_dim,
            content_hash,
            embedding
        )
        VALUES (%s, %s, %s, %s, %s::vector)
        ON CONFLICT (chunk_id, model, embedding_dim)
        DO UPDATE SET
            content_hash = EXCLUDED.content_hash,
            embedding = EXCLUDED.embedding,
            created_at = now();
    """

    params = (
        chunk_id,
        model,
        embedding_dim,
        hash_value,
        vector_literal(embedding),
    )

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            conn.commit()


def ingest_sna_chunks(
    pdf_path: Path,
    start_page: int | None,
    end_page: int | None,
    limit: int | None,
    force: bool,
) -> None:
    chunks = extract_pdf_chunks(
        pdf_path=pdf_path,
        start_page=start_page,
        end_page=end_page,
    )

    if limit is not None:
        chunks = chunks[:limit]

    print(f"Prepared {len(chunks)} chunks from {pdf_path}")

    client = get_genai_client()

    embedded = 0
    skipped = 0

    for index, chunk in enumerate(chunks, start=1):
        chunk_id = upsert_reference_chunk(chunk)

        if not force and embedding_exists(
            chunk_id=chunk_id,
            model=DEFAULT_EMBEDDING_MODEL,
            embedding_dim=DEFAULT_EMBEDDING_DIMENSION,
            hash_value=chunk["content_hash"],
        ):
            skipped += 1
            continue

        embedding = embed_text(
            client=client,
            text=chunk["chunk_text"],
            model=DEFAULT_EMBEDDING_MODEL,
            embedding_dim=DEFAULT_EMBEDDING_DIMENSION,
            task_type="RETRIEVAL_DOCUMENT",
        )

        upsert_reference_embedding(
            chunk_id=chunk_id,
            model=DEFAULT_EMBEDDING_MODEL,
            embedding_dim=DEFAULT_EMBEDDING_DIMENSION,
            hash_value=chunk["content_hash"],
            embedding=embedding,
        )

        embedded += 1

        if index % 25 == 0:
            print(f"Processed {index}/{len(chunks)} chunks")

    print(f"Embedded: {embedded}")
    print(f"Skipped existing: {skipped}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ingest SNA 2008 PDF pages as embedded reference chunks."
    )

    parser.add_argument(
        "--pdf",
        type=Path,
        default=Path("data/reference/sna2008.pdf"),
        help="Path to SNA 2008 PDF.",
    )
    parser.add_argument(
        "--start-page",
        type=int,
        default=None,
        help="Optional 1-based PDF page number to start from.",
    )
    parser.add_argument(
        "--end-page",
        type=int,
        default=None,
        help="Optional 1-based PDF page number to end at.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional maximum number of chunks to ingest.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-embed chunks even if matching embeddings already exist.",
    )

    return parser


def main() -> None:
    args = build_parser().parse_args()

    ingest_sna_chunks(
        pdf_path=args.pdf,
        start_page=args.start_page,
        end_page=args.end_page,
        limit=args.limit,
        force=args.force,
    )


if __name__ == "__main__":
    main()
