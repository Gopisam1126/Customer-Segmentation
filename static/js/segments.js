/* segments.js
   Segments page: per-segment cards + a detail table.
   Data comes straight from GET /api/segments. */

async function boot() {
  const segments = await fetchJSON("/api/segments");
  renderSegmentCards(segments);
  renderSegmentTable(segments);
}

function renderSegmentCards(segments) {
  const grid = document.getElementById("segmentGrid");
  grid.innerHTML = "";
  const sorted = [...segments].sort((a, b) => b.count - a.count);
  for (const s of sorted) {
    const card = document.createElement("div");
    card.className = "segment-card";
    card.style.setProperty("--seg-color", s.color);
    card.innerHTML = `
      <span class="segment-name">${escapeHtml(s.segment)}</span>
      <span class="segment-count">${s.count} customers · ${s.pct}% of all shoppers</span>
      <div class="segment-metric"><span>Typical income</span><strong>$${s.incomeMean.toFixed(0)}k / yr</strong></div>
      <div class="segment-metric"><span>Typical spending</span><strong>${s.spendingMean.toFixed(0)} / 100</strong></div>
      <div class="segment-metric"><span>Income varies by</span><strong>±$${s.incomeStd.toFixed(0)}k</strong></div>
    `;
    grid.appendChild(card);
  }
}

function renderSegmentTable(segments) {
  const tbody = document.getElementById("segmentTableBody");
  const sorted = [...segments].sort((a, b) => b.count - a.count);
  tbody.innerHTML = sorted.map(s => `
    <tr>
      <td><span class="segment-swatch" style="background:${s.color}"></span>${escapeHtml(s.segment)}</td>
      <td>${s.count}</td>
      <td>${s.pct}%</td>
      <td>$${s.incomeMean.toFixed(1)}k</td>
      <td>$${s.incomeMedian.toFixed(1)}k</td>
      <td>±${s.incomeStd.toFixed(1)}k</td>
      <td>${s.spendingMean.toFixed(1)}</td>
      <td>${s.spendingMedian.toFixed(1)}</td>
      <td>±${s.spendingStd.toFixed(1)}</td>
    </tr>
  `).join("");
}

boot().catch(err => {
  console.error(err);
  const tbody = document.getElementById("segmentTableBody");
  if (tbody) tbody.innerHTML = `<tr><td colspan="9" class="table-loading">Failed to load segments: ${err.message}</td></tr>`;
});
