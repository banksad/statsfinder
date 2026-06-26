# Stats Finder CLI Architecture

## Purpose

The Stats Finder CLI is a proposed command-line client for discovering, inspecting, and downloading official statistical series from Stats Finder.

The CLI should be a thin client over the public Stats Finder API. It should not parse SDMX directly, query the database directly, or maintain its own copy of official data.

The goal is:

> Find official statistics from the terminal, then download source-backed data in one command.

The CLI extends the same product principles as the main web application:

* lightweight
* fast
* developer-friendly
* source-grounded
* API-first
* easy to script
* minimal dependencies

## Relationship to Stats Finder Core

Stats Finder Core remains the system of record.

```text
Official SDMX sources
        ↓
Stats Finder Core
  FastAPI + PostgreSQL + pgvector
  Search / Browse / API / Export
        ↓
Stats Finder CLI
  Thin command-line client
```

The CLI should call public API endpoints such as:

```text
GET  /v1/series/search
GET  /v1/series/{dataset_id}/{series_key}
GET  /v1/series/{dataset_id}/{series_key}/observations
GET  /v1/discovery/nodes
GET  /v1/discovery/nodes/{slug}
POST /v1/export
```

The CLI must not duplicate the ingestion, metadata, search, or provenance logic.

## Design principles

### 1. Thin client

The CLI should be a convenience layer, not a second backend.

It should:

* call the Stats Finder API
* display concise terminal output
* save downloaded files
* support JSON output for scripting
* provide helpful error messages

It should not:

* parse raw SDMX files
* query PostgreSQL directly
* implement its own search ranking
* maintain its own catalogue
* generate or alter official metadata

### 2. API-first

Every CLI feature should map cleanly to an API endpoint.

This ensures that:

* web users and CLI users see the same data
* behaviour is consistent
* bugs are fixed in one place
* provenance remains centralised
* future adapters such as MCP can reuse the same endpoints

### 3. Terminal-native

The CLI should feel natural in a terminal.

It should support:

* simple commands
* compact tabular output
* JSON output
* file downloads
* useful exit codes
* pipe-friendly behaviour
* optional quiet mode
* optional verbose/debug mode

The CLI should not require a terminal UI framework for the first version.

A future interactive TUI can be built on top of the same client library.

### 4. Source-backed by default

The CLI should make it clear that data comes from official source-backed Stats Finder endpoints.

For example, `statsfinder series` should show:

* dataset ID
* series key
* title
* frequency
* unit
* source URL
* latest period
* API URL

Downloads should include metadata and provenance where possible.

### 5. No accounts for public data

The initial CLI should not require login.

Stats Finder’s public data discovery and export features should be open by default.

If rate limits, private datasets, or admin features are added later, authentication can be introduced only for those use cases.

## Target commands

## `statsfinder search`

Search for series by keyword or phrase.

```bash
statsfinder search "inflation"
```

Example output:

```text
1  CPI_GBR  PCPI_IX       Consumer Price Index, all items
2  CPI_GBR  PCPIH_IX      Consumer Prices Index including owner occupiers' housing costs
3  CPI_GBR  PCPICORE_IX   CPI excluding energy, food, alcohol and tobacco
```

Useful options:

```bash
statsfinder search "household spending" --limit 20
statsfinder search "GDP" --dataset NAG_GBR
statsfinder search "inflation" --json
statsfinder search "inflation" --show-urls
```

Expected API call:

```text
GET /v1/series/search?q=inflation&limit=20
```

## `statsfinder series`

Inspect a single series.

```bash
statsfinder series CPI_GBR:PCPI_IX
```

or:

```bash
statsfinder series CPI_GBR PCPI_IX
```

Example output:

```text
Consumer Price Index, all items

Dataset:     CPI_GBR — UK Consumer Price Index
Series key:  M.GB.PCPI_IX
Frequency:   Monthly
Unit:        Index
Source:      ONS/IMF SDMX
Latest:      2025-10 = 136.2

API:
https://statsfinder.uk/v1/series/CPI_GBR/M.GB.PCPI_IX
```

Useful options:

```bash
statsfinder series CPI_GBR:PCPI_IX --json
statsfinder series CPI_GBR:PCPI_IX --observations 12
statsfinder series CPI_GBR:PCPI_IX --copy-url
```

Expected API calls:

```text
GET /v1/series/{dataset_id}/{series_key}
GET /v1/series/{dataset_id}/{series_key}/observations
```

## `statsfinder observations`

Retrieve observations for a single series.

```bash
statsfinder observations CPI_GBR:PCPI_IX
```

Useful options:

```bash
statsfinder observations CPI_GBR:PCPI_IX --limit 20
statsfinder observations CPI_GBR:PCPI_IX --from 2020
statsfinder observations CPI_GBR:PCPI_IX --to 2024
statsfinder observations CPI_GBR:PCPI_IX --json
statsfinder observations CPI_GBR:PCPI_IX --csv
```

This command is useful for quick inspection without creating a download bundle.

## `statsfinder download`

Download one or more selected series.

```bash
statsfinder download CPI_GBR:PCPI_IX --format csv --output cpi.csv
```

Download several series:

```bash
statsfinder download \
  CPI_GBR:PCPI_IX \
  CPI_GBR:PCPIH_IX \
  NAG_GBR:NGDP_R_SA_XDC \
  --format csvw \
  --output uk-macro.zip
```

Supported formats:

```text
json
csv
csvw
jsonld
```

Initial implementation should support:

```text
json
csv
csvw
```

JSON-LD can come later.

Expected API call:

```text
POST /v1/export
```

Example request body:

```json
{
  "format": "csvw",
  "series": [
    {"dataset_id": "CPI_GBR", "series_key": "M.GB.PCPI_IX"},
    {"dataset_id": "CPI_GBR", "series_key": "M.GB.PCPIH_IX"}
  ]
}
```

## `statsfinder browse`

Browse the Stats Finder discovery tree.

```bash
statsfinder browse
```

Example output:

```text
Economy
Prices
Labour market
Population
Trade
Public sector finances
```

Browse a node:

```bash
statsfinder browse economy/national-accounts/gva-by-industry
```

Example output:

```text
GVA by industry

50 series
Frequency: Quarterly
Source: ONS/IMF SDMX

Commands:
  statsfinder browse economy/national-accounts/gva-by-industry --series
  statsfinder download-group gva-by-industry --format csvw --output gva-by-industry.zip
```

Useful options:

```bash
statsfinder browse --json
statsfinder browse economy/national-accounts --children
statsfinder browse gva-by-industry --series
```

Expected API calls:

```text
GET /v1/discovery/nodes
GET /v1/discovery/nodes/{slug}
GET /v1/discovery/nodes/{slug}/series
```

## `statsfinder download-group`

Download all series in a browse/discovery node.

```bash
statsfinder download-group gva-by-industry --format csvw --output gva-by-industry.zip
```

This supports use cases such as:

```text
GVA
  → GVA by industry
      → download all 50 series
```

The CLI does not resolve group membership itself. It asks Stats Finder Core to resolve the group.

Expected API call:

```text
POST /v1/export
```

Example request body:

```json
{
  "format": "csvw",
  "group_slug": "gva-by-industry"
}
```

The API should return a generated export bundle.

## `statsfinder api-url`

Print the API URL for a series, search, group, or export request.

```bash
statsfinder api-url series CPI_GBR:PCPI_IX
```

Example output:

```text
https://statsfinder.uk/v1/series/CPI_GBR/M.GB.PCPI_IX
```

This is useful for analysts who want to move from CLI exploration to code.

## Configuration

The CLI should support a default API base URL.

Default:

```text
https://statsfinder.uk
```

Local development:

```bash
statsfinder --base-url http://127.0.0.1:8000 search "inflation"
```

Environment variable:

```bash
export STATSFINDER_API_BASE_URL=http://127.0.0.1:8000
```

Optional config file:

```text
~/.config/statsfinder/config.toml
```

Example:

```toml
api_base_url = "https://statsfinder.uk"
default_format = "csvw"
```

The first version can avoid a config file and use only defaults, flags, and environment variables.

## Output modes

The CLI should support three main output modes.

### Human-readable text

Default mode.

```bash
statsfinder search "inflation"
```

This should produce compact readable output.

### JSON

Machine-readable mode.

```bash
statsfinder search "inflation" --json
```

This should print valid JSON to stdout and no decorative text.

### File output

Download mode.

```bash
statsfinder download CPI_GBR:PCPI_IX --format csvw --output cpi.zip
```

This writes a file and prints a short success message.

## Exit codes

The CLI should use predictable exit codes.

```text
0  success
1  general error
2  invalid arguments
3  API unavailable
4  not found
5  export failed
```

This makes the CLI useful in scripts and CI jobs.

## Error handling

Error messages should be concise and useful.

Example:

```text
Series not found: CPI_GBR:BAD_CODE

Try:
  statsfinder search "BAD_CODE"
```

For API errors:

```text
Could not reach Stats Finder API at http://127.0.0.1:8000

Check:
  - is the API running?
  - is STATSFINDER_API_BASE_URL correct?
```

For large exports:

```text
This export contains 1,250 series and approximately 500,000 observations.
Use --confirm to continue.
```

## Data formats

## JSON

JSON should mirror the public API response.

This is useful for scripting and integration.

## CSV

CSV should use long/tidy format for multiple series.

Example:

```csv
dataset_id,series_key,indicator_code,indicator_name,time_period,obs_value,unit,frequency,source_url
CPI_GBR,M.GB.PCPI_IX,PCPI_IX,Consumer Price Index,2024-01,131.5,Index,Monthly,https://...
NAG_GBR,Q.GB.NGDP_R_SA_XDC,NGDP_R_SA_XDC,GDP chained volume measure,2024-Q1,540000,Millions,Quarterly,https://...
```

Long format is preferred because selected series may have different:

* frequencies
* units
* time ranges
* dimensions
* source datasets

## CSVW

CSVW should be the preferred rich export format.

A CSVW export should be a zip bundle:

```text
statsfinder-export.zip
  observations.csv
  csvw-metadata.json
  README.txt
```

CSVW gives users a plain CSV file plus machine-readable metadata and provenance.

## JSON-LD

JSON-LD should be a later feature.

It is useful for linked data and semantic web use cases, but it needs careful modelling of:

* datasets
* series
* observations
* concepts
* codelists
* units
* sources
* provenance

CSVW should come first.

## Internal implementation

A future Python package could be structured as:

```text
statsfinder_cli/
  __init__.py
  main.py
  client.py
  config.py
  output.py
  commands/
    search.py
    series.py
    observations.py
    browse.py
    download.py
```

Suggested dependencies for a first version:

* `typer` or `argparse`
* `httpx`
* optionally `rich` for tables

For maximum lightweight discipline, start with:

* `argparse`
* `httpx`
* standard-library JSON and CSV tools

Add richer terminal formatting only when needed.

## First implementation milestone

The first useful version should support:

```text
statsfinder search
statsfinder series
statsfinder download
```

That is enough to prove the CLI concept.

Minimum commands:

```bash
statsfinder search "inflation"
statsfinder series CPI_GBR:PCPI_IX
statsfinder download CPI_GBR:PCPI_IX --format json --output cpi.json
```

## Second implementation milestone

Add discovery-tree support:

```text
statsfinder browse
statsfinder browse {node_slug}
statsfinder download-group {node_slug}
```

This supports grouped use cases such as downloading all GVA by industry series.

## Future interactive TUI

A future interactive terminal UI could be built on top of the same client library.

Example:

```bash
statsfinder tui
```

Possible features:

* search input
* keyboard selection
* browse tree navigation
* selected series basket
* export action
* inspect metadata panel

The TUI should remain an optional layer.

The CLI should work fully without it.

## Relationship to MCP

The CLI and MCP server should both be adapters over the same Stats Finder API.

```text
Stats Finder Core API
        ↓
CLI client
        ↓
human terminal users

Stats Finder Core API
        ↓
MCP server
        ↓
AI agents and tools
```

Neither adapter should own data logic.

This keeps Stats Finder Core as the single trusted source of source-backed statistical retrieval.

## Security and trust

The CLI should treat Stats Finder API responses as source-backed data, but it should still display provenance clearly.

Downloads should include:

* generated timestamp
* Stats Finder version, if available
* dataset IDs
* source URLs
* documentation URLs
* series keys
* indicator labels
* frequency
* units
* observation values

For public data, no authentication should be required.

If authentication is later introduced, it should be optional and limited to private/admin use cases.

## Summary

The Stats Finder CLI should make official statistics fast to discover and easy to download from the terminal.

It should be:

```text
thin
fast
scriptable
source-backed
developer-friendly
API-first
```

Its guiding principle is:

> The CLI is not a second Stats Finder. It is a terminal-shaped doorway into Stats Finder Core.


## Current status

There is no packaged CLI in the current repository. The CLI remains a proposed
thin client over the public API. Existing scripts are development and ingestion
utilities, not a user-facing `statsfinder` command.

The current API is already sufficient for a minimal future CLI to search, inspect,
and download single-series CSV files:

```text
GET /v1/series/search
GET /v1/series/search/semantic
GET /v1/datasets/{dataset_id}/series/by-indicator/{indicator_code}
GET /v1/datasets/{dataset_id}/series/by-indicator/{indicator_code}/observations
GET /v1/datasets/{dataset_id}/series/by-indicator/{indicator_code}/observations.csv
```

## Lightweight CLI rule

If a CLI is added, keep it as a very small API wrapper. It should not duplicate
SDMX parsing, database access, ranking, semantic retrieval, or provenance logic.
A first version should prefer a few scriptable commands over an interactive TUI or
large dependency stack.
