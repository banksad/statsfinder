# Automated ingest of latest data

Scope and design for keeping StatsFinder's datasets fresh automatically, and for
adding new datasets with minimal effort.

This document is a scoping note for issue #26. It records the current state, the
gaps that block automation, a recommended design, and a concrete task list. It
does not change runtime behaviour on its own.

## Goal

Today every dataset is refreshed by a human running the ingest pipeline by hand.
The official ONS/IMF source files are republished on a schedule (monthly or
quarterly for most series), so the database drifts out of date between manual
runs. We want a scheduled, idempotent job that re-fetches the official sources
and reloads the database with no manual steps, and a registry-driven path for
adding new datasets.

Design rule, unchanged: **the LLM may interpret, the database must answer.**
Automated ingest only moves official published values into Postgres faster; it
never generates or edits observations.

## Current pipeline (manual)

The registry [`config/datasets.json`](../config/datasets.json) is the single
source of truth. Each entry points at an official `source_url` and the on-disk
paths for its intermediate files. For each dataset the flow is:

```
download source XML   (manual / out of band — see gap 1)
  -> scripts.ingest.parse_dataset_to_records   raw XML  -> series + observation JSON
  -> scripts.ingest.enrich_dataset_series       + IMF codelist labels + search_text
  -> scripts.db.bootstrap_local_db              apply schema + load all datasets
```

Enrichment also needs the IMF ECOFIN codelists:

```
download ECOFIN DSD (~43MB)   ->  scripts.inspect.parse_codelists
  -> data/processed/ecofin_codelist_lookup.json
```

Loading is already safe to repeat: `load_dataset_to_postgres` upserts with
`ON CONFLICT ... DO UPDATE`, and the schema files use `CREATE TABLE IF NOT
EXISTS`. So re-running the whole pipeline is non-destructive by design — the
missing piece is automation, not idempotency.

If semantic search is enabled, new/changed series additionally need
`scripts.ingest.upsert_series_search_documents` then
`scripts.ingest.embed_series_search_documents` (Gemini) to refresh embeddings.

## Gaps that block automation

These are the concrete things missing today. Each is small.

1. **No download step in the codebase.** `parse_dataset_to_records` reads
   `raw_file_path` from local disk; nothing in the repo fetches `source_url`
   first. (The local bring-up did this with a throwaway script.) Automation needs
   a first-class fetch step driven by the registry.
2. **DSD source URL is not in config.** The ECOFIN DSD URL is only hard-coded in
   `scripts/inspect/inspect_imf_data_domains.py`. The working full-DSD query is:
   `https://sdmxcentral.imf.org/sdmx/v2/structure/datastructure/IMF/ECOFIN_DSD/1.0?references=all&detail=full`.
   It belongs in config (e.g. a `config/structures.json` or a field on the
   registry) so the job is fully declarative.
3. **`Dockerfile` does not `COPY sql/`.** The image used by Cloud Run has no
   schema files, so any in-container `bootstrap_local_db` fails with
   "No SQL schema files found in /app/sql". Add `COPY sql ./sql`.
4. **No single ingest entrypoint.** The steps are separate modules. Automation
   wants one command, e.g. `python -m scripts.ingest.refresh_all`, that runs
   fetch -> codelists -> parse -> enrich -> load (-> embed) for every registered
   dataset and exits non-zero on failure.
5. **README references stale flat module paths** (`scripts.bootstrap_local_db`);
   real paths are `scripts.db.*`, `scripts.ingest.*`, `scripts.inspect.*`.
   Worth fixing so the documented commands actually run.

Good news: [`app/services/postgres.py`](../app/services/postgres.py) `get_dsn()`
already supports both `ONS_SDMX_DB_DSN` and the Cloud SQL socket
(`CLOUD_SQL_INSTANCE_CONNECTION_NAME` + `DB_NAME`/`DB_USER`/`DB_PASSWORD`), so an
ingest job can reuse the exact same image and DB wiring as the service.

## Recommended design: Cloud Run Job + Cloud Scheduler

The deploy guide already states data loading should be *"separate administrative
tasks, not through the public Cloud Run service."* A **Cloud Run Job** is the
natural fit and reuses everything that already exists:

```
Cloud Scheduler (cron, e.g. weekly)
  -> triggers Cloud Run Job "statsfinder-ingest"
       same image as the service, command: python -m scripts.ingest.refresh_all
       --add-cloudsql-instances <CONNECTION_NAME>
       service account: statsfinder-ingest@... (roles/cloudsql.client [+ aiplatform.user for embeddings])
  -> Job: fetch sources -> parse codelists -> parse -> enrich -> upsert into Cloud SQL
  -> (optional) refresh embeddings via Gemini
```

Why a Job, not the web service:
- The service is read-only at runtime; ingestion is a batch task with a different
  lifecycle, resource profile (the 43MB DSD parse needs more memory), and
  failure semantics. Keeping it separate protects request latency and lets the
  job run to completion past any HTTP timeout.
- It reuses the same container, the same `get_dsn()` Cloud SQL path, the same
  secret (`statsfinder-db-password`), and the same runtime SA pattern as the
  documented deploy.

Cadence: **weekly** is plenty given monthly/quarterly source updates; ingest is
idempotent so an extra run is harmless. Tighten later if a faster SLA is wanted.

### Alternatives considered

- **GitHub Actions on a cron.** Works, but reaching Cloud SQL from GitHub needs
  the Cloud SQL Auth Proxy + Workload Identity Federation, and runs ingestion
  outside the deployment boundary. More moving parts than a Cloud Run Job for the
  same result. Reasonable if the team prefers to keep all scheduled work in CI.
- **Admin endpoint on the service** triggered by Scheduler. Rejected: it couples
  a long batch job to the public read-only service and widens its attack surface.
- **Commit processed JSON to the repo** and load on deploy. Rejected: bloats git
  with regenerated data and ties data freshness to code deploys.

## Change detection (optional, nice-to-have)

To avoid needless work and embedding spend, the fetch step can do a conditional
GET (`If-None-Modified` / `ETag`) or hash each downloaded file and skip
parse/enrich/load when a dataset's source is byte-identical to last run. Store
the last seen ETag/hash per dataset (a small table or object in the DB). Not
required for a first version — full re-ingest is cheap for these file sizes — but
it makes embedding refresh much cheaper.

## Observability and safety

- The job should print per-dataset series/observation counts (the loaders
  already do) and exit non-zero on any failure so Scheduler/alerting can see it.
- Wrap each dataset so one bad source file fails only that dataset, and the job
  reports which succeeded/failed rather than aborting the whole run.
- Idempotent upserts mean a partial run is safe to retry.
- Alert on: job failure, zero rows loaded for a dataset that previously had rows,
  or a source returning non-200.

## Adding new datasets (the other half of #26)

Adding a dataset is registry-only: append an entry to
[`config/datasets.json`](../config/datasets.json) (same shape as existing
entries — `dataset_id`, `source_url`, `data_domain_code`/`label`,
`structure_ref`, and the four file paths) and the pipeline picks it up. The
ONS IMF SDDS endpoint `https://static.ons.gov.uk/imf/<CODE>_GBR.xml` currently
publishes these UK datasets; **all are now in the registry**:

| Code | Domain | Status |
|------|--------|--------|
| NAG, CPI, BOP, SBS, GGO, GGD | original six | loaded |
| PPI | Producer price indices | added |
| CGO | Central government operations | added |
| CGD | Central government debt | added |
| DCS | Depository Corporations Survey | added |
| CBS | Central Bank Survey | added |
| EMP | Employment | added |
| IND | Index of economic activity | added |
| POP | Population | added |

A periodic "discovery" check could probe the ONS endpoint for new `<CODE>_GBR`
files and open an issue when one appears, but for now the catalogue is small and
curated by hand.

## Task checklist

Make ingest scriptable (prerequisites, all small):

- [ ] Add a registry-driven fetch step (download `source_url` -> `raw_file_path`).
- [ ] Move the ECOFIN DSD URL into config and fetch it in the pipeline.
- [ ] Add `COPY sql ./sql` to the `Dockerfile`.
- [ ] Add a single `scripts.ingest.refresh_all` entrypoint (fetch -> codelists ->
      parse -> enrich -> load, with per-dataset error isolation and counts).
- [ ] Fix stale module paths in the README.

Schedule it (cloud, with the repo owner / cloud admin):

- [ ] Build the ingest image (same Dockerfile) and create Cloud Run Job
      `statsfinder-ingest` with the Cloud SQL connection + DB secret.
- [ ] Create a dedicated ingest service account (`roles/cloudsql.client`, plus
      `roles/aiplatform.user` if refreshing embeddings).
- [ ] Create a Cloud Scheduler weekly trigger for the job.
- [ ] (If semantic search stays on) append `upsert_series_search_documents` +
      `embed_series_search_documents` to the job.
- [ ] Add change detection (ETag/hash) to skip unchanged sources.
- [ ] Wire failure alerting.
```
