# Stats Finder API Architecture

## Purpose

The Stats Finder API is the stable machine-readable interface to Stats Finder Core.

It should allow users, analysts, developers, CLI tools, MCP servers, and other products to discover, inspect, and download official statistical series without depending on the internal database schema.

The API is central to the product’s identity:

> Stats Finder is not just a website. It is a lightweight, source-backed API for finding and retrieving official statistics.

The website, CLI, MCP server, and future integrations should all use the same API.

## Core principle

Stats Finder Core is the system of record for source-backed statistical metadata and observations.

External products should integrate through the API rather than querying the database directly.

```text
Official SDMX sources
        ↓
Stats Finder Core
  PostgreSQL
  Search
  Browse
  Export
  Provenance
        ↓
Stats Finder API
        ↓
Website / CLI / MCP / external tools
```

The API should preserve the central Stats Finder rule:

> The LLM may interpret. The database must answer.

## Design goals

The API should be:

* stable
* readable
* source-backed
* versioned
* lightweight
* easy to test
* easy to call from scripts
* easy to wrap with CLI or MCP tools
* explicit about provenance
* careful with public identifiers

The API should avoid:

* exposing internal database IDs as the primary public identity
* returning generated statistical claims
* mixing official metadata with AI-generated enrichment
* requiring user accounts for public data
* forcing clients to understand raw SDMX before they can use the service

## Public identity model

Internal database IDs are useful inside PostgreSQL, but public API identity should use source-backed identifiers.

Preferred public identifiers:

```text
dataset_id
series_key
indicator_code
dimension values
```

Current prototype routes may use:

```text
dataset_id + indicator_code
```

Longer term, the preferred stable identity should be:

```text
dataset_id + series_key
```

because `series_key` is closer to the official multidimensional SDMX identity.

## Versioning

The public API should use versioned routes:

```text
/v1/...
```

Breaking changes should wait for a new version:

```text
/v2/...
```

The first version should prioritise clarity over perfection.

## API route groups

The API should be organised around product capabilities:

```text
Health
Datasets
Series
Search
Browse
Export
Codelists
Metadata
Provenance
```

## Health endpoints

### Basic health

```text
GET /health
```

Purpose:

* confirms the API process is running

Example response:

```json
{
  "status": "ok"
}
```

### Database health

```text
GET /health/db
```

Purpose:

* confirms the API can reach PostgreSQL
* returns basic row counts

Example response:

```json
{
  "status": "ok",
  "database": "reachable",
  "datasets": 2,
  "series": 22,
  "observations": 944
}
```

This is useful for local development, deployment checks, and Cloud Run health diagnostics.

## Dataset endpoints

### List datasets

```text
GET /v1/datasets
```

Returns available datasets.

Example response:

```json
{
  "datasets": [
    {
      "dataset_id": "NAG_GBR",
      "title": "UK National Accounts",
      "source_url": "https://static.ons.gov.uk/imf/NAG_GBR.xml",
      "documentation_url": "https://www.ons.gov.uk/aboutus/imfpage",
      "metadata_url": "https://dsbb.imf.org/sdds/dqaf-base/country/GBR/category/NAG00",
      "structure_ref": "IMF_ECOFIN_DSD_1_0"
    }
  ]
}
```

### Get dataset

```text
GET /v1/datasets/{dataset_id}
```

Returns one dataset, its metadata, source URLs, and summary counts.

Possible response fields:

```text
dataset_id
title
source_url
documentation_url
metadata_url
structure_ref
series_count
observation_count
```

## Series endpoints

### Get series metadata

Preferred future route:

```text
GET /v1/series/{dataset_id}/{series_key}
```

Returns official metadata for one series.

Example response:

```json
{
  "dataset_id": "CPI_GBR",
  "series_key": "M.GB.PCPI_IX",
  "indicator_code": "PCPI_IX",
  "title": "Consumer Price Index, all items",
  "frequency": "Monthly",
  "unit": "Index",
  "dimension_values": {},
  "dimension_labels": {},
  "source_url": "...",
  "documentation_url": "..."
}
```

### Current compatibility route

Current prototype routes may include:

```text
GET /v1/datasets/{dataset_id}/series/by-indicator/{indicator_code}
```

This is acceptable for the early prototype, but the long-term API should move toward `series_key`.

### Get observations

Preferred future route:

```text
GET /v1/series/{dataset_id}/{series_key}/observations
```

Useful query parameters:

```text
limit
offset
from
to
order
```

Example:

```text
GET /v1/series/CPI_GBR/M.GB.PCPI_IX/observations?from=2020&to=2024
```

Example response:

```json
{
  "dataset_id": "CPI_GBR",
  "series_key": "M.GB.PCPI_IX",
  "observations": [
    {
      "time_period": "2024-01",
      "obs_value": 131.5
    }
  ]
}
```

## Search endpoints

Search helps users find series when they do not know the exact dataset, indicator code, or series key.

### Series search

Current route:

```text
GET /v1/series/search?q={query}&limit={limit}&dataset_id={dataset_id}
```

Example:

```text
GET /v1/series/search?q=inflation&limit=20
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
      "source": "ONS/IMF SDMX"
    }
  ]
}
```

### Future unified search

Future route:

```text
GET /v1/search?q={query}&types=series,dataset,browse_node
```

This could return:

* series results
* dataset results
* browse node results

The first implementation can remain series-only.

## Browse endpoints

Browse supports structured discovery through topic trees and source-backed groups.

### List root browse nodes

```text
GET /v1/discovery/nodes
```

Returns top-level browse nodes.

Example:

```json
{
  "nodes": [
    {
      "slug": "economy",
      "title": "Economy",
      "node_type": "category",
      "source_type": "statsfinder_curated"
    }
  ]
}
```

### Get browse node

```text
GET /v1/discovery/nodes/{slug}
```

Returns one browse node.

Example:

```json
{
  "slug": "gva-by-industry",
  "title": "GVA by industry",
  "description": "Gross value added series broken down by industry.",
  "node_type": "series_group",
  "source_type": "statsfinder_curated",
  "dataset_id": "NAG_GBR",
  "member_count": 50
}
```

### Get browse node children

```text
GET /v1/discovery/nodes/{slug}/children
```

Returns child nodes.

### Get browse node series

```text
GET /v1/discovery/nodes/{slug}/series
```

Returns all series belonging to a browse node.

This supports workflows such as:

```text
GVA
  → GVA by industry
      → download all 50 series
```

## Export endpoints

Export is one of the most important API capabilities.

It allows users to download selected series or browse groups as reusable data bundles.

### Export selected series

```text
POST /v1/export
```

Example request:

```json
{
  "format": "csvw",
  "series": [
    {
      "dataset_id": "CPI_GBR",
      "series_key": "M.GB.PCPI_IX"
    },
    {
      "dataset_id": "NAG_GBR",
      "series_key": "Q.GB.NGDP_R_SA_XDC"
    }
  ]
}
```

### Export browse group

```text
POST /v1/export
```

Example request:

```json
{
  "format": "csvw",
  "group_slug": "gva-by-industry"
}
```

The same export engine should support both manually selected series and browse groups.

## Export formats

Initial supported formats:

```text
json
csv
csvw
```

Future format:

```text
jsonld
```

### JSON

Useful for developers and agents.

### CSV

Should use long/tidy format by default.

Example:

```csv
dataset_id,series_key,indicator_code,indicator_name,time_period,obs_value,unit,frequency,source_url
CPI_GBR,M.GB.PCPI_IX,PCPI_IX,Consumer Price Index,2024-01,131.5,Index,Monthly,https://...
```

### CSVW

Preferred rich download format.

A CSVW export should be a zip bundle:

```text
statsfinder-export.zip
  observations.csv
  csvw-metadata.json
  README.txt
```

CSVW gives users a plain CSV plus machine-readable metadata and provenance.

### JSON-LD

JSON-LD should come later because it requires careful modelling of:

* datasets
* series
* observations
* codelists
* units
* sources
* provenance

## Codelist endpoints

Codelists are important for understanding dimensions and classifications.

Possible endpoints:

```text
GET /v1/codelists
GET /v1/codelists/{codelist_id}
GET /v1/datasets/{dataset_id}/codelists
```

Example codelist item response:

```json
{
  "codelist_id": "CL_FREQ",
  "items": [
    {
      "code_id": "M",
      "name": "Monthly",
      "description": null
    },
    {
      "code_id": "Q",
      "name": "Quarterly",
      "description": null
    }
  ]
}
```

These endpoints support Browse, Search, API users, and future CLI/MCP tools.

## Provenance endpoints

Every series and export should expose provenance.

Possible endpoint:

```text
GET /v1/series/{dataset_id}/{series_key}/provenance
```

Example response:

```json
{
  "dataset_id": "CPI_GBR",
  "series_key": "M.GB.PCPI_IX",
  "source_url": "...",
  "documentation_url": "...",
  "metadata_url": "...",
  "structure_ref": "IMF_ECOFIN_DSD_1_0",
  "statement": "Values are loaded from official ONS/IMF SDMX source data. They are not generated by an LLM."
}
```

Exports should include equivalent provenance in their metadata files.

## API consumers

The API should support several consumer types.

### Website

The web UI uses the API or shared backend functions to power:

* Search
* Browse
* Series pages
* Export actions

### CLI

The CLI should be a thin API client.

Example:

```bash
statsfinder search "inflation"
statsfinder download-group gva-by-industry --format csvw
```

### MCP

The MCP server should be a thin adapter over the API.

Example tools:

```text
search_series(query)
get_series_metadata(dataset_id, series_key)
export_series(series, format)
export_browse_group(slug, format)
```

### External analysts

Analysts can use the API directly from:

* Python
* R
* curl
* notebooks
* scripts
* scheduled jobs

## Error handling

The API should return clear errors.

Example not found:

```json
{
  "detail": {
    "error": "series_not_found",
    "message": "No series found for dataset_id=CPI_GBR and series_key=BAD_CODE"
  }
}
```

Useful HTTP statuses:

```text
200 OK
400 Bad Request
404 Not Found
422 Validation Error
503 Service Unavailable
```

For export limits:

```json
{
  "detail": {
    "error": "export_too_large",
    "message": "This export contains too many observations for immediate download.",
    "series_count": 1250,
    "estimated_observations": 500000
  }
}
```

## Pagination

Endpoints returning lists should support pagination.

Useful parameters:

```text
limit
offset
```

Examples:

```text
GET /v1/series/search?q=gdp&limit=20&offset=0
GET /v1/discovery/nodes/gva-by-industry/series?limit=100&offset=0
```

The API should set sensible maximum limits.

## Large exports

Small exports can be generated immediately.

Example:

```text
10 series
50 series
a few thousand observations
```

Large exports may later need a background job.

Initial thresholds can be simple:

```text
0–100 series:
  immediate export

101–1,000 series:
  require confirmation or explicit parameter

1,000+ series:
  later background export pattern
```

The first version can support immediate exports only.

## Security

For public official data, the API should initially be open.

No authentication should be required for:

* search
* browse
* series metadata
* observations
* small exports

Future authenticated features might include:

* admin ingestion
* private datasets
* high-volume usage
* saved collections
* API keys for rate limits

These should not complicate the public API too early.

## Performance expectations

A catalogue of thousands of series is small for PostgreSQL.

The API should stay fast if it follows these rules:

* search metadata, not raw observations
* use indexes on public identifiers
* paginate list endpoints
* stream or generate exports carefully
* avoid returning huge observation sets by default
* keep result payloads compact
* use PostgreSQL full-text search before adding external search infrastructure
* use pgvector only for metadata search documents

Important indexes:

```sql
CREATE INDEX idx_series_dataset_key
ON series (dataset_id, series_key);

CREATE INDEX idx_observations_series_time
ON observations (series_id, time_period);

CREATE INDEX idx_series_indicator_code
ON series (indicator_code);
```

## API documentation

FastAPI should expose OpenAPI docs automatically.

Useful routes:

```text
/docs
/openapi.json
```

Longer term, Stats Finder may add a human-friendly API landing page:

```text
/api
```

That page should explain:

* common endpoints
* example curl commands
* export examples
* CSVW format
* CLI installation
* provenance model

## Naming conventions

Use clear, boring names.

Prefer:

```text
dataset_id
series_key
indicator_code
time_period
obs_value
source_url
documentation_url
metadata_url
```

Avoid clever abstractions.

The API should be easy to understand from JSON alone.

## Implementation stages

### Stage 1: Stabilise current API

* `/health`
* `/health/db`
* `/v1/datasets`
* `/v1/series/search`
* single series metadata
* single series observations

### Stage 2: Move toward stable series-key routes

Add:

```text
GET /v1/series/{dataset_id}/{series_key}
GET /v1/series/{dataset_id}/{series_key}/observations
```

Keep existing indicator routes temporarily for compatibility.

### Stage 3: Add export API

Add:

```text
POST /v1/export
```

Start with:

* JSON export
* CSV export
* CSVW zip export

### Stage 4: Add Browse API

Add:

```text
GET /v1/discovery/nodes
GET /v1/discovery/nodes/{slug}
GET /v1/discovery/nodes/{slug}/series
```

### Stage 5: Add richer metadata APIs

Add:

* codelists
* provenance
* availability
* metadata quality

### Stage 6: Support CLI and MCP adapters

Build CLI and MCP as API consumers, not as database clients.

## What the API should not become

The API should not become:

* a raw database mirror
* a chat-completion endpoint
* a generated-answer service
* an unstable internal implementation detail
* a dashboard state API
* a place where AI-generated metadata overwrites official metadata

The API should remain:

```text
stable
small
source-backed
predictable
developer-friendly
```

## Summary

The Stats Finder API is the contract between official source-backed data and every user-facing or machine-facing product built on top of it.

The core API pattern is:

```text
discover
→ inspect
→ retrieve
→ export
```

The API should make Stats Finder useful beyond the website:

* web users can search and browse
* analysts can download CSVW
* developers can script against JSON
* CLI users can work from the terminal
* MCP tools can expose safe agent actions
* future services can integrate without database coupling

The API is therefore one of the project’s most important assets.

Its guiding principle is:

> Keep the core API simple, stable, source-backed, and good enough to build other products on top of.


## Current implemented API surface

The current repository exposes a deliberately small implemented API. Route
coverage is asserted at FastAPI startup so accidental route removals are caught
early.

Implemented health routes:

```text
GET /health
GET /health/db
```

Implemented dataset and search routes:

```text
GET /v1/datasets
GET /v1/datasets/{dataset_id}
GET /v1/datasets/{dataset_id}/series
GET /v1/series/search
GET /v1/series/search/semantic
```

Implemented series and export routes:

```text
GET /v1/datasets/{dataset_id}/series/by-indicator/{indicator_code}
GET /v1/datasets/{dataset_id}/series/by-indicator/{indicator_code}/observations
GET /v1/datasets/{dataset_id}/series/by-indicator/{indicator_code}/observations.csv
```

Implemented experimental chat routes:

```text
POST /v1/chat/retrieve
POST /v1/chat/ask
```

The browser pages are also intentionally simple:

```text
GET /
GET /search
GET /browse
GET /browse/datasets/{dataset_id}
GET /series/{dataset_id}/{indicator_code}
GET /chat
GET /api
```

### Current identity note

The current public series routes use `dataset_id` plus `indicator_code`, with an
optional `series_id` query parameter when that pair is ambiguous, such as when an
indicator appears at more than one frequency. The longer-term API direction can
still move toward `dataset_id` plus `series_key`, but the current implementation
should not add a second identity style until it clearly improves simplicity for
users and clients.

### CSV exports

Single-series CSV export is implemented as the first lightweight export surface.
The CSV repeats key source and series metadata on each row so files remain easy
to inspect and combine without introducing a heavier export subsystem.

## Lightweight API rule

Keep the API easy to call with `curl`, notebooks, scripts, and the server-rendered
web UI. New endpoints should return source-backed records, explicit provenance,
and predictable JSON. Avoid adding authentication, client-specific response
shapes, or generated statistical claims for public official data unless a clear
future requirement justifies the complexity.
