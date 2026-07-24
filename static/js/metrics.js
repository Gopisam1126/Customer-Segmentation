/* metrics.js
   Choosing-k page: WCSS / silhouette / Davies-Bouldin curves + table.
   Data comes straight from GET /api/metrics. */

async function boot() {
  const metrics = await fetchJSON("/api/metrics");
  renderCurve("wcssSvg", metrics.k, metrics.wcss, "#457B9D", metrics.optimalK, false);
  renderCurve("silSvg", metrics.k, metrics.silhouette, "#2A9D8F", metrics.optimalK, false);
  renderCurve("dbiSvg", metrics.k, metrics.daviesBouldin, "#E9C46A", metrics.optimalK, true);
  renderMetricsTable(metrics);
}

function renderCurve(svgId, ks, values, color, optimalK) {
  const svg = document.getElementById(svgId);
  const W = 380, H = 220, padL = 40, padR = 16, padT = 14, padB = 30;
  const plotW = W - padL - padR, plotH = H - padT - padB;

  const validPairs = ks.map((k, i) => [k, values[i]]).filter(([, v]) => v !== null);
  const vals = validPairs.map(([, v]) => v);
  const vMin = Math.min(...vals), vMax = Math.max(...vals);
  const pad = (vMax - vMin) * 0.15 || 1;
  const yLo = vMin - pad, yHi = vMax + pad;

  const kMin = Math.min(...ks), kMax = Math.max(...ks);
  const x = k => padL + ((k - kMin) / (kMax - kMin)) * plotW;
  const y = v => padT + plotH - ((v - yLo) / (yHi - yLo)) * plotH;

  const parts = [];
  parts.push(`<line x1="${padL}" y1="${H - padB}" x2="${W - padR}" y2="${H - padB}" stroke="#D6D0C2" stroke-width="1"/>`);
  parts.push(`<line x1="${padL}" y1="${padT}" x2="${padL}" y2="${H - padB}" stroke="#D6D0C2" stroke-width="1"/>`);

  for (const k of ks) {
    parts.push(`<text x="${x(k)}" y="${H - padB + 16}" font-family="Space Grotesk" font-size="9.5" fill="#9096A1" text-anchor="middle">${k}</text>`);
  }

  parts.push(`<line x1="${x(optimalK)}" y1="${padT}" x2="${x(optimalK)}" y2="${H - padB}" stroke="#D4572A" stroke-width="1.2" stroke-dasharray="3,3"/>`);

  const linePts = validPairs.map(([k, v]) => `${x(k)},${y(v)}`).join(" ");
  parts.push(`<polyline points="${linePts}" fill="none" stroke="${color}" stroke-width="2"/>`);
  for (const [k, v] of validPairs) {
    parts.push(`<circle cx="${x(k)}" cy="${y(v)}" r="3.2" fill="${color}"/>`);
  }

  svg.innerHTML = parts.join("");
}

function renderMetricsTable(metrics) {
  const tbody = document.getElementById("metricsTableBody");
  const rows = metrics.k.map((k, i) => {
    const wcss = metrics.wcss[i];
    const sil = metrics.silhouette[i];
    const dbi = metrics.daviesBouldin[i];
    const isOptimal = k === metrics.optimalK;
    return `
      <tr class="${isOptimal ? 'is-optimal-row' : ''}">
        <td>${k}${isOptimal ? " ★" : ""}</td>
        <td>${wcss === null ? "—" : wcss.toFixed(2)}</td>
        <td>${sil === null ? "—" : sil.toFixed(4)}</td>
        <td>${dbi === null ? "—" : dbi.toFixed(4)}</td>
      </tr>
    `;
  });
  tbody.innerHTML = rows.join("");
}

boot().catch(err => {
  console.error(err);
  const tbody = document.getElementById("metricsTableBody");
  if (tbody) tbody.innerHTML = `<tr><td colspan="4" class="table-loading">Failed to load metrics: ${err.message}</td></tr>`;
});
