from __future__ import annotations

import os
from collections.abc import Sequence

from google import genai
from google.genai import types


DEFAULT_GEMINI_EMBEDDING_MODEL = "gemini-embedding-2"
DEFAULT_GEMINI_EMBEDDING_DIMENSION = 768


def require_gemini_environment() -> None:
    required_names = [
        "GOOGLE_CLOUD_PROJECT",
        "GOOGLE_CLOUD_LOCATION",
        "GOOGLE_GENAI_USE_ENTERPRISE",
    ]

    missing = [name for name in required_names if not os.getenv(name)]

    if missing:
        raise RuntimeError(
            "Missing required environment variables: " + ", ".join(missing)
        )


def get_genai_client() -> genai.Client:
    require_gemini_environment()

    return genai.Client()


def embed_texts(
    texts: Sequence[str],
    model: str = DEFAULT_GEMINI_EMBEDDING_MODEL,
    output_dimensionality: int = DEFAULT_GEMINI_EMBEDDING_DIMENSION,
    task_type: str = "RETRIEVAL_DOCUMENT",
    title: str | None = None,
    client: genai.Client | None = None,
) -> list[list[float]]:
    if not texts:
        return []

    genai_client = client or get_genai_client()

    response = genai_client.models.embed_content(
        model=model,
        contents=list(texts),
        config=types.EmbedContentConfig(
            task_type=task_type,
            output_dimensionality=output_dimensionality,
            title=title,
        ),
    )

    if not response.embeddings:
        raise RuntimeError("Gemini returned no embeddings.")

    embeddings: list[list[float]] = []

    for embedding in response.embeddings:
        values = embedding.values

        if values is None:
            raise RuntimeError("Gemini returned an embedding with no values.")

        embeddings.append([float(value) for value in values])

    return embeddings


def embed_query(
    query: str,
    model: str = DEFAULT_GEMINI_EMBEDDING_MODEL,
    output_dimensionality: int = DEFAULT_GEMINI_EMBEDDING_DIMENSION,
    client: genai.Client | None = None,
) -> list[float]:
    """
    Embed a user query for retrieval.

    Stored documents are embedded with RETRIEVAL_DOCUMENT. User queries should
    be embedded with RETRIEVAL_QUERY.
    """
    return embed_texts(
        texts=[query],
        model=model,
        output_dimensionality=output_dimensionality,
        task_type="RETRIEVAL_QUERY",
        client=client,
    )[0]


def vector_literal(values: Sequence[float]) -> str:
    return "[" + ",".join(str(float(value)) for value in values) + "]"
