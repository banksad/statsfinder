# StatsFinder

## Public repo note

This is an independent experimental prototype. It is not an official ONS product.

The project uses public official data sources where available and aims to preserve clear source attribution and provenance throughout the application.

**StatsFinder** is an experimental lightweight application for discovering, inspecting, and retrieving official statistical series.

The project explores a simple idea:

> Use AI and semantic search to help people find the right official statistics, but keep the data itself grounded in published SDMX source data.

The app is intentionally fast, small, and simple in its infrastructure. The ambition is to build a trustworthy discovery layer on top of well-structured official statistical metadata.

## Project status

Current features include:

* FastAPI JSON API with versioned `/v1` routes
* Lightweight server-rendered HTML pages using Jinja2
* Plain CSS and JavaScript, with no frontend framework or Node toolchain
* Dockerised FastAPI app
* Docker Compose local Postgres database
* Search page backed by database metadata search
* Optional pgvector/Gemini semantic search over series metadata
* Dataset filtering and dataset-level Browse pages
* Series detail pages with source/provenance blocks
* Fast and simple SVG time-series charts
* JSON and CSV observation endpoints for single-series exports
* Experimental source-grounded Chat page and retrieval endpoints
* Repeatable local database bootstrap script
* Support for the following configured ONS/IMF SDMX datasets:

  * `NAG_GBR` — UK National Accounts
  * `CPI_GBR` — UK Consumer Price Index
  * `BOP_GBR` — UK Balance of Payments
  * `SBS_GBR` — UK Sectoral Balance Sheet
  * `GGO_GBR` — UK General Government Operations

Planned work includes:

* Keeping semantic search and chat as lightweight, source-grounded helpers rather than product centres
* Better ranking and query interpretation
* Additional ONS/IMF SDMX datasets where they add clear value
* Richer SDMX metadata modelling without adding unnecessary infrastructure
* Cloud deployment on Google Cloud Run

## Core principle

The guiding design rules are:

> The LLM may help interpret the question. The database must answer it.

> Keep StatsFinder as lightweight and simple as possible. Prefer boring, reviewable components over extra services, frameworks, or clever abstractions.

The application should never invent statistical values. Any AI or semantic layer should help users discover candidate datasets and series, but observations should come from official published data loaded into the database.

In other words:

```text
User question
  → semantic interpretation / search
  → official metadata match
  → database query
  → sourced statistical result
```

## Why SDMX?

SDMX provides a strong foundation for official statistical dissemination because it already encodes many of the concepts needed for trustworthy machine-readable statistics:

* datasets and dataflows
* dimensions
* codelists
* concepts
* series keys
* observations
* frequency
* units
* reference areas
* metadata structures
* provenance and source links

This project treats SDMX as statistical infrastructure, not as the only user-facing format.

Users should not need to read SDMX XML. Instead, the application can ingest SDMX, normalise it into a database, and expose lightweight outputs:

* simple JSON APIs
* human-readable HTML pages
* charts
* semantic search results
* future AI-assisted discovery interfaces

The goal is to show how official SDMX metadata can support faster, simpler, and more innovative dissemination products.

## Architecture

Current local architecture:

```text
Official ONS/IMF SDMX files
  → parsing and enrichment scripts
  → Postgres tables
  → FastAPI JSON API and small service modules
  → Jinja2 HTML pages
  → lightweight browser UI
```

Main components:

```text
app/
  api/
    main.py              FastAPI app factory and router registration
    web_routes.py        HTML page routes
    v1_routes.py         Versioned JSON API routes
    chat_routes.py       Experimental grounded chat routes
    exports.py           CSV and resource URL export helpers
  services/
    postgres.py          Database query/service helpers
    semantic_search.py   Optional pgvector/Gemini semantic search
    reference_search.py  Source/reference retrieval helpers
    chat.py              Grounded chat orchestration helpers
  charts.py              Server-side chart data and SVG helpers

templates/
  index.html             Search page
  browse.html            Browse landing page
  browse_dataset.html    Dataset Browse page
  series.html            Series detail page
  api.html               API landing page
  chat.html              Experimental grounded chat page

static/
  styles.css             Plain CSS
  app.js                 Plain JavaScript search UI
  series-chart.js        Small SVG chart helper
  chat.js                Plain JavaScript chat UI

scripts/
  common/               Shared script utilities and dataset registry helpers
  ingest/               Dataset parsing/loading, enrichment, and search document ingestion
  db/                   Local database bootstrap and query CLIs
  inspect/              SDMX/codelist inspection and preview helpers
  search/               Semantic search command and document-building helpers
  smoke/                Local smoke tests and embedding environment checks

sql/
  001_create_core_tables.sql
  002_create_semantic_search_tables.sql
  003_create_series_embeddings.sql
  004_create_reference_chunks.sql

infra/
  local/
    compose.yaml         Local Docker Compose stack
```


## Repository map

Quick orientation for contributors:

* `app/api/` is the FastAPI/web layer. `app/api/main.py` creates the application, mounts static assets, and registers routers; route implementations live in focused modules such as `app/api/web_routes.py`, `app/api/v1_routes.py`, and `app/api/chat_routes.py`. CSV/resource export helpers live in `app/api/exports.py`.
* `app/services/` contains the database-backed service logic used by the web/API routes, including Postgres queries, optional semantic search, reference retrieval, and grounded chat orchestration. `app/charts.py` contains the server-side chart formatting and SVG data helpers used by series pages. Commands that query series, run smoke tests, or serve pages need a populated Postgres database and `ONS_SDMX_DB_DSN`.
* `scripts/db/query_postgres.py` is a CLI-oriented database query helper. Ingestion, smoke-test, and maintenance scripts share the same database assumptions as the web layer but should not be treated as the primary home for application service logic.
* Ingestion scripts such as `scripts/ingest/parse_dataset_to_records.py`, `scripts/ingest/load_dataset_to_postgres.py`, and `scripts/ingest/upsert_series_search_documents.py` parse registered source datasets and write normalized records/search documents to Postgres. Loader/upsert commands require a reachable Postgres database; embedding generation additionally requires Gemini/Google Cloud environment variables such as `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, and `GOOGLE_GENAI_USE_ENTERPRISE`.
* `sql/` holds ordered migration/schema files for the core tables and semantic-search/embedding support. Apply these before running database-backed commands on a fresh database.
* `docs/` contains the deeper architecture references for the API, CLI, search, browse, chat, and overall system design. Keep README notes high-level and update the docs when changing architecture details. Every design change should reinforce the same constraint: keep the product lightweight and simple.

## Local development

### 1. Create a local environment file

Create `.env` from `.env.example`:

```bash
cp .env.example .env
```

Example values:

```env
POSTGRES_DB=ons_sdmx
POSTGRES_USER=ons_sdmx_user
POSTGRES_PASSWORD=change_me
POSTGRES_HOST_PORT=5433
ONS_SDMX_DB_DSN=postgresql://ons_sdmx_user:change_me@localhost:5433/ons_sdmx
```

`.env` is ignored by Git and should not be committed.

### 2. Start the local stack

```bash
docker compose --env-file .env -f infra/local/compose.yaml up --build
```

Or run detached:

```bash
docker compose --env-file .env -f infra/local/compose.yaml up -d --build
```

### 3. Load data

From the project root, fetch the official sources and load everything with one
idempotent command:

```bash
export ONS_SDMX_DB_DSN="postgresql://ons_sdmx_user:change_me@localhost:5433/ons_sdmx"
python3 -m scripts.ingest.refresh_all
```

This applies the schema, downloads each registered SDMX source and the IMF
codelist structure, then parses, enriches, and upserts every dataset, printing a
per-dataset summary. It is safe to re-run; pass `--only CPI_GBR,NAG_GBR` to
refresh a subset, or `--skip-fetch` to reuse source files already on disk.

If the processed JSON is already present, `python3 -m scripts.db.bootstrap_local_db`
applies the schema and loads it without re-downloading.

With the local Docker stack running, run local smoke tests with:

```bash
docker compose --env-file .env -f infra/local/compose.yaml up -d --build
python -m scripts.smoke.smoke_test_local
```

### 4. Static formatting and lint checks

The repository includes conservative Ruff configuration for Python formatting and
static lint checks. To check formatting without changing files, run:

```bash
python -m ruff format --check .
```

To run lint checks, run:

```bash
python -m ruff check .
```

The browser code in `static/` is intentionally plain JavaScript and CSS with no
Node or npm toolchain requirement. Keep JavaScript/CSS formatting small, manual,
and reviewable unless the project explicitly introduces frontend tooling later.

If a future formatting pass would touch many files, make that mechanical change
in a separate follow-up commit so behavior-preserving refactors remain easy to
review.

### 5. Open the app

```text
http://127.0.0.1:8000/
```

Example series pages:

```text
http://127.0.0.1:8000/series/NAG_GBR/NGDP_R_SA_XDC
http://127.0.0.1:8000/series/CPI_GBR/PCPI_IX
```

## API examples

Health check:

```bash
curl -sS http://127.0.0.1:8000/health
```

List datasets:

```bash
curl -sS http://127.0.0.1:8000/v1/datasets | python3 -m json.tool
```

Search series:

```bash
curl -sS "http://127.0.0.1:8000/v1/series/search?q=real%20gdp&limit=5" | python3 -m json.tool
```

Search within a dataset:

```bash
curl -sS "http://127.0.0.1:8000/v1/series/search?q=price&dataset_id=CPI_GBR&limit=5" | python3 -m json.tool
```

Get series metadata:

```bash
curl -sS "http://127.0.0.1:8000/v1/datasets/NAG_GBR/series/by-indicator/NGDP_R_SA_XDC" | python3 -m json.tool
```

Get series observations:

```bash
curl -sS "http://127.0.0.1:8000/v1/datasets/NAG_GBR/series/by-indicator/NGDP_R_SA_XDC/observations?limit=20" | python3 -m json.tool
```

## Design principles

This project prioritises:

* speed
* lightweight implementation
* simple infrastructure
* clear provenance
* official source data
* machine-readable metadata
* simple public APIs
* semantic discovery over free-form statistical generation

It deliberately avoids:

* frontend frameworks
* complex dashboard tooling
* unnecessary client-side state
* generated statistical values
* chatbot-style answers without source data
* hiding provenance from users

## Experimental semantic search direction

The intended semantic search model is:

```text
official metadata document
  → embedding
  → vector search
  → candidate series
  → structured database query
  → sourced result
```

The semantic layer should help users find relevant series when they do not know the exact dataset name, indicator code, classification, or wording.

For example:

```text
"real GDP"
"food inflation"
"manufacturing output"
"quarterly national accounts"
```

should eventually map to candidate official series using metadata, codelists, aliases, and SDMX structures.

The semantic layer should not generate observations. It should retrieve and explain official metadata matches.



Additional endpoint examples:

```bash
curl -sS "http://127.0.0.1:8000/v1/datasets"
curl -sS "http://127.0.0.1:8000/v1/series/search?q=inflation&dataset_id=CPI_GBR"
curl -sS "http://127.0.0.1:8000/v1/series/search/semantic?q=government%20revenue&dataset_id=GGO_GBR"
curl -sS "http://127.0.0.1:8000/v1/datasets/NAG_GBR/series/by-indicator/NGDP_R_SA_XDC/observations?limit=5"
curl -sS -o observations.csv "http://127.0.0.1:8000/v1/datasets/CPI_GBR/series/by-indicator/PCPI_IX/observations.csv"
```

## Lightweight product rule

When updating StatsFinder, choose the smallest useful implementation:

* keep the web UI server-rendered unless a clear need emerges
* keep browser code plain JavaScript and CSS
* keep search, browse, exports, and chat grounded in database records
* avoid new infrastructure unless PostgreSQL, FastAPI, and small scripts are not enough
* prefer source-backed metadata and simple API responses over generated claims
