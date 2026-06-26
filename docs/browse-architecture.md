# Stats Finder Browse Architecture

## Purpose

The Browse feature gives users a structured way to explore official statistical series by topic, dataset, concept, and statistical breakdown.

Search is for users who know the words they want to use.

Browse is for users who know the area they are interested in, but want to understand what exists.

The core browse idea is:

> Let users move from a broad statistical topic to a meaningful group of source-backed series, then inspect or download those series.

Example:

```text
Economy
  National accounts
    Gross value added
      GVA by industry
        Download all 50 series
```

Browse should support Stats Finder’s wider product principles:

* lightweight
* fast
* SDMX-aware
* source-grounded
* API-first
* export-friendly
* clear about provenance
* useful without becoming a dashboard

## Relationship to Search

Stats Finder should have two first-class discovery modes.

```text
Search:
  “I know roughly what I want to find.”

Browse:
  “I want to explore what exists in this topic area.”
```

Search is intent-driven.

Browse is structure-driven.

Both should ultimately resolve to the same core objects:

* datasets
* series
* observations
* codelists
* metadata
* source URLs
* export bundles

Search and Browse should therefore share the same underlying data model where possible.

## Product experience

The top-level navigation should remain simple:

```text
Search   Browse   API
```

Later this may become:

```text
Search   Browse   API   CLI   MCP
```

The Browse page should start with a topic tree.

Example:

```text
Economy
Prices
Labour market
Population
Trade
Public sector finances
```

A user can drill down:

```text
Economy
  National accounts
    Gross value added
      GVA by industry
      GVA by region
      GVA by sector
```

A terminal browse node might show:

```text
GVA by industry

50 series
Dataset: UK National Accounts
Frequency: Quarterly
Source: ONS/IMF SDMX

Actions:
  Download CSVW
  Download JSON
  Add all to basket

Included series:
  Agriculture
  Manufacturing
  Construction
  Services
  ...
```

The Browse feature should make grouped export easy.

The target user flow is:

```text
Browse topic
→ open group
→ review count and provenance
→ download all matching series
```

## SDMX relationship

SDMX already contains concepts that can support browsing.

Stats Finder should use these where available:

* Category Schemes
* Categories
* Dataflows
* Data Structure Definitions
* Codelists
* Hierarchies
* Concepts

The useful distinction is:

```text
SDMX Categories:
  useful for organising datasets and dataflows into topic trees

SDMX Hierarchies:
  useful for organising codes inside dimensions, such as industries,
  geographies, sectors, products, or classifications

Stats Finder discovery nodes:
  lightweight internal browse nodes that can be mapped to SDMX metadata
  where available, or curated by Stats Finder where source metadata is incomplete
```

Stats Finder should not require every source to provide perfect SDMX Category Schemes or Hierarchies before Browse becomes useful.

Instead, Browse should support three source types:

```text
sdmx_category
sdmx_hierarchy
statsfinder_curated
```

This allows Stats Finder to be honest:

```text
This browse grouping is curated by Stats Finder.
The underlying series and observations are official source-backed data.
```

## Core design rule

Browse should select official series through metadata.

It should not manually duplicate observations or create unofficial statistical values.

The core pattern is:

```text
browse node
→ resolves to official series IDs
→ export engine retrieves official observations
→ CSVW / JSON / JSON-LD bundle includes metadata and provenance
```

This keeps Browse lightweight and trustworthy.

## Data model

Browse should use a small discovery-tree layer.

A suggested table:

```sql
CREATE TABLE discovery_nodes (
    discovery_node_id BIGSERIAL PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    parent_slug TEXT REFERENCES discovery_nodes(slug),
    title TEXT NOT NULL,
    description TEXT,
    node_type TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_id TEXT,
    dataset_id TEXT,
    selection_rule JSONB,
    member_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Possible `node_type` values:

```text
category
dataset
series_group
dimension_group
code_group
```

Possible `source_type` values:

```text
sdmx_category
sdmx_hierarchy
statsfinder_curated
```

Example nodes:

```text
economy
  title: Economy
  node_type: category
  source_type: statsfinder_curated

national-accounts
  parent_slug: economy
  title: National accounts
  node_type: category
  source_type: statsfinder_curated

gross-value-added
  parent_slug: national-accounts
  title: Gross value added
  node_type: category
  source_type: statsfinder_curated

gva-by-industry
  parent_slug: gross-value-added
  title: GVA by industry
  node_type: series_group
  source_type: statsfinder_curated
  dataset_id: NAG_GBR
```

## Materialised group membership

For performance and clarity, Browse should materialise series membership.

```sql
CREATE TABLE discovery_node_series (
    discovery_node_id BIGINT NOT NULL REFERENCES discovery_nodes(discovery_node_id),
    series_id BIGINT NOT NULL REFERENCES series(series_id),
    PRIMARY KEY (discovery_node_id, series_id)
);
```

This means:

```text
/browse/gva-by-industry
→ known set of series IDs
→ fast display
→ fast export
```

Materialised membership is preferable to dynamically reasoning from scratch on every request.

It also makes the system easy to debug:

```sql
SELECT COUNT(*)
FROM discovery_node_series
WHERE discovery_node_id = ...;
```

## Selection rules

Each browse node may also store a `selection_rule`.

Example:

```json
{
  "dataset_id": "NAG_GBR",
  "indicator_family": "GVA",
  "breakdown_dimension": "industry"
}
```

The `selection_rule` explains how membership was created.

However, user-facing requests should rely on materialised membership for speed and predictability.

The selection rule is useful for:

* rebuilding membership
* explaining the grouping
* auditing curated nodes
* testing whether metadata changes affect group membership

## API design

Browse should be API-first.

Suggested endpoints:

```text
GET /v1/discovery/nodes
GET /v1/discovery/nodes/{slug}
GET /v1/discovery/nodes/{slug}/children
GET /v1/discovery/nodes/{slug}/series
POST /v1/export
```

### Root nodes

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
    },
    {
      "slug": "prices",
      "title": "Prices",
      "node_type": "category",
      "source_type": "statsfinder_curated"
    }
  ]
}
```

### Node detail

```text
GET /v1/discovery/nodes/gva-by-industry
```

Returns metadata about the node.

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

### Node series

```text
GET /v1/discovery/nodes/gva-by-industry/series
```

Returns the series included in the node.

Example:

```json
{
  "slug": "gva-by-industry",
  "title": "GVA by industry",
  "series_count": 50,
  "series": [
    {
      "dataset_id": "NAG_GBR",
      "series_key": "...",
      "indicator_code": "...",
      "indicator_name": "GVA: Agriculture",
      "frequency": "Quarterly",
      "unit": "£ million"
    }
  ]
}
```

### Group export

Browse should integrate with the same export endpoint used by manually selected series.

Example:

```text
POST /v1/export
```

Request:

```json
{
  "format": "csvw",
  "group_slug": "gva-by-industry"
}
```

The export service resolves the group slug to official series IDs and returns a download bundle.

## HTML routes

Suggested HTML routes:

```text
/browse
/browse/{slug}
```

The root page shows top-level nodes.

The node page shows:

* title
* description
* source type
* member count
* child nodes
* included series
* export actions
* provenance note

Example page structure:

```text
GVA by industry

Gross value added series broken down by industry.

Source of grouping:
  Stats Finder curated navigation

Underlying data:
  Official ONS/IMF SDMX series

50 series available

[Download CSVW]
[Download JSON]
[Add all to basket]

Included series:
  ...
```

## Export behaviour

Browse should make grouped export easy, but exports should include clear counts before download.

For example:

```text
This export contains 50 series and approximately 12,000 observations.
```

For small groups, the download can proceed immediately.

For large groups, the UI or API may require confirmation.

Suggested thresholds:

```text
0–100 series:
  download immediately

101–1,000 series:
  show confirmation

1,000+ series:
  require explicit confirmation or background export later
```

These thresholds can be adjusted later.

## Export format

Grouped exports should use long/tidy data by default.

Example:

```csv
dataset_id,series_key,indicator_code,indicator_name,time_period,obs_value,unit,frequency,source_url
NAG_GBR,...,GVA_AGRI,GVA: Agriculture,2023-Q1,12345,£ million,Quarterly,https://...
NAG_GBR,...,GVA_MANU,GVA: Manufacturing,2023-Q1,45678,£ million,Quarterly,https://...
```

Long format works well for groups because series may have different:

* time ranges
* units
* frequencies
* dimensions
* labels
* attributes

Wide format should not be the default.

CSVW is especially suitable for grouped exports because it allows Stats Finder to package:

```text
observations.csv
csvw-metadata.json
README.txt
```

## Browse and basket integration

Browse should support both direct group export and basket workflows.

Direct group export:

```text
Browse → GVA by industry → Download all
```

Basket workflow:

```text
Browse → GVA by industry → Add all to basket
Search → inflation → add one series
Download selected
```

The basket remains browser-side and stores only stable series references.

Example:

```json
[
  {"dataset_id": "NAG_GBR", "series_key": "..."},
  {"dataset_id": "CPI_GBR", "series_key": "..."}
]
```

This avoids accounts, dashboards, and server-side sessions.

## Browse and Search integration

Browse nodes should be discoverable through Search.

For example, searching for:

```text
industry gva
```

could return:

```text
Series results:
  GVA: Manufacturing
  GVA: Construction

Browse groups:
  GVA by industry
```

This lets users move naturally between Search and Browse.

Search results can include both:

* series matches
* browse node matches

But they should be clearly labelled.

## Provenance

Browse introduces a subtle provenance distinction.

A browse grouping may be official, semi-official, or curated.

The underlying series and observations remain official source-backed data.

Stats Finder should show both facts.

Example:

```text
Grouping source:
  Stats Finder curated navigation

Data source:
  Official ONS/IMF SDMX

Series source:
  NAG_GBR

Structure reference:
  IMF_ECOFIN_DSD_1_0
```

This prevents a curated browse tree from being mistaken for official SDMX metadata.

## Metadata quality benefits

Browse can help identify metadata problems.

For example:

* missing labels
* unclear codelists
* duplicate labels
* unhelpful indicator names
* missing hierarchy information
* inconsistent group membership
* categories that do not map cleanly to useful user journeys

A future script could generate a browse quality report:

```bash
python3 -m scripts.discovery_quality_report
```

Example output:

```text
Node: gva-by-industry
  member_count: 50
  missing industry labels: 0
  duplicate series titles: 2
  missing units: 0
```

This supports Stats Finder’s wider SDMX quality argument.

## Implementation stages

### Stage 1: Curated static browse tree

Create a small curated tree manually.

Example:

```text
Economy
  National accounts
    Gross value added
      GVA by industry
Prices
  Consumer prices
```

Use a simple JSON seed file or SQL seed script.

Goal:

```text
prove the Browse UX without building a full SDMX registry
```

### Stage 2: Discovery tables

Add:

```text
discovery_nodes
discovery_node_series
```

Seed them from curated configuration.

### Stage 3: Browse pages

Add:

```text
/browse
/browse/{slug}
```

Use Jinja2 templates.

### Stage 4: Browse API

Add:

```text
GET /v1/discovery/nodes
GET /v1/discovery/nodes/{slug}
GET /v1/discovery/nodes/{slug}/series
```

### Stage 5: Group export

Allow:

```json
{
  "format": "csvw",
  "group_slug": "gva-by-industry"
}
```

in the export API.

### Stage 6: SDMX category and hierarchy import

Where source metadata provides useful Category Schemes or Hierarchies, import them and mark source type appropriately.

### Stage 7: Search integration

Allow search results to include matching browse groups as well as individual series.

## What Browse should avoid

Browse should not become:

* a dashboard builder
* a manually maintained spreadsheet of statistical products
* a second metadata system detached from SDMX
* a place where unofficial values are created
* a complex frontend tree component requiring a build step
* a system that hides whether groupings are official or curated

Browse should remain:

```text
small
fast
transparent
source-backed
export-friendly
```

## Relationship to CLI and MCP

Browse should expose clean API endpoints so future adapters can use it.

CLI example:

```bash
statsfinder browse
statsfinder browse gva-by-industry
statsfinder download-group gva-by-industry --format csvw
```

MCP example tools:

```text
list_browse_nodes()
get_browse_node(slug)
get_browse_node_series(slug)
export_browse_node(slug, format)
```

The CLI and MCP services should not implement their own browse logic.

They should call Stats Finder Core.

## Summary

Browse is the structured discovery layer of Stats Finder.

It complements Search by helping users explore official statistics through topics, datasets, concepts, and statistical breakdowns.

The core Browse pattern is:

```text
topic tree
→ meaningful group
→ official series
→ source-backed export
```

Browse strengthens the product because it supports users who do not know the right search term, indicator code, or SDMX structure.

It also supports one of Stats Finder’s strongest use cases:

> Find a meaningful group of official series, then download the whole group in a clean machine-readable format.

Browse should be implemented as a lightweight discovery tree over official metadata, with clear provenance and direct integration with the export API.


## Current implementation

The current Browse implementation is intentionally modest:

```text
GET /browse
GET /browse/datasets/{dataset_id}
GET /v1/datasets
GET /v1/datasets/{dataset_id}
GET /v1/datasets/{dataset_id}/series
```

The Browse landing page leads users to configured datasets. A dataset Browse page
shows source-backed dataset metadata, a full series table, and optional semantic
matches within that dataset when a query is supplied. This gives users a useful
structured path without requiring a complete curated topic tree first.

Current configured datasets are:

```text
NAG_GBR  UK National Accounts
CPI_GBR  UK Consumer Price Index
BOP_GBR  UK Balance of Payments
SBS_GBR  UK Sectoral Balance Sheet
GGO_GBR  UK General Government Operations
```

The future discovery-tree model remains useful, but it should be introduced only
when it simplifies real browse journeys. Until then, dataset-level browsing is a
valid lightweight product surface.

## Lightweight browse rule

Browse should not become a dashboard builder or a second metadata system. Keep it
as a simple route from topic or dataset context to official series, observations,
and exports. Curated nodes should be small, transparent, and easy to delete or
replace when better SDMX metadata becomes available.
