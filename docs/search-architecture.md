# Stats Finder Search Architecture

## Purpose

Search is the primary discovery experience in Stats Finder.

It helps users find official statistical series when they do not know the exact dataset, indicator code, SDMX series key, or official terminology.

The core search idea is:

> Help users find the right official series by meaning, while keeping results grounded in source metadata and official observations.

Search should be fast, lightweight, explainable, and source-backed.

It should support the wider Stats Finder product goal:

> A lightweight, discovery layer for UK official statistics, grounded in SDMX metadata and enhanced with semantic search.

## Relationship to Browse

Stats Finder has two first-class discovery modes.

```text
Search:
  “I know roughly what I want, but not the official code or label.”

Browse:
  “I know the topic area and want to explore what exists.”
```

Search is query-driven.

Browse is structure-driven.

Both should resolve to the same core objects:

* datasets
* series
* observations
* codelists
* metadata
* source URLs
* provenance
* export bundles

Search should also be able to return Browse groups where useful.

For example, a search for:

```text
industry GVA
```

could return:

```text
Series matches:
  GVA: Manufacturing
  GVA: Construction

Browse group matches:
  GVA by industry
```

## Search principles

## 1. Search metadata, not raw observations

Search should operate primarily over series metadata, not observation values.

The search index should include:

* dataset title
* dataset ID
* indicator code
* indicator label
* dimension values
* dimension labels
* codelist labels
* units
* frequency
* geography
* source metadata
* documentation links
* search-only aliases

Observation values should be retrieved only after the user selects a series or export group.

## 2. Official metadata remains separate from search enrichment

Search may use enriched terms to improve findability.

Example:

```text
Official label:
  Non-profit institutions serving households

Search aliases:
  charities
  charity sector
  voluntary sector
  non-profit sector
```

The official label should never be overwritten.

Search-only enrichment should be clearly stored as search metadata, not as official source metadata.

## 3. The database must answer

Search can use AI to help interpret user intent, generate embeddings, or create search-only aliases.

But the selected result must always resolve to official metadata and source-backed observations.

The central rule is:

> The LLM may interpret. The database must answer.

## 4. Explain why a result matched

Search should eventually show lightweight match explanations.

Example:

```text
Matched because:
  "charity sector" matched search aliases for NPISH.
```

or:

```text
Matched because:
  "inflation" matched Consumer Price Index metadata.
```

This improves trust and makes semantic search less mysterious.

## 5. Keep search fast

Search should feel immediate.

The initial search architecture should stay PostgreSQL-first:

* exact match
* simple lexical search
* PostgreSQL full-text search
* pgvector semantic search

Additional infrastructure such as Elasticsearch should only be considered if PostgreSQL cannot meet clear performance or ranking requirements.

## Search user experience

The Search page should be simple.

```text
Search   Browse   API
```

A search page should include:

* search box
* dataset filter
* result list
* clear metadata
* source/provenance hints
* add-to-basket checkbox
* export selected action

Example:

```text
Search: "inflation"

[ ] Consumer Price Index, all items
    Dataset: UK Consumer Price Index
    Frequency: Monthly
    Unit: Index
    Source: ONS/IMF SDMX

[ ] Consumer Prices Index including owner occupiers' housing costs
    Dataset: UK Consumer Price Index
    Frequency: Monthly
    Unit: Index
    Source: ONS/IMF SDMX
```

Search should support the workflow:

```text
search
→ inspect result
→ add to basket
→ search again
→ add another series
→ download selected
```

The selected basket should remain browser-side and store only stable series references.

## Search result types

Search should eventually support multiple result types.

## Series result

A normal statistical series.

```json
{
  "result_type": "series",
  "dataset_id": "CPI_GBR",
  "series_key": "M.GB.PCPI_IX",
  "indicator_code": "PCPI_IX",
  "title": "Consumer Price Index, all items",
  "frequency": "Monthly",
  "unit": "Index",
  "source": "ONS/IMF SDMX"
}
```

## Dataset result

A dataset or dataflow.

```json
{
  "result_type": "dataset",
  "dataset_id": "CPI_GBR",
  "title": "UK Consumer Price Index",
  "series_count": 2
}
```

## Browse group result

A structured discovery group.

```json
{
  "result_type": "browse_node",
  "slug": "gva-by-industry",
  "title": "GVA by industry",
  "member_count": 50
}
```

The first implementation can return only series results. Dataset and Browse group results can be added later.

## Search stages

Search should evolve in stages.

## Stage 1: Exact and simple lexical search

Initial search should support:

* indicator code match
* dataset ID match
* indicator label match
* dimension label match
* simple `ILIKE` search over `search_text`

This is easy to debug and good enough for the early prototype.

Example API:

```text
GET /v1/series/search?q=inflation&limit=20
```

## Stage 2: PostgreSQL full-text search

Next, Stats Finder should generate a richer search document for each series and index it with PostgreSQL full-text search.

This supports better ranking than simple `ILIKE`.

Possible table:

```sql
CREATE TABLE series_search_documents (
    search_document_id BIGSERIAL PRIMARY KEY,
    dataset_id TEXT NOT NULL,
    series_key TEXT NOT NULL,
    indicator_code TEXT,
    official_text TEXT NOT NULL,
    enriched_text TEXT,
    embedding_text TEXT NOT NULL,
    search_vector TSVECTOR,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (dataset_id, series_key)
);
```

Index:

```sql
CREATE INDEX idx_series_search_documents_vector
ON series_search_documents
USING GIN (search_vector);
```

The `official_text` should be deterministic and source-backed.

The `enriched_text` should contain search-only aliases or curated terms.

The `embedding_text` should be the combined text used for semantic embedding.

## Stage 3: Semantic search with pgvector

Semantic search should help users find series when they do not know the official terminology.

Examples:

```text
"charity sector"
  → Non-profit institutions serving households

"cost of living"
  → Consumer price inflation

"economic output"
  → Gross domestic product / gross value added

"household spending"
  → Household final consumption expenditure
```

The vector should represent metadata documents, not observation values.

Later table extension:

```sql
ALTER TABLE series_search_documents
ADD COLUMN embedding_model TEXT;

ALTER TABLE series_search_documents
ADD COLUMN embedding vector(768);
```

The vector dimension should match the chosen embedding model.

## Stage 4: Hybrid ranking

Eventually, search should combine several signals:

```text
exact code match
official label match
alias match
PostgreSQL full-text rank
vector similarity
dataset priority
data availability
metadata quality
```

A simple ranking model might be:

```text
exact indicator code match      +100
exact dataset ID match          +80
official title lexical match    +50
alias match                     +40
full-text rank                  variable
vector similarity               variable
has observations                +10
```

This can remain simple and explainable.

## Stage 5: Lightweight query interpretation

Later, a small LLM-assisted interpretation step may be useful.

Example user query:

```text
charity sector spending quarterly
```

The query interpreter might extract:

```json
{
  "concepts": ["charity sector", "spending"],
  "frequency": "quarterly",
  "possible_official_terms": ["NPISH", "final consumption expenditure"]
}
```

This should be optional and should not be required for basic search.

The search engine should still work without an LLM.

## Search document generation

Stats Finder should generate one search document per official series.

Example search document:

```text
Dataset: UK Consumer Price Index
Dataset ID: CPI_GBR
Indicator code: PCPI_IX
Indicator label: Consumer Price Index, all items
Frequency: Monthly
Reference area: United Kingdom
Unit: Index
Source: ONS/IMF SDMX
Documentation: ...
Useful terms: inflation, consumer prices, price index, cost of living
```

The document should be generated from:

* official dataset metadata
* series dimensions
* codelist labels
* source URLs
* curated aliases
* optional LLM-enriched search terms

The document should be inspectable. If search behaves badly, an engineer should be able to read the search document and understand why.

## Search-only aliases

Aliases can be curated manually or generated by an LLM and reviewed.

Possible table:

```sql
CREATE TABLE series_search_aliases (
    alias_id BIGSERIAL PRIMARY KEY,
    dataset_id TEXT NOT NULL,
    series_key TEXT NOT NULL,
    alias TEXT NOT NULL,
    source_type TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (dataset_id, series_key, alias)
);
```

Possible `source_type` values:

```text
manual
llm_generated
statsfinder_curated
official_synonym
```

Aliases must not replace official labels.

They only improve search.

## API design

Initial endpoint:

```text
GET /v1/series/search?q={query}&limit={limit}&dataset_id={dataset_id}
```

Future version:

```text
GET /v1/search?q={query}&limit={limit}&types=series,dataset,browse_node
```

Example response:

```json
{
  "query": "inflation",
  "results": [
    {
      "result_type": "series",
      "dataset_id": "CPI_GBR",
      "series_key": "M.GB.PCPI_IX",
      "indicator_code": "PCPI_IX",
      "title": "Consumer Price Index, all items",
      "frequency": "Monthly",
      "unit": "Index",
      "score": 0.92,
      "match_reason": "Matched official metadata and inflation alias."
    }
  ]
}
```

Search should remain read-only.

It should not create user state.

## HTML routes

Suggested routes:

```text
/search
```

The homepage may also contain a search box, but `/search` should be the canonical search page.

Possible route pattern:

```text
/search?q=inflation
```

This makes searches linkable.

Example:

```text
https://statsfinder.uk/search?q=inflation
```

The search page should support:

* query parameter
* dataset filter
* pagination
* selected-series basket
* export selected action

## Selected-series basket

Search should support multi-series selection without server sessions.

The browser stores selected series references in localStorage.

Example:

```json
[
  {"dataset_id": "CPI_GBR", "series_key": "M.GB.PCPI_IX"},
  {"dataset_id": "NAG_GBR", "series_key": "Q.GB.NGDP_R_SA_XDC"}
]
```

The basket should store identifiers only, not observation data.

The export endpoint receives the selected series and generates the requested file.

This avoids:

* user accounts
* dashboards
* server-side sessions
* stateful frontend frameworks

## Export integration

Search should integrate with the export API.

User flow:

```text
Search "inflation"
→ select CPI
→ Search "GDP"
→ select GDP
→ Download selected as CSVW
```

Export request:

```json
{
  "format": "csvw",
  "series": [
    {"dataset_id": "CPI_GBR", "series_key": "M.GB.PCPI_IX"},
    {"dataset_id": "NAG_GBR", "series_key": "Q.GB.NGDP_R_SA_XDC"}
  ]
}
```

The export engine retrieves official observations and metadata from the database.

## Performance expectations

A catalogue of 8,000 series is small for PostgreSQL.

Search should remain fast if the design is disciplined:

* search metadata, not observations
* index `dataset_id`
* index `series_key`
* index `indicator_code`
* use PostgreSQL full-text search for text
* use pgvector only on search documents
* paginate results
* keep result payloads small

Useful indexes:

```sql
CREATE INDEX idx_series_dataset_key
ON series (dataset_id, series_key);

CREATE INDEX idx_series_indicator_code
ON series (indicator_code);

CREATE INDEX idx_observations_series_time
ON observations (series_id, time_period);
```

For full-text search:

```sql
CREATE INDEX idx_series_search_documents_tsv
ON series_search_documents
USING GIN (search_vector);
```

For semantic search, add a pgvector index only when needed.

## Search quality evaluation

Stats Finder should eventually have a small set of test queries.

Example:

```text
inflation
GDP
household spending
charity sector
industry GVA
manufacturing output
cost of living
public sector borrowing
```

Each query should have expected high-quality results.

A future script could run:

```bash
python3 -m scripts.evaluate_search_quality
```

Example output:

```text
Query: inflation
  expected: CPI_GBR / PCPI_IX
  rank: 1
  pass: yes

Query: charity sector
  expected: NPISH-related series
  rank: 2
  pass: yes
```

This helps avoid regressions as search becomes more sophisticated.

## Search provenance

Search results should show enough provenance to build trust.

Each result should include:

* dataset ID
* source name
* source URL
* documentation URL where available
* series key
* structure reference where available
* whether match came from official metadata or search-only enrichment

Example:

```text
Matched via:
  search-only alias: "charity sector"

Official label:
  Non-profit institutions serving households
```

This distinction is important.

## What Search should avoid

Search should not become:

* a chatbot answer generator
* a black-box ranking system
* a dashboard builder
* a full web search engine
* a separate search platform too early
* a place where AI-generated labels overwrite official labels
* a system that searches observation values by default
* a system that returns generated statistical claims

Search should remain:

```text
fast
small
metadata-first
source-grounded
explainable
export-friendly
```

## Relationship to CLI and MCP

The CLI and MCP services should use the same search API.

CLI example:

```bash
statsfinder search "inflation"
```

MCP tool example:

```text
search_series(query="inflation")
```

Neither the CLI nor MCP server should implement their own ranking logic.

They should call Stats Finder Core.

## Implementation stages

### Stage 1: Improve current search page

* canonical `/search` route
* dataset filter
* result list
* checkboxes
* basket count
* link to series page

### Stage 2: Add search document generation

* create deterministic search text per series
* inspect generated documents
* store in database or regenerate during load

### Stage 3: PostgreSQL full-text search

* create `series_search_documents`
* add `search_vector`
* add GIN index
* rank results with PostgreSQL full-text search

### Stage 4: Add search-only aliases

* manual aliases first
* later LLM-generated aliases with review status

### Stage 5: Add pgvector semantic search

* generate embeddings for search documents
* store vectors in PostgreSQL
* combine vector similarity with lexical ranking

### Stage 6: Add grouped results

* return matching Browse nodes alongside individual series
* clearly label result types

### Stage 7: Add lightweight match explanations

* explain whether result matched official metadata, alias, full-text, or semantic similarity

## Summary

Search is the intent-based discovery layer of Stats Finder.

It should help users find official statistical series even when they do not know the exact terminology.

The core pattern is:

```text
user query
→ metadata search
→ candidate official series
→ visible provenance
→ inspect or export
```

Search should remain lightweight, fast, and explainable.

Its strongest design principle is:

> Search helps users find the right official series. It does not become the source of statistical truth.


## Current implementation

The current search implementation has two routes:

```text
GET /v1/series/search
GET /v1/series/search/semantic
```

The standard search route performs database-backed metadata search with optional
dataset filtering. The semantic route embeds the query with the configured Gemini
embedding model and searches stored series metadata embeddings in PostgreSQL with
pgvector.

The web Search page remains intentionally lightweight: Jinja2 renders the page,
plain JavaScript calls the API, and result links resolve to source-backed series
pages. There is no frontend framework or search-specific infrastructure outside
PostgreSQL.

Semantic search should remain an enhancement, not a dependency for the whole
product. If embeddings, Google Cloud configuration, or pgvector data are missing,
standard dataset pages, series pages, and lexical API search should still be easy
to reason about.

## Lightweight search rule

Search should stay simple, fast, and explainable. Improve ranking and retrieval
inside PostgreSQL first. Add aliases, keyword text, embeddings, or small query
expansions only when they map back to official metadata and make the user journey
simpler.
