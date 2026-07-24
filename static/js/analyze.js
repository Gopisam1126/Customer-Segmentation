/* analyze.js
   Analyze page: two independent sections.
     1) Dataset upload  -> POST /api/upload  (re-fits the whole pipeline)
     2) Customer search -> GET  /api/search  (+ /api/search/suggest for autocomplete)
   Neither recomputes clustering client-side; both read the fitted
   pipeline via the API. */

// ══ Section 1: dataset upload ══════════════════════════════════════════════

let pendingFile = null;

function initUpload() {
  const dropzone = document.getElementById("dropzone");
  const fileInput = document.getElementById("fileInput");
  const uploadBtn = document.getElementById("uploadBtn");
  const form = document.getElementById("uploadForm");

  fileInput.addEventListener("change", () => {
    if (fileInput.files.length) setPendingFile(fileInput.files[0]);
  });

  // Drag & drop
  ["dragenter", "dragover"].forEach(evt =>
    dropzone.addEventListener(evt, e => {
      e.preventDefault();
      dropzone.classList.add("is-dragover");
    })
  );
  ["dragleave", "drop"].forEach(evt =>
    dropzone.addEventListener(evt, e => {
      e.preventDefault();
      dropzone.classList.remove("is-dragover");
    })
  );
  dropzone.addEventListener("drop", e => {
    if (e.dataTransfer.files.length) setPendingFile(e.dataTransfer.files[0]);
  });

  form.addEventListener("submit", async e => {
    e.preventDefault();
    if (!pendingFile) return;
    await uploadDataset(pendingFile);
  });

  document.getElementById("datasetResetBtn").addEventListener("click", resetDataset);

  refreshDatasetStatus();
}

function setPendingFile(file) {
  pendingFile = file;
  document.getElementById("uploadFilename").textContent = file.name;
  document.getElementById("dropzoneTitle").textContent = file.name;
  document.getElementById("uploadBtn").disabled = false;
  hide("uploadError");
  hide("uploadSuccess");
}

async function uploadDataset(file) {
  const btn = document.getElementById("uploadBtn");
  btn.disabled = true;
  btn.textContent = "Analyzing…";
  hide("uploadError");
  hide("uploadSuccess");

  const fd = new FormData();
  fd.append("file", file);

  let data;
  try {
    const res = await fetch("/api/upload", { method: "POST", body: fd });
    data = await res.json().catch(() => ({}));
    if (res.status === 401) { window.location.href = "/login"; return; }
    if (!res.ok) throw new Error(data.error || "Upload failed.");
  } catch (err) {
    showError("uploadError", err.message);
    btn.textContent = "Analyze my customers";
    btn.disabled = false;
    return;
  }

  // Success — show summary + refresh the topbar pills to the new counts.
  const success = document.getElementById("uploadSuccess");
  success.textContent = data.message;
  success.hidden = false;

  document.getElementById("sumRows").textContent = data.nRows;
  document.getElementById("sumK").textContent = data.optimalK;
  document.getElementById("sumSuggestedK").textContent = data.suggestedK;
  document.getElementById("sumIncome").textContent =
    `${data.incomeRange[0].toFixed(1)} – ${data.incomeRange[1].toFixed(1)}`;
  document.getElementById("sumScore").textContent =
    `${data.scoreRange[0].toFixed(1)} – ${data.scoreRange[1].toFixed(1)}`;
  document.getElementById("uploadSummary").hidden = false;

  btn.textContent = "Analyze my customers";
  btn.disabled = false;
  pendingFile = null;

  hydrateTopbarPills();
  refreshDatasetStatus();
  updateSearchAvailability(false);
}

async function resetDataset() {
  const btn = document.getElementById("datasetResetBtn");
  btn.disabled = true;
  btn.textContent = "Reverting…";
  try {
    const res = await fetch("/api/reset-dataset", { method: "POST" });
    if (res.status === 401) { window.location.href = "/login"; return; }
    if (!res.ok) throw new Error("Reset failed.");
  } catch (err) {
    showError("uploadError", err.message);
    btn.disabled = false;
    btn.textContent = "Go back to sample data";
    return;
  }
  document.getElementById("uploadSummary").hidden = true;
  hide("uploadSuccess");
  btn.textContent = "Go back to sample data";
  btn.disabled = false;
  hydrateTopbarPills();
  refreshDatasetStatus();
  updateSearchAvailability(true);
}

async function refreshDatasetStatus() {
  let data;
  try {
    data = await fetchJSON("/api/dataset");
  } catch {
    return;
  }
  document.getElementById("datasetStatusText").textContent =
    `Current data: ${data.label} · ${data.nRows} customers · ${data.optimalK} groups`;
  const dot = document.getElementById("datasetStatusDot");
  dot.classList.toggle("is-custom", !data.isDefault);
  document.getElementById("datasetResetBtn").hidden = data.isDefault;
  updateSearchAvailability(data.isDefault);
}

// ══ Section 2: customer search (with suggestions) ══════════════════════════

let suggestTimer = null;
let activeSuggestion = -1;
let currentSuggestions = [];

function initSearch() {
  const form = document.getElementById("searchForm");
  const input = document.getElementById("searchInput");
  const list = document.getElementById("searchSuggestions");

  form.addEventListener("submit", async e => {
    e.preventDefault();
    hideSuggestions();
    await runSearch(input.value);
  });

  input.addEventListener("input", () => {
    clearTimeout(suggestTimer);
    const q = input.value.trim();
    if (!q) { hideSuggestions(); return; }
    suggestTimer = setTimeout(() => fetchSuggestions(q), 130);
  });

  input.addEventListener("keydown", e => {
    if (list.hidden) return;
    if (e.key === "ArrowDown") { e.preventDefault(); moveActive(1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); moveActive(-1); }
    else if (e.key === "Enter" && activeSuggestion >= 0) {
      e.preventDefault();
      chooseSuggestion(currentSuggestions[activeSuggestion]);
    } else if (e.key === "Escape") {
      hideSuggestions();
    }
  });

  // Dismiss suggestions when clicking outside.
  document.addEventListener("click", e => {
    if (!e.target.closest(".search-input-wrap")) hideSuggestions();
  });
}

async function fetchSuggestions(q) {
  let data;
  try {
    data = await fetchJSON(`/api/search/suggest?q=${encodeURIComponent(q)}`);
  } catch {
    return;
  }
  currentSuggestions = data.suggestions || [];
  renderSuggestions();
}

function renderSuggestions() {
  const list = document.getElementById("searchSuggestions");
  const input = document.getElementById("searchInput");
  activeSuggestion = -1;

  if (!currentSuggestions.length) { hideSuggestions(); return; }

  list.innerHTML = currentSuggestions.map((s, i) => `
    <li class="search-suggestion" role="option" data-idx="${i}">
      <span class="suggestion-name">${escapeHtml(s.name)}</span>
      <span class="suggestion-id">#${escapeHtml(s.customerId)}</span>
    </li>
  `).join("");

  list.hidden = false;
  input.setAttribute("aria-expanded", "true");

  list.querySelectorAll(".search-suggestion").forEach(li => {
    li.addEventListener("mousedown", e => {
      e.preventDefault(); // keep focus in the input
      chooseSuggestion(currentSuggestions[Number(li.dataset.idx)]);
    });
  });
}

function moveActive(delta) {
  const items = document.querySelectorAll(".search-suggestion");
  if (!items.length) return;
  activeSuggestion = (activeSuggestion + delta + items.length) % items.length;
  items.forEach((li, i) => li.classList.toggle("is-active", i === activeSuggestion));
}

function chooseSuggestion(s) {
  const input = document.getElementById("searchInput");
  input.value = s.name;
  hideSuggestions();
  runSearch(s.name);
}

function hideSuggestions() {
  const list = document.getElementById("searchSuggestions");
  list.hidden = true;
  list.innerHTML = "";
  activeSuggestion = -1;
  document.getElementById("searchInput").setAttribute("aria-expanded", "false");
}

async function runSearch(query) {
  const resultsEl = document.getElementById("searchResults");
  resultsEl.innerHTML = `<p class="search-empty">Searching…</p>`;

  if (!query.trim()) {
    resultsEl.innerHTML = `
      <div class="result-placeholder" id="searchPlaceholder">
        <span class="result-placeholder-mark">⌕</span>
        <p>Search results will appear here.</p>
      </div>`;
    return;
  }

  let data;
  try {
    data = await fetchJSON(`/api/search?q=${encodeURIComponent(query.trim())}`);
  } catch (err) {
    resultsEl.innerHTML = `<p class="search-empty">Search failed: ${escapeHtml(err.message)}</p>`;
    return;
  }

  if (!data.results.length) {
    const extra = data.dataset_is_default
      ? ""
      : " Note: you're viewing your own uploaded data, and this name list belongs to the sample customers — switch back to sample data to look these names up.";
    resultsEl.innerHTML = `<p class="search-empty">We couldn't find anyone matching “${escapeHtml(query)}”.${extra}</p>`;
    return;
  }

  resultsEl.innerHTML = data.results.map(renderResultCard).join("");
}

function renderResultCard(r) {
  const genderAge = [r.gender, r.age ? `${r.age} yrs` : null].filter(Boolean).join(" · ");
  return `
    <div class="search-result-card" style="--seg-color:${r.color}">
      <div>
        <span class="search-result-id">Customer #${escapeHtml(r.customerId)}</span>
        <span class="search-result-name">${escapeHtml(r.name)}</span>
        <div class="search-result-meta">${escapeHtml(genderAge)} · $${r.income.toFixed(0)}k income · ${r.spending} spending</div>
      </div>
      <div class="search-result-segment">
        <span class="search-result-segment-name">${escapeHtml(r.segment)}</span>
        <span class="search-result-segment-meta">their group</span>
      </div>
    </div>
  `;
}

// When the user's own data is loaded, the sample name list won't line up
// with its customer numbers — surface a gentle note rather than confusing them.
function updateSearchAvailability(isDefault) {
  const hint = document.getElementById("searchHint");
  if (!hint) return;
  if (isDefault) {
    hint.textContent =
      "Try a name like Aarav Mehta, Priya Nair, or Sara Thompson — or a customer number such as 12.";
  } else {
    hint.textContent =
      "You're viewing your own uploaded data. This name list belongs to the sample customers, so name searches may not match — switch back to sample data above to use it.";
  }
}

// ══ small shared helpers (local to this page) ══════════════════════════════

function hide(id) { const el = document.getElementById(id); if (el) el.hidden = true; }
function showError(id, msg) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = msg;
  el.hidden = false;
}

initUpload();
initSearch();
