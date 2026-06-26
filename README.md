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

* FastAPI JSON API
* Lightweight server-rendered HTML pages using Jinja2
* Plain CSS and JavaScript, with no frontend framework
* Dockerised FastAPI app
* Docker Compose local Postgres database
* Dataset search
* Dataset filtering
* Series detail pages
* Source and provenance blocks
* Fast and simple SVG time-series charts
* Repeatable local database bootstrap script
* Initial support for the following ONS/IMF SDMX datasets:

  * `NAG_GBR` — UK National Accounts
  * `CPI_GBR` — UK Consumer Price Index

Planned work includes:

* LLM-assisted semantic search over statistical metadata
* Better ranking and query interpretation
* Additional ONS/IMF SDMX datasets
* Richer SDMX metadata modelling
* Cloud deployment on Google Cloud Run
* Postgres/pgvector-backed semantic search

## Core principle

The guiding design rule is:

> The LLM may help interpret the question. The database must answer it.

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
  → FastAPI JSON API
  → Jinja2 HTML pages
  → lightweight browser UI
```

Main components:

```text
app/
  api/
    main.py              FastAPI application

templates/
  index.html             Search page
  series.html            Series detail page

static/
  styles.css             Plain CSS
  app.js                 Plain JavaScript search UI

scripts/
  parse_dataset_to_records.py
  enrich_dataset_series.py
  load_dataset_to_postgres.py
  bootstrap_local_db.py

sql/
  001_create_core_tables.sql

infra/
  local/
    compose.yaml         Local Docker Compose stack
```

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

### 3. Bootstrap the database

From the project root:

```bash
export ONS_SDMX_DB_DSN="postgresql://ons_sdmx_user:change_me@localhost:5433/ons_sdmx"
python3 -m scripts.bootstrap_local_db
```

This applies the schema, loads configured datasets, and prints row counts.

With the local Docker stack running, run local smoke tests with:

```bash
docker compose --env-file .env -f infra/local/compose.yaml up -d --build
python -m scripts.smoke_test_local
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


