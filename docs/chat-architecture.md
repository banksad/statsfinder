# Stats Finder Chat Architecture

## Purpose

Chat is an experimental source-grounded assistant for StatsFinder. It should help
users ask plain-language questions and then route them back to official series,
metadata, observations, and reference passages.

Chat is not the product centre. StatsFinder should remain a lightweight Search,
Browse, API, and Export service. Chat is useful only when it makes those simple,
source-backed workflows easier to use.

## Core principle

The central rule still applies:

> The LLM may interpret. The database must answer.

Chat may retrieve candidate series, retrieve reference passages, summarise the
retrieved context, and suggest where a user should inspect the data next. It must
not invent observations, overwrite official metadata, or present generated prose
as a substitute for source-backed records.

## Current implementation

Current routes:

```text
GET  /chat
POST /v1/chat/retrieve
POST /v1/chat/ask
```

The browser page is server-rendered with Jinja2 and enhanced with small plain
JavaScript. The API accepts a question and optional `dataset_id` filter.

Current retrieval flow:

```text
question
  → small query normalisation and domain-specific expansions
  → semantic search over stored series metadata embeddings
  → reference chunk search over ingested SNA passages
  → short grounded response with candidate source-backed series
```

The implementation uses the configured Gemini chat model for generation and the
same semantic search service used by the Search and Browse surfaces. Missing
Google Cloud or embedding configuration should fail as an optional feature, not
make the whole application conceptually dependent on chat.

## Design rules

Chat should stay:

* small;
* explicit about retrieved context;
* grounded in source-backed series and reference passages;
* secondary to Search, Browse, API, and Export;
* easy to remove or disable if it stops simplifying the product.

Avoid:

* broad chatbot behaviour;
* unsupported statistical claims;
* hiding source metadata behind generated prose;
* complex conversational state;
* extra infrastructure beyond the existing FastAPI, PostgreSQL, pgvector, and
  small service-module pattern.

## Lightweight chat rule

If chat cannot answer from retrieved source-backed context, it should say so and
point the user to search or browse. The simplest trustworthy response is better
than a clever but unsupported one.
