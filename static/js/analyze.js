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
  refreshDatasetStatus();   // also refreshes the search hint for the new data
  clearSearch();            // old dataset's results no longer apply
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
  refreshDatasetStatus();   // also refreshes the search hint for the new data
  clearSearch();            // old dataset's results no longer apply
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
  updateSearchAvailability(data);
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
      <span class="suggestion-name">${escapeHtml(s.display || s.name || "")}</span>
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

// Search with the suggestion's `query`, not its visible label: a customer
// with no name is shown as "Customer #1003" but must be looked up by its
// bare ID, since the label itself matches nothing.
function chooseSuggestion(s) {
  if (!s) return;
  const term = s.query || s.name || s.customerId;
  const input = document.getElementById("searchInput");
  input.value = term;
  hideSuggestions();
  runSearch(term);
}

function hideSuggestions() {
  const list = document.getElementById("searchSuggestions");
  list.hidden = true;
  list.innerHTML = "";
  activeSuggestion = -1;
  document.getElementById("searchInput").setAttribute("aria-expanded", "false");
}

// Reset the search box back to its empty state — used when the active
// dataset changes, since results from the previous one are meaningless.
function clearSearch() {
  const input = document.getElementById("searchInput");
  if (input) input.value = "";
  hideSuggestions();
  const resultsEl = document.getElementById("searchResults");
  if (resultsEl) {
    resultsEl.innerHTML = `
      <div class="result-placeholder" id="searchPlaceholder">
        <span class="result-placeholder-mark">⌕</span>
        <p>Search results will appear here.</p>
      </div>`;
  }
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
    // Searching now always runs against the active dataset, so the only
    // useful extra hint is when that dataset has no names to match on.
    const extra = data.has_names
      ? ""
      : " This dataset doesn't include customer names, so try searching by customer number instead.";
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

// The search box follows whichever dataset is loaded, so the hint has to
// say what THAT dataset can actually be searched on: its own names if the
// file has a name column, otherwise its own customer numbers.
function updateSearchAvailability(info) {
  const hint = document.getElementById("searchHint");
  if (!hint) return;

  // Accept a plain boolean for backwards compatibility with older callers.
  const data = typeof info === "boolean" ? { isDefault: info } : (info || {});

  const names = (data.sampleNames || []).slice(0, 2).join(" or ");
  const ids = (data.sampleIds || []).slice(0, 2).join(" or ");

  if (data.isDefault) {
    hint.textContent =
      "Try a name like Aarav Mehta, Priya Nair, or Sara Thompson — or a customer number such as 12.";
  } else if (data.hasIds === false) {
    hint.textContent =
      "Your file doesn't include a customer number or name column, so there's nothing to look customers up by. Everything else on the dashboard still works.";
  } else if (data.nameSource === "generated") {
    // Names here are placeholders we generated, not data from the file —
    // say so, so nobody mistakes them for real customer names.
    hint.textContent = names
      ? `Your file has no name column, so display names are generated for the demo — try ${names}, or a customer number such as ${ids}.`
      : "Your file has no name column, so display names are generated for the demo — you can also search by customer number.";
  } else if (data.hasNames) {
    hint.textContent = names
      ? `Searching your uploaded customers — try a name like ${names}, or a customer number.`
      : "Searching your uploaded customers — type a name or a customer number.";
  } else {
    hint.textContent = ids
      ? `Search your uploaded customers by number — try ${ids}.`
      : "Search your uploaded customers by number.";
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
