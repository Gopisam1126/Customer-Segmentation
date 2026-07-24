/* predict.js
   Classify page: form -> POST /api/predict -> result card + map point.
   Uses the actual fitted StandardScaler + KMeans model server-side via
   scaler.transform() -> model.predict(); nothing is recomputed here. */

const state = {
  customers: [],
  centroids: [],
  config: null,
};

const SCATTER = { w: 860, h: 400, padL: 64, padR: 24, padT: 20, padB: 50 };
let scales = null;

async function boot() {
  const [customersData, config] = await Promise.all([
    fetchJSON("/api/customers"),
    fetchJSON("/api/config"),
  ]);

  state.customers = customersData.customers;
  state.centroids = customersData.centroids;
  state.config = config;

  renderBaseMap();
  wirePredictor();
}

// ── Background map (customers + centroids, same math as dashboard) ─────

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

function renderBaseMap() {
  const svg = document.getElementById("scatterSvg");
  scales = scatterScales();
  const { x, y, xMin, xMax, yMin, yMax } = scales;

  const parts = [];
  parts.push(`<line x1="${SCATTER.padL}" y1="${SCATTER.h - SCATTER.padB}" x2="${SCATTER.w - SCATTER.padR}" y2="${SCATTER.h - SCATTER.padB}" stroke="#D6D0C2" stroke-width="1.5"/>`);
  parts.push(`<line x1="${SCATTER.padL}" y1="${SCATTER.padT}" x2="${SCATTER.padL}" y2="${SCATTER.h - SCATTER.padB}" stroke="#D6D0C2" stroke-width="1.5"/>`);

  const xTicks = niceTicks(xMin, xMax, 6);
  const yTicks = niceTicks(yMin, yMax, 5);
  for (const t of xTicks) {
    parts.push(`<line x1="${x(t)}" y1="${SCATTER.h - SCATTER.padB}" x2="${x(t)}" y2="${SCATTER.h - SCATTER.padB + 5}" stroke="#9096A1" stroke-width="1"/>`);
    parts.push(`<text x="${x(t)}" y="${SCATTER.h - SCATTER.padB + 20}" font-family="Space Grotesk" font-size="11" fill="#5C6472" text-anchor="middle">${t}</text>`);
  }
  for (const t of yTicks) {
    parts.push(`<line x1="${SCATTER.padL - 5}" y1="${y(t)}" x2="${SCATTER.padL}" y2="${y(t)}" stroke="#9096A1" stroke-width="1"/>`);
    parts.push(`<text x="${SCATTER.padL - 10}" y="${y(t) + 4}" font-family="Space Grotesk" font-size="11" fill="#5C6472" text-anchor="end">${t}</text>`);
  }

  parts.push(`<text x="${(SCATTER.padL + SCATTER.w - SCATTER.padR) / 2}" y="${SCATTER.h - 10}" font-family="Inter" font-size="12" fill="#1B2430" text-anchor="middle">Annual Income (k$)</text>`);

  for (const c of state.customers) {
    parts.push(`<circle cx="${x(c.income)}" cy="${y(c.spending)}" r="4" fill="${c.color}" fill-opacity="0.55" stroke="${c.color}" stroke-width="1"/>`);
  }
  for (const c of state.centroids) {
    const cx = x(c.income), cy = y(c.spending);
    const s = 8;
    parts.push(`<path d="M ${cx} ${cy - s} L ${cx + s} ${cy} L ${cx} ${cy + s} L ${cx - s} ${cy} Z" fill="#1B2430" stroke="#FAF7F2" stroke-width="1.5"/>`);
  }

  svg.innerHTML = parts.join("");
}

// ── Predictor form ───────────────────────────────────────────────────────

function wirePredictor() {
  const { incomeRange, scoreRange } = state.config;

  document.getElementById("incomeRangeHint").textContent = `(${incomeRange[0]}–${incomeRange[1]} k$)`;
  document.getElementById("scoreRangeHint").textContent = `(${scoreRange[0]}–${scoreRange[1]})`;

  const incomeSlider = document.getElementById("incomeSlider");
  const incomeInput = document.getElementById("incomeInput");
  const scoreSlider = document.getElementById("scoreSlider");
  const scoreInput = document.getElementById("scoreInput");

  [incomeSlider, incomeInput].forEach(el => { el.min = incomeRange[0]; el.max = incomeRange[1]; });
  [scoreSlider, scoreInput].forEach(el => { el.min = scoreRange[0]; el.max = scoreRange[1]; });

  syncPair(incomeSlider, incomeInput);
  syncPair(scoreSlider, scoreInput);

  document.getElementById("predictorForm").addEventListener("submit", async e => {
    e.preventDefault();
    const errorEl = document.getElementById("predictError");
    errorEl.hidden = true;

    let result;
    try {
      result = await fetchJSON("/api/predict", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          income: parseFloat(incomeInput.value),
          spending: parseFloat(scoreInput.value),
        }),
      });
    } catch (err) {
      errorEl.textContent = err.message;
      errorEl.hidden = false;
      return;
    }

    showPredictionResult(result);
    plotPredictionPoint(parseFloat(incomeInput.value), parseFloat(scoreInput.value), result.color);
  });
}

function syncPair(slider, input) {
  slider.addEventListener("input", () => { input.value = slider.value; });
  input.addEventListener("input", () => {
    const clamped = Math.min(Math.max(input.value, slider.min), slider.max);
    slider.value = clamped;
  });
}

function showPredictionResult(result) {
  document.getElementById("resultPlaceholder").hidden = true;
  const card = document.getElementById("resultCard");
  card.hidden = false;
  card.style.setProperty("--seg-color", result.color);

  document.getElementById("resultSegment").textContent = result.segment;

  // Turn the raw distance-to-centre into a plain-language "fit" rating.
  // Smaller distance = closer to the group's typical shopper.
  const d = result.distanceToCentroid;
  let fit;
  if (d < 0.5) fit = "Very typical";
  else if (d < 1.0) fit = "Typical";
  else if (d < 1.75) fit = "Somewhat typical";
  else fit = "On the edge of this group";
  document.getElementById("resultDistance").textContent = fit;

  document.getElementById("resultCentroid").textContent =
    `$${result.centroid.income.toFixed(0)}k income · ${result.centroid.spending.toFixed(0)} spending`;
}

function plotPredictionPoint(income, spending, color) {
  const svg = document.getElementById("scatterSvg");
  const existing = svg.querySelector("#predictedPoint");
  if (existing) existing.remove();

  const { x, y } = scales;
  const cx = x(income), cy = y(spending);

  const ns = "http://www.w3.org/2000/svg";
  const group = document.createElementNS(ns, "g");
  group.setAttribute("id", "predictedPoint");

  const ring = document.createElementNS(ns, "circle");
  ring.setAttribute("cx", cx);
  ring.setAttribute("cy", cy);
  ring.setAttribute("r", "11");
  ring.setAttribute("fill", "none");
  ring.setAttribute("stroke", "#D4572A");
  ring.setAttribute("stroke-width", "2");

  const dot = document.createElementNS(ns, "circle");
  dot.setAttribute("cx", cx);
  dot.setAttribute("cy", cy);
  dot.setAttribute("r", "5.5");
  dot.setAttribute("fill", color);
  dot.setAttribute("stroke", "#1B2430");
  dot.setAttribute("stroke-width", "1.5");

  group.appendChild(ring);
  group.appendChild(dot);
  svg.appendChild(group);

  group.animate(
    [{ opacity: 0, transform: "scale(0.5)" }, { opacity: 1, transform: "scale(1)" }],
    { duration: 220, easing: "ease-out" }
  );
}

boot().catch(err => {
  console.error(err);
  const wrap = document.querySelector(".wrap");
  if (wrap) {
    wrap.innerHTML = `<p style="padding:40px;color:#D4572A;font-family:'Space Grotesk',sans-serif;">
      Failed to load pipeline data: ${err.message}.
    </p>`;
  }
});
