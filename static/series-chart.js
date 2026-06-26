const chartPanel = document.getElementById("series-chart-panel");
const chartSvg = document.getElementById("series-chart-svg");
const chartReadout = document.getElementById("chart-readout");
const hoverLine = document.getElementById("chart-hover-line");
const hoverPoint = document.getElementById("chart-hover-point");
const fullscreenButton = document.getElementById("chart-fullscreen-button");
const downloadSvgButton = document.getElementById("chart-download-svg-button");

function chartPoints() {
  if (!chartSvg) {
    return [];
  }

  return Array.from(chartSvg.querySelectorAll(".chart-hit-target"))
    .map((target) => ({
      period: target.dataset.period,
      value: target.dataset.value,
      x: Number(target.dataset.x),
      y: Number(target.dataset.y),
      element: target,
    }))
    .filter((point) => Number.isFinite(point.x) && Number.isFinite(point.y));
}

function svgCoordinatesFromPointer(event) {
  if (!chartSvg) {
    return null;
  }

  const point = chartSvg.createSVGPoint();
  point.x = event.clientX;
  point.y = event.clientY;

  const matrix = chartSvg.getScreenCTM();

  if (!matrix) {
    return null;
  }

  return point.matrixTransform(matrix.inverse());
}

function nearestPointByX(x) {
  const points = chartPoints();

  if (points.length === 0) {
    return null;
  }

  return points.reduce((nearest, point) => {
    const nearestDistance = Math.abs(nearest.x - x);
    const pointDistance = Math.abs(point.x - x);

    return pointDistance < nearestDistance ? point : nearest;
  });
}

function showPoint(point) {
  if (!point || !hoverLine || !hoverPoint || !chartReadout) {
    return;
  }

  hoverLine.setAttribute("x1", point.x);
  hoverLine.setAttribute("x2", point.x);
  hoverLine.hidden = false;

  hoverPoint.setAttribute("cx", point.x);
  hoverPoint.setAttribute("cy", point.y);
  hoverPoint.hidden = false;

  chartReadout.innerHTML = `<strong>${escapeHtml(point.period)}</strong> · ${escapeHtml(point.value)}`;
}

function clearHoveredPoint() {
  if (hoverLine) {
    hoverLine.hidden = true;
  }

  if (hoverPoint) {
    hoverPoint.hidden = true;
  }
}

function handlePointerMove(event) {
  const coordinates = svgCoordinatesFromPointer(event);

  if (!coordinates || !chartSvg) {
    return;
  }

  const plotLeft = Number(chartSvg.dataset.plotLeft);
  const plotRight = Number(chartSvg.dataset.plotRight);
  const plotTop = Number(chartSvg.dataset.plotTop);
  const plotBottom = Number(chartSvg.dataset.plotBottom);

  if (
    Number.isFinite(plotLeft) &&
    Number.isFinite(plotRight) &&
    Number.isFinite(plotTop) &&
    Number.isFinite(plotBottom)
  ) {
    const outsidePlot =
      coordinates.x < plotLeft ||
      coordinates.x > plotRight ||
      coordinates.y < plotTop ||
      coordinates.y > plotBottom;

    if (outsidePlot) {
      clearHoveredPoint();
      return;
    }
  }

  showPoint(nearestPointByX(coordinates.x));
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
  clonedSvg.removeAttribute("aria-label");

  clonedSvg
    .querySelectorAll(".chart-hit-target, #chart-hover-line, #chart-hover-point")
    .forEach((element) => element.remove());

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
      opacity: 0.7;
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

  window.setTimeout(() => URL.revokeObjectURL(url), 500);
}

async function toggleFullscreen() {
  if (!chartPanel) {
    return;
  }

  try {
    if (!document.fullscreenElement) {
      await chartPanel.requestFullscreen();
      return;
    }

    await document.exitFullscreen();
  } catch (error) {
    console.error("Fullscreen failed", error);
  }
}

if (chartSvg) {
  chartSvg.addEventListener("pointermove", handlePointerMove);
  chartSvg.addEventListener("pointerleave", clearHoveredPoint);
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
