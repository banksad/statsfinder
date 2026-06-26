const chatForm = document.getElementById("chat-form");
const questionInput = document.getElementById("chat-question");
const datasetSelect = document.getElementById("chat-dataset");
const answerContainer = document.getElementById("chat-answer");
const selectedSeriesContainer = document.getElementById("chat-selected-series");
const referencesContainer = document.getElementById("chat-references");
const debugContainer = document.getElementById("chat-debug");
const submitButton = document.getElementById("chat-submit-button");

function formatScore(value) {
  const number = Number(value);

  if (!Number.isFinite(number)) {
    return "";
  }

  return number.toFixed(3);
}


function seriesTitle(row) {
  return (
    row.indicator_name ||
    row.display_name ||
    row.primary_text ||
    row.indicator_code ||
    "Untitled series"
  );
}

function datasetTitle(row) {
  const datasetId = row.dataset_id || "";
  const datasetName = row.dataset_title || "";

  if (datasetId && datasetName) {
    return `${datasetId} — ${datasetName}`;
  }

  return datasetId || datasetName || "Unknown dataset";
}

function datasetUrl(row) {
  if (!row.dataset_id) {
    return "#";
  }

  return `/browse/datasets/${encodeURIComponent(row.dataset_id)}`;
}

function buildSeriesMetaParts(row) {
  const parts = [];

  if (row.frequency_name || row.frequency_code) {
    parts.push(row.frequency_name || row.frequency_code);
  }

  if (row.measure_type) {
    parts.push(row.measure_type);
  }

  if (row.seasonal_adjustment) {
    parts.push(row.seasonal_adjustment);
  }

  if (row.base_period) {
    parts.push(`base period ${row.base_period}`);
  }

  if (row.unit) {
    parts.push(row.unit);
  }

  const periods = [row.first_period, row.latest_period].filter(Boolean).join(" to ");

  if (periods) {
    parts.push(periods);
  }

  return parts;
}

function renderSelectedSeries(seriesRows) {
  if (!selectedSeriesContainer) {
    return;
  }

  if (!seriesRows || seriesRows.length === 0) {
    selectedSeriesContainer.innerHTML = "<p>No specific data series were selected.</p>";
    return;
  }

  const items = seriesRows.map((row) => {
    const title = escapeHtml(seriesTitle(row));
    const url = escapeHtml(row.series_url || "#");

    const datasetLabel = escapeHtml(datasetTitle(row));
    const datasetHref = escapeHtml(datasetUrl(row));

    const metaParts = buildSeriesMetaParts(row)
      .map((part) => `<span>${escapeHtml(part)}</span>`)
      .join("");

    const displayName = row.display_name
      ? `<div class="chat-series-display-name">${escapeHtml(row.display_name)}</div>`
      : "";

    const codeLine = [
      row.indicator_code ? `Code: ${row.indicator_code}` : null,
      row.series_id ? `Series ID: ${row.series_id}` : null,
      row.observation_count ? `${row.observation_count} observations` : null,
    ]
      .filter(Boolean)
      .map(escapeHtml)
      .join(" · ");

    return `
      <li class="chat-series-card">
        <a class="chat-series-title" href="${url}">${title}</a>

        ${displayName}

        <div class="chat-series-dataset">
          <a href="${datasetHref}">${datasetLabel}</a>
        </div>

        <div class="chat-series-meta">
          ${metaParts}
        </div>

        <div class="chat-series-code">
          ${codeLine}
        </div>
      </li>
    `;
  });

  selectedSeriesContainer.innerHTML = `<ul class="chat-series-list">${items.join("")}</ul>`;
}

function renderReferences(referenceRows) {
  if (!referencesContainer) {
    return;
  }

  if (!referenceRows || referenceRows.length === 0) {
    referencesContainer.innerHTML = "<p>No reference passages were selected.</p>";
    return;
  }

  const items = referenceRows.map((row) => {
    const sourceTitle = escapeHtml(row.source_title || "Reference source");
    const page = row.page_number ? `PDF page ${escapeHtml(row.page_number)}` : "page not available";
    const text = escapeHtml((row.chunk_text || "").slice(0, 800));
    const score = formatScore(row.similarity_score);

    return `
      <li>
        <strong>${sourceTitle}</strong> · ${page}${score ? ` · similarity ${score}` : ""}
        <blockquote>${text}</blockquote>
      </li>
    `;
  });

  referencesContainer.innerHTML = `<ul class="chat-source-list">${items.join("")}</ul>`;
}

function renderDebug(debug) {
  if (!debugContainer) {
    return;
  }

  if (!debug) {
    debugContainer.innerHTML = "<p>No debug information available.</p>";
    return;
  }

  const retrievalQueries = debug.retrieval_queries || [];
  const candidateSeries = debug.candidate_series || [];
  const candidateReferences = debug.candidate_references || [];

  const queryItems = retrievalQueries
    .map((query) => `<li>${escapeHtml(query)}</li>`)
    .join("");

  const seriesItems = candidateSeries
    .map((row) => {
      const title = escapeHtml(seriesTitle(row));
      const score = formatScore(row.similarity_score);
      const url = escapeHtml(row.series_url || "#");

      return `
        <li>
          <a href="${url}">${title}</a>
          ${row.dataset_id ? ` · ${escapeHtml(row.dataset_id)}` : ""}
          ${row.frequency_name ? ` · ${escapeHtml(row.frequency_name)}` : ""}
          ${score ? ` · similarity ${score}` : ""}
        </li>
      `;
    })
    .join("");

  const referenceItems = candidateReferences
    .map((row) => {
      const sourceTitle = escapeHtml(row.source_title || "Reference source");
      const score = formatScore(row.similarity_score);

      return `
        <li>
          ${sourceTitle}
          ${row.page_number ? ` · PDF page ${escapeHtml(row.page_number)}` : ""}
          ${score ? ` · similarity ${score}` : ""}
        </li>
      `;
    })
    .join("");

  debugContainer.innerHTML = `
    <h3>Retrieval queries</h3>
    <ul>${queryItems || "<li>None</li>"}</ul>

    <h3>Candidate SDMX series</h3>
    <ul>${seriesItems || "<li>None</li>"}</ul>

    <h3>Candidate reference passages</h3>
    <ul>${referenceItems || "<li>None</li>"}</ul>
  `;
}

function setLoading(isLoading) {
  if (submitButton) {
    submitButton.disabled = isLoading;
    submitButton.textContent = isLoading ? "Asking..." : "Ask";
  }
}

async function askChat() {
  const question = questionInput.value.trim();

  if (!question) {
    answerContainer.textContent = "Please enter a question.";
    return;
  }

  const datasetId = datasetSelect.value || null;

  answerContainer.textContent = "Thinking...";
  selectedSeriesContainer.innerHTML = "";
  referencesContainer.innerHTML = "";
  debugContainer.innerHTML = "";
  setLoading(true);

  try {
    const response = await fetch("/v1/chat/ask", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        question,
        dataset_id: datasetId,
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(errorText || `Request failed with status ${response.status}`);
    }

    const data = await response.json();

    answerContainer.textContent = data.answer || "No answer was returned.";
    renderSelectedSeries(data.selected_series || []);
    renderReferences(data.selected_references || []);
    renderDebug(data.debug || null);
  } catch (error) {
    answerContainer.textContent = `Error: ${error.message}`;
  } finally {
    setLoading(false);
  }
}

if (chatForm) {
  chatForm.addEventListener("submit", (event) => {
    event.preventDefault();
    askChat();
  });
}
