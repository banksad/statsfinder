const form = document.getElementById("search-form");
const input = document.getElementById("search-input");
const datasetSelect = document.getElementById("dataset-select");
const resultsDiv = document.getElementById("results");
const datasetSummaryDiv = document.getElementById("dataset-summary");
const searchModeSelect = document.getElementById("search-mode");

const urlParams = new URLSearchParams(window.location.search);
const initialDatasetId = urlParams.get("dataset_id") || "";
const initialQuery = urlParams.get("q");
const initialMode = urlParams.get("mode") || "semantic";

if (searchModeSelect) {
  searchModeSelect.value = initialMode;
}

if (initialQuery !== null) {
  input.value = initialQuery;
} else if (initialDatasetId) {
  input.value = "";
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

function updateSearchUrl(query, datasetId, mode) {
  const params = new URLSearchParams();

  if (mode) {
    params.set("mode", mode);
  }

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
	  <section class="dataset-panel">
	    <div class="dataset-panel-header">
	      <h2>Available datasets</h2>
	      <p class="muted">
		${escapeHtml(data.datasets.length)} datasets loaded from source-backed SDMX metadata.
	      </p>
	    </div>

	    <div class="dataset-grid">
	      ${data.datasets.map(dataset => `
		<article class="dataset-card-compact">
		  <div class="dataset-card-title">
		    <strong>${escapeHtml(dataset.dataset_id)}</strong>
		    ${dataset.dataset_title ? `<span>${escapeHtml(dataset.dataset_title)}</span>` : ""}
		  </div>

		  <p class="dataset-card-meta">
		    ${escapeHtml(dataset.series_count)} series
		    ·
		    ${escapeHtml(dataset.observation_count)} observations
		  </p>

		  <p class="dataset-card-links">
		    <a href="/browse/datasets/${encodeURIComponent(dataset.dataset_id)}">
		      Browse
		    </a>
		    |
		    <a href="${escapeHtml(dataset.source_url)}" target="_blank" rel="noopener noreferrer">
		      Source
		    </a>
		    ${dataset.documentation_url ? `
		      |
		      <a href="${escapeHtml(dataset.documentation_url)}" target="_blank" rel="noopener noreferrer">
			Docs
		      </a>
		    ` : ""}
		    ${dataset.metadata_url ? `
		      |
		      <a href="${escapeHtml(dataset.metadata_url)}" target="_blank" rel="noopener noreferrer">
			Metadata
		      </a>
		    ` : ""}
		  </p>
		</article>
	      `).join("")}
	    </div>
	  </section>
	`;
}


async function runSearch(query, options = {}) {
  const updateUrl = options.updateUrl ?? true;
  const trimmedQuery = query.trim();
  const selectedDatasetId = datasetSelect.value;
  const selectedMode = searchModeSelect ? searchModeSelect.value : "keyword";

  if (updateUrl) {
    updateSearchUrl(trimmedQuery, selectedDatasetId, selectedMode);
  }

  if (!trimmedQuery) {
    showEmptySearchPrompt();
    return;
  }

  resultsDiv.innerHTML = "<p>Searching...</p>";

  let url;

  if (selectedMode === "semantic") {
    url = `/v1/series/search/semantic?q=${encodeURIComponent(trimmedQuery)}&limit=10`;
  } else {
    url = `/v1/series/search?q=${encodeURIComponent(trimmedQuery)}&limit=10`;
  }

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
  const modeLabel = selectedMode === "semantic" ? "Semantic" : "Keyword";

  if (data.results.length === 0) {
    resultsDiv.innerHTML = `
      <h2>${escapeHtml(modeLabel)} results for "${escapeHtml(data.query)}" in ${escapeHtml(datasetLabel)}</h2>
      <p>No results found.</p>
    `;
    return;
  }

  resultsDiv.innerHTML = `
    <h2>${escapeHtml(modeLabel)} results for "${escapeHtml(data.query)}" in ${escapeHtml(datasetLabel)}</h2>

    ${data.results.map(result => {
      const datasetId = encodeURIComponent(result.dataset_id);
      const indicatorCode = encodeURIComponent(result.indicator_code);

      const metadataUrl = `/v1/datasets/${datasetId}/series/by-indicator/${indicatorCode}`;
      const csvUrl = `${metadataUrl}/observations.csv?limit=10000`;

      let scoreHtml = "";

      if (result.similarity_score !== undefined && result.similarity_score !== null) {
        const similarity = Number(result.similarity_score);
        scoreHtml = `
          <p class="result-score">
            Semantic similarity: ${similarity.toFixed(3)}
          </p>
        `;
      }

	const displayName = (
	  result.display_name
	  || result.primary_text
	  || result.indicator_name
	  || result.indicator_code
	);

	return `
	  <div class="result">
	    <h3>
	      <a href="/series/${datasetId}/${indicatorCode}">
		${escapeHtml(displayName)}
	      </a>
	    </h3>

	    <p class="result-dataset-link">
	      Dataset:
	      <a href="/browse/datasets/${datasetId}">
		${escapeHtml(result.dataset_title || result.dataset_id)}
	      </a>
	      <span class="code">${escapeHtml(result.dataset_id)}</span>
	    </p>

	    ${scoreHtml}

	    ${result.indicator_name ? `
	      <p class="series-official-name">
		Official label: ${escapeHtml(result.indicator_name)}
	      </p>
	    ` : ""}

	    <p>
	      Indicator code:
	      <span class="code">${escapeHtml(result.indicator_code)}</span>
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

if (searchModeSelect) {
  searchModeSelect.addEventListener("change", () => {
    runSearch(input.value);
  });
}

loadDatasetSummary().then(() => {
  runSearch(input.value, { updateUrl: false });
});
