# Customer Segmentation — Web Dashboard

An interactive local dashboard for the existing K-Means customer
segmentation pipeline. **None of the original pipeline logic was
changed** — `preprocessor.py`, `clustering.py`, `evaluator.py`, and
`config.py` are byte-for-byte identical to the versions you provided.

On top of the original single-page dashboard, this version adds:

1. **Login** — a hardcoded demo account gates the whole app.
2. **A dedicated page per API endpoint**, tied together with a navbar.
3. **An "Analyze" page** that combines:
   - **Dataset upload** — drop in a CSV or Excel file and the whole
     dashboard (counts, classifications, optimal k, curves, segment
     profiles) re-fits to your data.
   - **Customer search** — look up a customer by name or ID, now with
     live autocomplete suggestions.
4. **Auto-open** — `python app.py` opens your browser automatically.

## File structure

```
webapp/
├── app.py                    ← MODIFIED: auth, page routes, upload/reset/search/suggest APIs, auto-open
├── auth.py                   ← hardcoded demo login (SHA-256 hashed password)
├── customer_directory.py     ← hardcoded name↔CustomerID demo directory (+ suggestions)
├── dataset_manager.py        ← NEW: validates + stages uploaded CSV/Excel, derives safe config bounds
├── preprocessor.py           ← unchanged
├── clustering.py             ← unchanged
├── evaluator.py              ← unchanged
├── config.py                 ← unchanged
├── data/
│   └── Mall_Customers.csv     ← default dataset
├── templates/
│   ├── _navbar.html          ← shared navbar (Search renamed to Analyze)
│   ├── login.html
│   ├── index.html            ← Dashboard (overview + scatter)
│   ├── segments.html
│   ├── metrics.html
│   ├── predict.html
│   └── analyze.html          ← NEW (renamed from search.html): upload + search sections
├── static/
│   ├── css/style.css         ← extended: upload/suggestions/dataset-status styles, same tokens
│   └── js/
│       ├── common.js         ← shared fetch helper + topbar pill hydration
│       ├── dashboard.js
│       ├── segments.js
│       ├── metrics.js
│       ├── predict.js
│       └── analyze.js        ← NEW (renamed from search.js): upload + search-with-suggestions
└── requirements.txt          ← adds openpyxl (Excel read support)
```

## Logging in

One hardcoded demo account:

| Username | Password  |
|----------|-----------|
| `admin`  | `mall2026` |

The password is hashed with SHA-256 and compared as a hash — never
stored or compared in plaintext. This is still **not** production-grade
auth (single shared account, no user store); swap in a real identity
provider before using it beyond a demo. Every page and `/api/*` route
is behind `@login_required` (pages redirect to `/login`, APIs return
`401`).

## Pages

| Page | Backed by | What it shows |
|---|---|---|
| `/` (Dashboard) | `GET /api/overview`, `GET /api/customers` | Headline stats + income/spending scatter map with centroids |
| `/segments` | `GET /api/segments` | Segment cards + detail table |
| `/metrics` | `GET /api/metrics` | WCSS, silhouette, Davies–Bouldin curves + table |
| `/predict` | `POST /api/predict` | Classify a new customer via the real fitted model |
| `/analyze` | upload + search APIs (below) | Upload a dataset, or look up a customer |

`/search` still works — it redirects to `/analyze` for backwards
compatibility. The navbar highlights the active page and (below ~860px)
collapses into a hamburger menu.

## Analyze page — dataset upload

Drop a **CSV or Excel** file (`.csv`, `.xlsx`, `.xls`) containing the
`Annual Income (k$)` and `Spending Score (1-100)` columns (the raw
Mall_Customers headers, or the renamed `AnnualIncome_k` /
`SpendingScore`). `POST /api/upload` then:

1. Validates + stages the file (`dataset_manager.py`). Excel files are
   converted to a plain CSV first, so `DataPreprocessor` only ever sees
   a CSV path — **no file-type branching was added to preprocessor.py**.
2. Derives safe values for the dataset-shape constants the pipeline
   hardcodes in `config.py` — the income/score domain bounds
   (`preprocessor.py` filters rows to these) and the k-sweep upper bound
   (`clustering.py` needs at least *k* rows to fit *k* clusters) — from
   the uploaded data itself, then pushes them into the already-imported
   pipeline modules. This is exactly what you'd do by hand editing
   `config.py` and restarting, but without a restart, and **without
   changing any logic** in those modules.
3. Re-runs the same `build_pipeline()` sequence against the staged file.

Every other endpoint reflects the new dataset immediately, since they
all read the shared in-memory cache that `build_pipeline()` repopulates.
A **"Revert to default"** button (`POST /api/reset-dataset`) restores
the original Mall_Customers.csv and default bounds.

Invalid uploads (wrong file type, missing columns, too few rows) return
a clear error and **leave the current dataset untouched** — validation
happens before any re-fit.

> Note: the demo **name** directory maps to the default dataset's
> CustomerIDs, so after uploading a custom dataset, name lookups in the
> search section may not resolve (ID lookups against the new data still
> work). The page shows a hint explaining this; revert to the default
> dataset to use the demo directory again.

## Analyze page — customer search

Search by name or Customer ID. As you type, `GET /api/search/suggest`
returns up to 8 autocomplete suggestions (arrow-key + click
selectable). On submit, `GET /api/search` matches the demo directory
and pairs each match with its **real** segment from the fitted
pipeline — the classification is never invented, it's the same
`ClusterID` / `SegmentLabel` `main.py` would produce.

Try: `Priya`, `Sara Thompson`, `0012`, or just `12`.

## Running it

```bash
cd webapp
pip install -r requirements.txt
python app.py
```

`python app.py` fits the pipeline, starts the server on
**http://localhost:5000**, and **opens your browser there
automatically**. You'll land on `/login` first — sign in with
`admin` / `mall2026`.

## Notes

- The pipeline is deterministic (`RANDOM_SEED = 42`), so the default
  dataset's results match `python main.py` exactly.
- Uploaded files are staged as CSVs under a `uploads/` folder (created
  automatically) and are safe to delete between runs.
- Segment names come from `clustering.py`'s dynamic centroid-quadrant
  labeling, not the static `SEGMENT_LABELS` dict in `config.py`.
- Sessions use Flask's signed-cookie session with a secret key
  generated fresh each process start (or read from `FLASK_SECRET_KEY`),
  so logging in again after a restart is expected.
