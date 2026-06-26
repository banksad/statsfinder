from __future__ import annotations

import os
import sys

from google import genai
from google.genai.types import EmbedContentConfig


MODEL = "gemini-embedding-2"
OUTPUT_DIMENSIONALITY = 768


def require_environment() -> None:
    required_names = [
        "GOOGLE_CLOUD_PROJECT",
        "GOOGLE_CLOUD_LOCATION",
        "GOOGLE_GENAI_USE_ENTERPRISE",
    ]

    missing = [
        name
        for name in required_names
        if not os.getenv(name)
    ]

    if missing:
        raise RuntimeError(
            "Missing required environment variables: "
            + ", ".join(missing)
        )


def main() -> int:
    require_environment()

    client = genai.Client()

    text = (
        "Exports of Goods and Services. "
        "This series measures exports of goods and services in UK National Accounts."
    )

    response = client.models.embed_content(
        model=MODEL,
        contents=[text],
        config=EmbedContentConfig(
            task_type="RETRIEVAL_DOCUMENT",
            output_dimensionality=OUTPUT_DIMENSIONALITY,
            title="Exports of Goods and Services",
        ),
    )

    if not response.embeddings:
        raise RuntimeError("Gemini returned no embeddings.")

    values = response.embeddings[0].values

    if values is None:
        raise RuntimeError("Gemini returned an embedding with no values.")

    print(f"Model: {MODEL}")
    print(f"Requested dimensionality: {OUTPUT_DIMENSIONALITY}")
    print(f"Returned values: {len(values)}")
    print(f"First 5 values: {values[:5]}")

    metadata = getattr(response, "metadata", None)
    if metadata is not None:
        print(f"Metadata: {metadata}")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        raise SystemExit(1)
