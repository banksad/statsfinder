

from typing import Any

from fastapi import FastAPI, HTTPException, Path, Query
from fastapi.responses import HTMLResponse

from scripts.query_postgres import (
    build_observations_by_indicator_response,
    build_search_response,
    get_series_observations_by_indicator,
    get_series_summary_by_indicator,
    list_datasets,
    search_series,
)


app = FastAPI(
    title="ONS StatsChat Lite API",
    description="A lightweight API for discovering public ONS/IMF SDMX series.",
    version="0.1.0",
)


HOME_PAGE_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>ONS StatsChat Lite</title>
  <style>
    body {
      font-family: system-ui, sans-serif;
      max-width: 900px;
      margin: 40px auto;
      padding: 0 20px;
      line-height: 1.5;
    }

    input {
      width: 70%;
      padding: 10px;
      font-size: 1rem;
    }

    button {
      padding: 10px 14px;
      font-size: 1rem;
      cursor: pointer;
    }

    .result {
      border: 1px solid #ddd;
      border-radius: 8px;
      padding: 14px;
      margin: 14px 0;
    }

    .dataset-summary {
      border: 1px solid #ddd;
      border-radius: 8px;
      padding: 14px;
      margin: 18px 0;
      background: #fafafa;
    }

    .code {
      font-family: monospace;
      background: #f5f5f5;
      padding: 2px 5px;
      border-radius: 4px;
    }

    .muted {
      color: #666;
    }
  </style>
</head>
<body>
  <h1>ONS StatsChat Lite</h1>

  <p>
    Search public ONS/IMF SDMX series metadata.
  </p>

  <div id="dataset-summary" class="dataset-summary">
    Loading available datasets...
  </div>

  <form id="search-form">
    <input
      id="search-input"
      type="search"
      value="real gdp"
      placeholder="Try: real gdp, household, imports"
    >
    <button type="submit">Search</button>
  </form>

  <p class="muted">
    This page calls the local FastAPI endpoint:
    <span class="code">/v1/series/search</span>
  </p>

  <div id="results"></div>

  <script>
    const form = document.getElementById("search-form");
    const input = document.getElementById("search-input");
    const resultsDiv = document.getElementById("results");
    const datasetSummaryDiv = document.getElementById("dataset-summary");

    function externalLink(url, label) {
      if (!url) {
        return "";
      }

      return `
        |
        <a href="${url}" target="_blank" rel="noopener noreferrer">
          ${label}
        </a>
      `;
    }

    async function loadDatasetSummary() {
      const response = await fetch("/v1/datasets");

      if (!response.ok) {
        datasetSummaryDiv.innerHTML = "<p>Could not load dataset summary.</p>";
        return;
      }

      const data = await response.json();

      if (data.datasets.length === 0) {
        datasetSummaryDiv.innerHTML = "<p>No datasets are currently loaded.</p>";
        return;
      }

      datasetSummaryDiv.innerHTML = `
        <h2>Available datasets</h2>
        ${data.datasets.map(dataset => `
          <p>
            <strong>${dataset.dataset_id}</strong>
            ${dataset.dataset_title ? `— ${dataset.dataset_title}` : ""}
          </p>

          <p>
            Series: ${dataset.series_count}
            |
            Observations: ${dataset.observation_count}
            |
            Structure:
            <span class="code">${dataset.structure_ref}</span>
          </p>

          <p>
            <a href="${dataset.source_url}" target="_blank" rel="noopener noreferrer">
              Official SDMX source
            </a>
            ${externalLink(dataset.documentation_url, "ONS documentation")}
            ${externalLink(dataset.metadata_url, "IMF metadata")}
          </p>
        `).join("")}
      `;
    }

    async function runSearch(query) {
      resultsDiv.innerHTML = "<p>Searching...</p>";

      const url = `/v1/series/search?q=${encodeURIComponent(query)}&limit=5`;
      const response = await fetch(url);

      if (!response.ok) {
        resultsDiv.innerHTML = `<p>Search failed: ${response.status}</p>`;
        return;
      }

      const data = await response.json();

      if (data.results.length === 0) {
        resultsDiv.innerHTML = "<p>No results found.</p>";
        return;
      }

      resultsDiv.innerHTML = `
        <h2>Results for "${data.query}"</h2>
        ${data.results.map(result => `
          <div class="result">
            <h3>${result.indicator_name}</h3>

            <p>
              Indicator:
              <span class="code">${result.indicator_code}</span>
            </p>

            <p>
              Dataset:
              <span class="code">${result.dataset_id}</span>
              ${result.dataset_title ? `— ${result.dataset_title}` : ""}
            </p>

            <p>
              Structure:
              <span class="code">${result.structure_ref}</span>
            </p>

            <p>
              Frequency: ${result.frequency_name}
              |
              Period: ${result.first_period} to ${result.latest_period}
              |
              Observations: ${result.observation_count}
            </p>

            <p>
              <a href="/v1/datasets/${result.dataset_id}/series/by-indicator/${result.indicator_code}" target="_blank">
                View metadata JSON
              </a>
              |
              <a href="/v1/datasets/${result.dataset_id}/series/by-indicator/${result.indicator_code}/observations?limit=5" target="_blank">
                View first 5 observations JSON
              </a>
              ${externalLink(result.source_url, "Official SDMX source")}
              ${externalLink(result.documentation_url, "ONS documentation")}
              ${externalLink(result.metadata_url, "IMF metadata")}
            </p>
          </div>
        `).join("")}
      `;
    }

    form.addEventListener("submit", event => {
      event.preventDefault();
      runSearch(input.value);
    });

    loadDatasetSummary();
    runSearch(input.value);
  </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def home_page() -> str:
    """
    Tiny browser UI for searching series metadata.

    This is intentionally simple: one HTML page calling our JSON API.
    """
    return HOME_PAGE_HTML


@app.get("/health")
def health_check() -> dict[str, str]:
    """
    Simple health check endpoint.

    This proves the API server is running.
    """
    return {"status": "ok"}


@app.get("/v1/datasets")
def list_datasets_endpoint() -> dict[str, Any]:
    """
    Return datasets currently available in this prototype.
    """
    rows = list_datasets()

    return {
        "count": len(rows),
        "datasets": rows,
    }


@app.get("/v1/series/search")
def search_series_endpoint(
    q: str = Query(
        ...,
        min_length=1,
        description="Search query, for example 'real gdp'.",
    ),
    limit: int = Query(
        10,
        ge=1,
        le=50,
        description="Maximum number of series results to return.",
    ),
) -> dict[str, Any]:
    """
    Search for statistical series.

    Example:
        /v1/series/search?q=real%20gdp&limit=3
    """
    rows = search_series(q, limit)
    return build_search_response(q, limit, rows)


@app.get("/v1/datasets/{dataset_id}/series/by-indicator/{indicator_code}")
def get_series_by_indicator_endpoint(
    dataset_id: str = Path(
        ...,
        description="Dataset ID, for example NAG_GBR.",
    ),
    indicator_code: str = Path(
        ...,
        description="SDMX indicator code, for example NGDP_R_SA_XDC.",
    ),
) -> dict[str, Any]:
    """
    Return summary metadata for one series using public identifiers.

    This endpoint avoids requiring public users to know the internal series_id.
    """
    row = get_series_summary_by_indicator(dataset_id, indicator_code)

    if row is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Series not found for dataset_id={dataset_id} "
                f"and indicator_code={indicator_code}."
            ),
        )

    return row


@app.get(
    "/v1/datasets/{dataset_id}/series/by-indicator/{indicator_code}/observations"
)
def get_series_observations_by_indicator_endpoint(
    dataset_id: str = Path(
        ...,
        description="Dataset ID, for example NAG_GBR.",
    ),
    indicator_code: str = Path(
        ...,
        description="SDMX indicator code, for example NGDP_R_SA_XDC.",
    ),
    limit: int = Query(
        10,
        ge=1,
        le=500,
        description="Maximum number of observations to return.",
    ),
) -> dict[str, Any]:
    """
    Return observations for one series using public identifiers.

    Example:
        /v1/datasets/NAG_GBR/series/by-indicator/NGDP_R_SA_XDC/observations?limit=5
    """
    summary = get_series_summary_by_indicator(dataset_id, indicator_code)

    if summary is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Series not found for dataset_id={dataset_id} "
                f"and indicator_code={indicator_code}."
            ),
        )

    rows = get_series_observations_by_indicator(
        dataset_id,
        indicator_code,
        limit,
    )

    return build_observations_by_indicator_response(
        dataset_id,
        indicator_code,
        limit,
        rows,
    )
