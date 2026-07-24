/* common.js
   Shared helpers used by every page: dashboard.js, segments.js, metrics.js,
   predict.js, search.js. Nothing here recomputes clustering client-side —
   it only fetches from /api/* and renders. */

async function fetchJSON(url, opts) {
  const res = await fetch(url, opts);
  if (res.status === 401) {
    // Session expired or never existed — bounce back to login.
    window.location.href = "/login";
    throw new Error("Not authenticated");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || `Request to ${url} failed`);
  }
  return res.json();
}

/* Populates the "N customers" / "k = N" pills in the topbar on every page. */
async function hydrateTopbarPills() {
  try {
    const overview = await fetchJSON("/api/overview");
    const pillCustomers = document.getElementById("pillCustomers");
    const pillK = document.getElementById("pillK");
    if (pillCustomers) pillCustomers.textContent = `${overview.n_customers} customers`;
    if (pillK) pillK.textContent = `k = ${overview.optimal_k}`;
    return overview;
  } catch (err) {
    // If unauthenticated, fetchJSON already redirected; otherwise fail quietly,
    // the pills just stay at their placeholder text.
    return null;
  }
}

function niceTicks(min, max, count) {
  const range = max - min;
  const rawStep = range / count;
  const mag = Math.pow(10, Math.floor(Math.log10(rawStep)));
  const norm = rawStep / mag;
  let step;
  if (norm < 1.5) step = 1 * mag;
  else if (norm < 3) step = 2 * mag;
  else if (norm < 7) step = 5 * mag;
  else step = 10 * mag;

  const ticks = [];
  let t = Math.ceil(min / step) * step;
  while (t <= max) {
    ticks.push(Math.round(t * 100) / 100);
    t += step;
  }
  return ticks;
}

function escapeAttr(s) {
  return String(s).replace(/&/g, "&amp;").replace(/"/g, "&quot;");
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

document.addEventListener("DOMContentLoaded", hydrateTopbarPills);
