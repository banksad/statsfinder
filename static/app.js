const form = document.getElementById("search-form");
const input = document.getElementById("search-input");
const datasetSelect = document.getElementById("dataset-select");
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

  datasetSelect.innerHTML = `
    <option value="">All datasets</option>
    ${data.datasets.map(dataset => `
      <option value="${dataset.dataset_id}">
        ${dataset.dataset_id} — ${dataset.dataset_title}
      </option>
    `).join("")}
  `;

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

  const selectedDatasetId = datasetSelect.value;

  let url = `/v1/series/search?q=${encodeURIComponent(query)}&limit=5`;

  if (selectedDatasetId) {
    url += `&dataset_id=${encodeURIComponent(selectedDatasetId)}`;
  }

  const response = await fetch(url);

  if (!response.ok) {
    resultsDiv.innerHTML = `<p>Search failed: ${response.status}</p>`;
    return;
  }

  const data = await response.json();

  if (data.results.length === 0) {
    const datasetLabel = selectedDatasetId || "all datasets";

    resultsDiv.innerHTML = `
      <h2>Results for "${data.query}" in ${datasetLabel}</h2>
      <p>No results found.</p>
    `;
    return;
  }

  const datasetLabel = selectedDatasetId || "all datasets";

  resultsDiv.innerHTML = `
    <h2>Results for "${data.query}" in ${datasetLabel}</h2>
    ${data.results.map(result => {
      const datasetId = encodeURIComponent(result.dataset_id);
      const indicatorCode = encodeURIComponent(result.indicator_code);

      return `
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
          <a href="/series/${datasetId}/${indicatorCode}">
            View series page
          </a>
          |
          <a href="/v1/datasets/${datasetId}/series/by-indicator/${indicatorCode}" target="_blank">
            View metadata JSON
          </a>
          |
          <a href="/v1/datasets/${datasetId}/series/by-indicator/${indicatorCode}/observations?limit=5" target="_blank">
            View first 5 observations JSON
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
  runSearch(input.value);
});
