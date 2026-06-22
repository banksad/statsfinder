const form = document.getElementById("search-form");
const input = document.getElementById("search-input");
const datasetSelect = document.getElementById("dataset-select");
const resultsDiv = document.getElementById("results");
const datasetSummaryDiv = document.getElementById("dataset-summary");

const urlParams = new URLSearchParams(window.location.search);
const initialDatasetId = urlParams.get("dataset_id") || "";
const initialQuery = urlParams.get("q");

if (initialQuery !== null) {
  input.value = initialQuery;
} else if (initialDatasetId) {
  input.value = "";
}

function escapeHtml(value) {
  if (value === null || value === undefined) {
    return "";
  }

  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function externalLink(url, label) {
  if (!url) {
    return "";
  }

  return `
    |
    <a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">
      ${escapeHtml(label)}
    </a>
  `;
}

function updateSearchUrl(query, datasetId) {
  const params = new URLSearchParams();

  if (query) {
    params.set("q", query);
  }

  if (datasetId) {
    params.set("dataset_id", datasetId);
  }

  const newUrl = params.toString()
    ? `/search?${params.toString()}`
    : "/search";

  window.history.replaceState({}, "", newUrl);
}

function showEmptySearchPrompt() {
  const selectedDatasetId = datasetSelect.value;
  const datasetLabel = selectedDatasetId || "all datasets";

  resultsDiv.innerHTML = `
    <h2>Search series metadata</h2>
    <p>
      Enter search terms to search within ${escapeHtml(datasetLabel)}.
    </p>
    <p class="muted">
      Try: real gdp, consumer price, imports, exports, balance of payments.
    </p>
  `;
}

async function loadDatasetSummary() {
  const response = await fetch("/v1/datasets");

  if (!response.ok) {
    datasetSummaryDiv.innerHTML = "<p>Could not load dataset summary.</p>";
    return;
  }

  const data = await response.json();

  datasetSelect.innerHTML = `
    <option value="">All datasets</option>
    ${data.datasets.map(dataset => `
      <option value="${escapeHtml(dataset.dataset_id)}">
        ${escapeHtml(dataset.dataset_id)} — ${escapeHtml(dataset.dataset_title)}
      </option>
    `).join("")}
  `;

  if (initialDatasetId) {
    datasetSelect.value = initialDatasetId;
  }

  if (data.datasets.length === 0) {
    datasetSummaryDiv.innerHTML = "<p>No datasets are currently loaded.</p>";
    return;
  }

  datasetSummaryDiv.innerHTML = `
    <h2>Available datasets</h2>
    ${data.datasets.map(dataset => `
      <p>
        <strong>${escapeHtml(dataset.dataset_id)}</strong>
        ${dataset.dataset_title ? `— ${escapeHtml(dataset.dataset_title)}` : ""}
      </p>

      <p>
        Series: ${escapeHtml(dataset.series_count)}
        |
        Observations: ${escapeHtml(dataset.observation_count)}
        |
        Structure:
        <span class="code">${escapeHtml(dataset.structure_ref)}</span>
      </p>

      <p>
        <a href="/browse/datasets/${encodeURIComponent(dataset.dataset_id)}">
          Browse dataset
        </a>
        |
        <a href="${escapeHtml(dataset.source_url)}" target="_blank" rel="noopener noreferrer">
          Official SDMX source
        </a>
        ${externalLink(dataset.documentation_url, "ONS documentation")}
        ${externalLink(dataset.metadata_url, "IMF metadata")}
      </p>
    `).join("")}
  `;
}

async function runSearch(query, options = {}) {
  const updateUrl = options.updateUrl ?? true;
  const trimmedQuery = query.trim();
  const selectedDatasetId = datasetSelect.value;

  if (updateUrl) {
    updateSearchUrl(trimmedQuery, selectedDatasetId);
  }

  if (!trimmedQuery) {
    showEmptySearchPrompt();
    return;
  }

  resultsDiv.innerHTML = "<p>Searching...</p>";

  let url = `/v1/series/search?q=${encodeURIComponent(trimmedQuery)}&limit=10`;

  if (selectedDatasetId) {
    url += `&dataset_id=${encodeURIComponent(selectedDatasetId)}`;
  }

  const response = await fetch(url);

  if (!response.ok) {
    resultsDiv.innerHTML = `<p>Search failed: ${response.status}</p>`;
    return;
  }

  const data = await response.json();
  const datasetLabel = selectedDatasetId || "all datasets";

  if (data.results.length === 0) {
    resultsDiv.innerHTML = `
      <h2>Results for "${escapeHtml(data.query)}" in ${escapeHtml(datasetLabel)}</h2>
      <p>No results found.</p>
    `;
    return;
  }

  resultsDiv.innerHTML = `
    <h2>Results for "${escapeHtml(data.query)}" in ${escapeHtml(datasetLabel)}</h2>

    ${data.results.map(result => {
      const datasetId = encodeURIComponent(result.dataset_id);
      const indicatorCode = encodeURIComponent(result.indicator_code);

      const metadataUrl = `/v1/datasets/${datasetId}/series/by-indicator/${indicatorCode}`;
      const csvUrl = `${metadataUrl}/observations.csv?limit=10000`;

      return `
        <div class="result">
          <h3>${escapeHtml(result.indicator_name || result.indicator_code)}</h3>

          <p>
            Indicator:
            <span class="code">${escapeHtml(result.indicator_code)}</span>
          </p>

          <p>
            Dataset:
            <span class="code">${escapeHtml(result.dataset_id)}</span>
            ${result.dataset_title ? `— ${escapeHtml(result.dataset_title)}` : ""}
          </p>

          <p>
            Structure:
            <span class="code">${escapeHtml(result.structure_ref)}</span>
          </p>

          <p>
            Frequency: ${escapeHtml(result.frequency_name)}
            |
            Period: ${escapeHtml(result.first_period)} to ${escapeHtml(result.latest_period)}
            |
            Observations: ${escapeHtml(result.observation_count)}
          </p>

          <p>
            <a href="/series/${datasetId}/${indicatorCode}">
              View series page
            </a>
            |
            <a href="/browse/datasets/${datasetId}">
              Browse dataset
            </a>
            |
            <a href="/v1/datasets/${datasetId}/series/by-indicator/${indicatorCode}" target="_blank" rel="noopener noreferrer">
              View metadata JSON
            </a>
            |
            <a href="/v1/datasets/${datasetId}/series/by-indicator/${indicatorCode}/observations?limit=5" target="_blank" rel="noopener noreferrer">
              View first 5 observations JSON
            </a>
            |
	    <a href="${csvUrl}">
	      Download CSV
	    </a>
            ${externalLink(result.source_url, "Official SDMX source")}
            ${externalLink(result.documentation_url, "ONS documentation")}
            ${externalLink(result.metadata_url, "IMF metadata")}
          </p>
        </div>
      `;
    }).join("")}
  `;
}

form.addEventListener("submit", event => {
  event.preventDefault();
  runSearch(input.value);
});

datasetSelect.addEventListener("change", () => {
  runSearch(input.value);
});

loadDatasetSummary().then(() => {
  runSearch(input.value, { updateUrl: false });
});
