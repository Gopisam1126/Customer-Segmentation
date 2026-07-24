/* dashboard.js
   Dashboard page: overview stats + behavioral scatter map.
   All numbers come from /api/overview and /api/customers, backed by the
   actual fitted pipeline objects (preprocessor.py, clustering.py). */

const state = {
  overview: null,
  customers: [],
  centroids: [],
};

async function boot() {
  const [overview, customersData] = await Promise.all([
    fetchJSON("/api/overview"),
    fetchJSON("/api/customers"),
  ]);

  state.overview = overview;
  state.customers = customersData.customers;
  state.centroids = customersData.centroids;

  renderStats();
  renderLegend();
  renderScatter();
}

function renderStats() {
  const o = state.overview;
  document.getElementById("statCustomers").textContent = o.n_customers;
  document.getElementById("statSegments").textContent = o.n_segments;
  document.getElementById("statSilhouette").textContent = o.silhouette.toFixed(3);
  document.getElementById("statDBI").textContent = o.davies_bouldin.toFixed(3);
  document.getElementById("statK").textContent = o.optimal_k;

  const kFoot = document.getElementById("statKFoot");
  kFoot.textContent = o.suggested_k === o.optimal_k
    ? "the best split for this list"
    : `${o.suggested_k} groups may fit even better`;
}

function renderLegend() {
  const el = document.getElementById("scatterLegend");
  el.innerHTML = "";
  const seen = new Set();
  for (const c of state.centroids) {
    if (seen.has(c.segment)) continue;
    seen.add(c.segment);
    const item = document.createElement("div");
    item.className = "legend-item";
    item.innerHTML = `<span class="legend-swatch" style="background:${c.color}"></span>${c.segment}`;
    el.appendChild(item);
  }
}

// ── Scatter plot (hand-drawn SVG, real data-to-pixel scaling) ───────────

const SCATTER = { w: 860, h: 560, padL: 64, padR: 24, padT: 20, padB: 50 };

function scatterScales() {
  const incomes = state.customers.map(c => c.income).concat(state.centroids.map(c => c.income));
  const spendings = state.customers.map(c => c.spending).concat(state.centroids.map(c => c.spending));
  const xMin = Math.floor(Math.min(...incomes) / 10) * 10 - 5;
  const xMax = Math.ceil(Math.max(...incomes) / 10) * 10 + 5;
  const yMin = Math.floor(Math.min(...spendings) / 10) * 10 - 5;
  const yMax = Math.ceil(Math.max(...spendings) / 10) * 10 + 5;

  const plotW = SCATTER.w - SCATTER.padL - SCATTER.padR;
  const plotH = SCATTER.h - SCATTER.padT - SCATTER.padB;

  const x = v => SCATTER.padL + ((v - xMin) / (xMax - xMin)) * plotW;
  const y = v => SCATTER.padT + plotH - ((v - yMin) / (yMax - yMin)) * plotH;
  return { x, y, xMin, xMax, yMin, yMax };
}

function renderScatter() {
  const svg = document.getElementById("scatterSvg");
  const { x, y, xMin, xMax, yMin, yMax } = scatterScales();

  const parts = [];

  parts.push(`<line x1="${SCATTER.padL}" y1="${SCATTER.h - SCATTER.padB}" x2="${SCATTER.w - SCATTER.padR}" y2="${SCATTER.h - SCATTER.padB}" stroke="#D6D0C2" stroke-width="1.5"/>`);
  parts.push(`<line x1="${SCATTER.padL}" y1="${SCATTER.padT}" x2="${SCATTER.padL}" y2="${SCATTER.h - SCATTER.padB}" stroke="#D6D0C2" stroke-width="1.5"/>`);

  const xTicks = niceTicks(xMin, xMax, 6);
  const yTicks = niceTicks(yMin, yMax, 6);
  for (const t of xTicks) {
    parts.push(`<line x1="${x(t)}" y1="${SCATTER.h - SCATTER.padB}" x2="${x(t)}" y2="${SCATTER.h - SCATTER.padB + 5}" stroke="#9096A1" stroke-width="1"/>`);
    parts.push(`<text x="${x(t)}" y="${SCATTER.h - SCATTER.padB + 20}" font-family="Space Grotesk" font-size="11" fill="#5C6472" text-anchor="middle">${t}</text>`);
  }
  for (const t of yTicks) {
    parts.push(`<line x1="${SCATTER.padL - 5}" y1="${y(t)}" x2="${SCATTER.padL}" y2="${y(t)}" stroke="#9096A1" stroke-width="1"/>`);
    parts.push(`<text x="${SCATTER.padL - 10}" y="${y(t) + 4}" font-family="Space Grotesk" font-size="11" fill="#5C6472" text-anchor="end">${t}</text>`);
  }

  parts.push(`<text x="${(SCATTER.padL + SCATTER.w - SCATTER.padR) / 2}" y="${SCATTER.h - 10}" font-family="Inter" font-size="12" fill="#1B2430" text-anchor="middle">Annual Income (k$)</text>`);
  parts.push(`<text x="18" y="${(SCATTER.padT + SCATTER.h - SCATTER.padB) / 2}" font-family="Inter" font-size="12" fill="#1B2430" text-anchor="middle" transform="rotate(-90 18 ${(SCATTER.padT + SCATTER.h - SCATTER.padB) / 2})">Spending Score (1–100)</text>`);

  for (const c of state.customers) {
    parts.push(`<circle class="scatter-point" data-income="${c.income}" data-spending="${c.spending}" data-segment="${escapeAttr(c.segment)}" data-id="${escapeAttr(c.customerId)}" cx="${x(c.income)}" cy="${y(c.spending)}" r="5" fill="${c.color}" fill-opacity="0.72" stroke="${c.color}" stroke-width="1"/>`);
  }

  for (const c of state.centroids) {
    const cx = x(c.income), cy = y(c.spending);
    const s = 9;
    parts.push(`<path d="M ${cx} ${cy - s} L ${cx + s} ${cy} L ${cx} ${cy + s} L ${cx - s} ${cy} Z" fill="#1B2430" stroke="#FAF7F2" stroke-width="1.5"/>`);
  }

  svg.innerHTML = parts.join("");

  const tooltip = document.getElementById("scatterTooltip");
  const shell = svg.closest(".scatter-shell");
  svg.querySelectorAll(".scatter-point").forEach(pt => {
    pt.addEventListener("mousemove", e => {
      const rect = shell.getBoundingClientRect();
      tooltip.style.left = `${e.clientX - rect.left}px`;
      tooltip.style.top = `${e.clientY - rect.top}px`;
      tooltip.innerHTML = `${pt.dataset.segment}<br><span style="color:#B8BEC8">$${pt.dataset.income}k income · ${pt.dataset.spending} score</span>`;
      tooltip.classList.add("visible");
      pt.setAttribute("r", "7");
    });
    pt.addEventListener("mouseleave", () => {
      tooltip.classList.remove("visible");
      pt.setAttribute("r", "5");
    });
  });
}

boot().catch(err => {
  console.error(err);
  const wrap = document.querySelector(".wrap");
  if (wrap) {
    wrap.innerHTML = `<p style="padding:40px;color:#D4572A;font-family:'Space Grotesk',sans-serif;">
      Failed to load pipeline data: ${err.message}. Check that app.py fitted the pipeline successfully on startup.
    </p>`;
  }
});
