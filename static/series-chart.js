const chartPanel = document.getElementById("series-chart-panel");
const chartSvg = document.getElementById("series-chart-svg");
const chartReadout = document.getElementById("chart-readout");
const hoverLine = document.getElementById("chart-hover-line");
const hoverPoint = document.getElementById("chart-hover-point");
const fullscreenButton = document.getElementById("chart-fullscreen-button");
const downloadSvgButton = document.getElementById("chart-download-svg-button");

function showHoveredPoint(target) {
  if (!target || !hoverLine || !hoverPoint || !chartReadout) {
    return;
  }

  const period = target.dataset.period;
  const value = target.dataset.value;
  const x = target.dataset.x;
  const y = target.dataset.y;

  hoverLine.setAttribute("x1", x);
  hoverLine.setAttribute("x2", x);
  hoverLine.hidden = false;

  hoverPoint.setAttribute("cx", x);
  hoverPoint.setAttribute("cy", y);
  hoverPoint.hidden = false;

  chartReadout.innerHTML = `<strong>${period}</strong> · ${value}`;
}

function clearHoveredPoint() {
  if (hoverLine) {
    hoverLine.hidden = true;
  }

  if (hoverPoint) {
    hoverPoint.hidden = true;
  }
}

function safeFilename(value) {
  return String(value || "chart")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80);
}

function downloadSvg() {
  if (!chartSvg) {
    return;
  }

  const clonedSvg = chartSvg.cloneNode(true);

  clonedSvg.removeAttribute("id");

  const style = document.createElementNS("http://www.w3.org/2000/svg", "style");

  style.textContent = `
    .chart-axis {
      stroke: #8c959f;
      stroke-width: 1;
      vector-effect: non-scaling-stroke;
    }

    .chart-grid {
      stroke: #d0d7de;
      stroke-width: 1;
      opacity: 0.6;
      vector-effect: non-scaling-stroke;
    }

    .chart-line {
      fill: none;
      stroke: #1f2328;
      stroke-width: 2.5;
      vector-effect: non-scaling-stroke;
    }

    .chart-x-label,
    .chart-y-label,
    .chart-axis-title {
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      fill: #1f2328;
    }

    .chart-x-label,
    .chart-y-label {
      font-size: 13px;
    }

    .chart-axis-title {
      font-size: 14px;
      font-weight: 700;
    }

    .chart-hover-line,
    .chart-hover-point,
    .chart-hit-target {
      display: none;
    }
  `;

  clonedSvg.insertBefore(style, clonedSvg.firstChild);

  clonedSvg.setAttribute("xmlns", "http://www.w3.org/2000/svg");

  const serializer = new XMLSerializer();
  const svgText = serializer.serializeToString(clonedSvg);
  const blob = new Blob([svgText], {
    type: "image/svg+xml;charset=utf-8",
  });

  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  const title = chartSvg.dataset.chartTitle || "chart";

  link.href = url;
  link.download = `${safeFilename(title)}.svg`;
  document.body.appendChild(link);
  link.click();
  link.remove();

  URL.revokeObjectURL(url);
}

async function toggleFullscreen() {
  if (!chartPanel) {
    return;
  }

  if (!document.fullscreenElement) {
    await chartPanel.requestFullscreen();
    return;
  }

  await document.exitFullscreen();
}

if (chartSvg) {
  const hitTargets = chartSvg.querySelectorAll(".chart-hit-target");

  hitTargets.forEach((target) => {
    target.addEventListener("mouseenter", () => showHoveredPoint(target));
    target.addEventListener("focus", () => showHoveredPoint(target));
  });

  chartSvg.addEventListener("mouseleave", clearHoveredPoint);
}

if (fullscreenButton) {
  fullscreenButton.addEventListener("click", toggleFullscreen);
}

if (downloadSvgButton) {
  downloadSvgButton.addEventListener("click", downloadSvg);
}

document.addEventListener("fullscreenchange", () => {
  if (!fullscreenButton) {
    return;
  }

  fullscreenButton.textContent = document.fullscreenElement
    ? "Exit fullscreen"
    : "Fullscreen";
});
