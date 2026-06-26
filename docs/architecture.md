# Stats Finder: High-Level Architecture and Principles

## Purpose

Stats Finder is an experimental, lightweight discovery service for official statistical time series.

The long-term goal is to build a FRED-like service for UK official statistics: fast search, structured browse, stable series pages, simple exports, clear provenance, and a public API.

Stats Finder is designed around one core idea:

> Help people find the right official statistics by meaning, while keeping the data itself grounded in published source data and official metadata.

Stats Finder is not intended to be a general-purpose chatbot, dashboard builder, or statistical answer generator. It is a search, browse, metadata, export, and API layer over official statistical data.

## North-star product

Stats Finder should let users:

```text
Search when they know the words.
Browse when they know the topic.
Use the API when they need the data.
```

The first-class product surfaces are:

```text
Search
Browse
API
```

Later, the product may add:

```text
CLI
MCP
```

But these should be adapters over the same core API, not separate systems of record.

## Unique selling proposition

Stats Finder’s USP is:

> A lightweight, FRED-like discovery layer for UK official statistics, grounded in SDMX metadata, enhanced with semantic search, and exposed through a simple public API.

This combines:

* FRED-like usability
* UK official statistics focus
* SDMX-native metadata grounding
* fast search
* structured browse
* stable public URLs
* source-backed observations
* clear provenance
* simple CSVW / JSON exports
* API-first design
* future CLI and MCP integration
* lightweight deployment

## Core principle

The central rule is:

> The LLM may interpret. The database must answer.

This means:

* AI can help interpret user intent.
* AI can help generate search-only aliases.
* AI can help create embeddings.
* AI can help explain why a result matched.
* AI must not invent statistical values.
* AI must not overwrite official metadata.
* Official observations must come from the database.
* The database must be loaded from source-backed official data.

## High-level architecture

Stats Finder Core is the trusted centre of the system.

```text
Official SDMX sources
        ↓
Ingestion and metadata processing
        ↓
PostgreSQL
  official datasets
  official series
  official observations
  codelists
  search documents
  browse nodes
  exports
        ↓
FastAPI Core
  Search
  Browse
  Series metadata
  Observations
  Export
  Provenance
        ↓
Product surfaces
  Web UI
  API
  CLI
  MCP
```

The architecture should remain deliberately small.

The preferred core stack is:

* FastAPI
* PostgreSQL
* pgvector when semantic search is needed
* Jinja2
* plain CSS
* small plain JavaScript
* Docker for local development
* Cloud Run for deployment
* Cloud SQL for PostgreSQL
* Secret Manager for credentials
* Cloudflare DNS for `statsfinder.uk`

## Product surfaces

## 1. Search

Search is for users who know roughly what they want, but not the official dataset, indicator code, or SDMX series key.

Example searches:

```text
inflation
charity sector spending
industry GVA
household consumption
GDP chained volume measure
```

Search should operate over metadata, not raw observation values.

Search should evolve through stages:

```text
exact match
→ lexical search
→ PostgreSQL full-text search
→ pgvector semantic search
→ lightweight ranking and explanations
```

Search should return candidate official series, not generated statistical claims.

## 2. Browse

Browse is for users who want to explore what exists by topic or statistical structure.

Example:

```text
Economy
  National accounts
    Gross value added
      GVA by industry
        Download all 50 series
```

Browse should be SDMX-aware, but not blocked by incomplete source metadata.

Where available, Browse can use:

* SDMX Category Schemes
* SDMX Categories
* SDMX Hierarchies
* Codelists
* Concepts
* Dataflows
* Data Structure Definitions

Where these are missing or incomplete, Stats Finder can use curated browse nodes, clearly marked as curated navigation.

The underlying series and observations must remain source-backed.

## 3. API

The API is the stable machine-readable interface to Stats Finder Core.

The API should support:

* dataset listing
* series search
* series metadata
* observations
* browse nodes
* group membership
* codelists
* provenance
* exports

The API should be good enough for:

* the web UI
* analysts
* scripts
* notebooks
* CLI tools
* MCP servers
* external products

The API is one of the project’s most important assets.

## 4. Export

Export should allow users to download one series, several selected series, or all series in a browse group.

Examples:

```text
download CPI as JSON
download CPI + GDP as CSVW
download all GVA by industry series as CSVW
```

Exports should be generated from official database records.

Multi-series exports should use long/tidy format by default.

Example:

```csv
dataset_id,series_key,indicator_code,indicator_name,time_period,obs_value,unit,frequency,source_url
CPI_GBR,M.GB.PCPI_IX,PCPI_IX,Consumer Price Index,2024-01,131.5,Index,Monthly,https://...
NAG_GBR,Q.GB.NGDP_R_SA_XDC,NGDP_R_SA_XDC,GDP chained volume measure,2024-Q1,540000,£ million,Quarterly,https://...
```

CSVW should be a preferred rich export format because it combines plain CSV with machine-readable metadata and provenance.

A CSVW bundle might contain:

```text
observations.csv
csvw-metadata.json
README.txt
```

JSON-LD can come later.

## 5. CLI

A future CLI should be a thin client over the Stats Finder API.

Example commands:

```bash
statsfinder search "inflation"
statsfinder series CPI_GBR:PCPI_IX
statsfinder download CPI_GBR:PCPI_IX --format csvw --output cpi.zip
statsfinder browse gva-by-industry
statsfinder download-group gva-by-industry --format csvw
```

The CLI should not parse SDMX or query PostgreSQL directly.

It should be:

* fast
* scriptable
* terminal-native
* useful to humans
* useful to LLM agents with terminal access

## 6. MCP

A future MCP server should be a thin adapter over the Stats Finder API.

Possible tools:

```text
search_series(query)
get_series_metadata(dataset_id, series_key)
get_observations(dataset_id, series_key)
list_browse_nodes()
export_series(series, format)
export_browse_group(slug, format)
```

The MCP server should not own data logic.

The MCP server should not become a second backend.

## Architecture principles

## 1. Lightweight by default

Stats Finder should be small enough for one engineer to understand.

Avoid unnecessary infrastructure unless there is a clear need.

Prefer:

```text
PostgreSQL before Elasticsearch
server-rendered HTML before React
Cloud Run before Kubernetes
plain JavaScript before a frontend framework
simple SQL before complex service layers
```

The product should feel fast, inspectable, and easy to debug.

## 2. Source-backed trust

Stats Finder must clearly separate:

```text
official source data
official metadata
curated navigation
search-only enrichment
LLM-generated aliases
user-facing explanations
```

Official data and official metadata should never be silently overwritten by AI-generated content.

Every series page and export should make provenance visible.

## 3. SDMX-aware, not SDMX-burdened

Stats Finder should use SDMX as a grounding layer, especially for:

* datasets
* series keys
* dimensions
* codelists
* concepts
* source metadata
* structures
* hierarchies where available
* categories where available

But the user should not need to understand SDMX to use the product.

Stats Finder should translate SDMX structure into useful search, browse, metadata, and export experiences.

## 4. API-first

The web UI, CLI, MCP server, and future integrations should all rely on the same core API.

The rule is:

```text
External products call the API.
They do not query the database directly.
```

This keeps Stats Finder Core as the single trusted source of retrieval logic.

## 5. Stable public identifiers

Internal database IDs are useful, but public URLs and API calls should use source-backed identifiers.

Preferred public identity:

```text
dataset_id + series_key
```

Early prototype routes may use:

```text
dataset_id + indicator_code
```

But the long-term design should move toward stable SDMX-style series identity.

## 6. Search metadata, not observations

Search should operate over metadata documents, not raw observation values.

Observation values should be retrieved only after a user selects:

* a series
* a group
* an export request

This keeps search fast and avoids misleading value-based matches.

## 7. Explainability

Search and browse should be understandable.

Where possible, Stats Finder should explain:

* why a result matched
* whether a grouping is official or curated
* where the data came from
* which source file or metadata URL supports it
* whether a term came from official metadata or search-only enrichment

This is especially important when semantic search is added.

## 8. No unnecessary accounts

Public official statistics should be accessible without login.

Avoid accounts, sessions, saved dashboards, and personal workspaces unless there is a strong future reason.

Selection state can live in the browser.

Example:

```text
selected series basket in localStorage
→ POST /v1/export
→ source-backed download
```

## 9. TUI-inspired simplicity

Even on the web, Stats Finder should borrow design values from terminal user interfaces:

* speed
* clarity
* keyboard friendliness
* information density
* low visual noise
* predictable navigation
* copyable URLs
* copyable commands
* developer-friendly outputs

The product should feel closer to a fast search/documentation/API tool than to a heavy dashboard.

## 10. Modular core, microservice edges

The core product should remain simple.

Future specialised products should be separate adapters:

```text
Stats Finder Core
  Search
  Browse
  API
  Export
  Provenance

Separate adapters
  CLI
  MCP
  catalogue connector
  spreadsheet connector
  documentation site
```

These adapters should consume the API.

They should not duplicate core data logic.

## Data model direction

The core database should hold official source-backed objects:

```text
datasets
series
observations
codelists
codelist_items
```

Future additions should support discovery and export:

```text
series_search_documents
series_search_aliases
discovery_nodes
discovery_node_series
export_requests
```

The model should preserve the distinction between official data and Stats Finder-added discovery layers.

## Search direction

Search should mature through clear stages:

```text
Stage 1:
  simple lexical search over current series metadata

Stage 2:
  deterministic search documents

Stage 3:
  PostgreSQL full-text search

Stage 4:
  search-only aliases

Stage 5:
  pgvector semantic search

Stage 6:
  hybrid ranking

Stage 7:
  lightweight match explanations
```

The search system should work without an LLM at every stage. AI should improve discovery, not become a hard dependency for basic search.

## Browse direction

Browse should mature through clear stages:

```text
Stage 1:
  curated static browse tree

Stage 2:
  discovery_nodes and discovery_node_series tables

Stage 3:
  browse pages

Stage 4:
  browse API

Stage 5:
  group export

Stage 6:
  SDMX category and hierarchy import where available

Stage 7:
  search integration for browse groups
```

Browse should support the key workflow:

```text
topic tree
→ meaningful group
→ official series
→ source-backed export
```

## Export direction

Export should mature through clear stages:

```text
Stage 1:
  JSON export for selected series

Stage 2:
  CSV export in long format

Stage 3:
  CSVW zip export

Stage 4:
  browse group export

Stage 5:
  JSON-LD export

Stage 6:
  large export handling
```

Export is a major product feature, not an afterthought.

## Deployment direction

The preferred deployment path is:

```text
Cloudflare DNS
        ↓
Cloud Run
        ↓
Cloud SQL PostgreSQL
        ↓
Secret Manager
```

This keeps operations simple.

Avoid Kubernetes, complex service meshes, and multi-service platforms unless there is a clear need.

## What Stats Finder should not become

Stats Finder should not become:

* a generic chatbot
* a dashboard builder
* a statistical claims generator
* a heavy frontend application
* a Kubernetes platform
* a duplicate SDMX registry
* a black-box semantic search product
* a system where AI-generated metadata replaces official metadata
* a system where users need accounts to download public data
* a system where every new idea is added to the core app

## Success criteria

Stats Finder is succeeding if a user can:

```text
search for a statistical concept
find the right official series
understand why it matched
inspect the metadata
trust the provenance
download the data
call the API
reuse the result in another tool
```

It is especially succeeding if the product remains:

```text
small
fast
clear
source-backed
developer-friendly
easy to deploy
easy to explain
```

## Summary

Stats Finder should be the trusted lightweight core for finding and retrieving official UK statistical series.

Its strongest identity is:

```text
Search
Browse
API
```

Its future extension points are:

```text
CLI
MCP
other API consumers
```

Its architectural philosophy is:

```text
Official data in the database.
Meaningful discovery through metadata.
AI only where it helps findability.
APIs for reuse.
Adapters at the edges.
Keep the core small.
```

The guiding statement is:

> Stats Finder makes official statistics fast to find, easy to inspect, and hard to misinterpret.


## Current repository shape

The current implementation remains intentionally small and should stay that way.
StatsFinder is now organised around a handful of FastAPI route modules, small
service modules, Jinja templates, plain static assets, SQL migrations, and
repeatable scripts.

Current product surfaces:

```text
/search                  server-rendered search page
/browse                  server-rendered browse landing page
/browse/datasets/{id}    dataset browse table with optional semantic matches
/series/{dataset}/{code} server-rendered series page with chart and exports
/chat                    experimental source-grounded chat page
/api                     human-readable API landing page
/v1/...                  JSON and CSV API routes
```

Current configured datasets:

```text
NAG_GBR  UK National Accounts
CPI_GBR  UK Consumer Price Index
BOP_GBR  UK Balance of Payments
SBS_GBR  UK Sectoral Balance Sheet
GGO_GBR  UK General Government Operations
```

Current optional AI-assisted features are implemented as helpers around the
source-backed database:

* semantic series search embeds the user query and compares it with stored
  series metadata embeddings in PostgreSQL/pgvector;
* chat retrieval combines semantic series matches with ingested SNA reference
  chunks;
* chat generation must present short grounded answers and should point users
  back to source-backed series pages and metadata.

These features must not change the product centre of gravity. StatsFinder should
remain a lightweight Search, Browse, API, and Export service first. Chat and AI
retrieval are useful only when they make source-backed discovery simpler.

## Simplicity guardrails

Every architecture change should answer this question first:

> Is this the smallest simple thing that improves source-backed discovery?

Prefer:

* FastAPI routes over extra backend services;
* Jinja2 pages over a frontend framework;
* plain CSS and small JavaScript over a bundled frontend toolchain;
* PostgreSQL full-text search and pgvector over separate search clusters;
* scripts that can be run locally over complex orchestration;
* explicit source/provenance fields over generated prose;
* simple JSON and CSV endpoints over bespoke export systems.

Avoid adding infrastructure, queues, caches, build steps, or frameworks unless a
measured product need proves that the current lightweight approach is no longer
enough.
