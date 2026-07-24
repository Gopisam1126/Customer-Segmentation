"""
app.py
Flask web application that showcases the existing Customer Segmentation
pipeline (preprocessor.py, clustering.py, evaluator.py, visualizer.py)
in an interactive dashboard.

IMPORTANT: This file does not alter the logic of the original pipeline
modules in any way. It imports and orchestrates them exactly as
main.py does, then serves their outputs (and the fitted model itself)
over a small JSON API for the frontend to render.

Dataset uploads (CSV/Excel) are handled by dataset_manager.py, which
stages an uploaded file as a CSV and derives safe config values (income
/ score ranges, k-sweep bounds) from it -- app.py then re-runs the same
build_pipeline() sequence against that staged CSV. No pipeline module
was changed to support this.

Run:
    python app.py
This also opens your browser to http://localhost:5000 automatically.
"""

import os
import math
import secrets
import threading
import webbrowser
from functools import wraps

import numpy as np
import pandas as pd
from flask import Flask, jsonify, request, render_template, redirect, url_for, session
from flask.json.provider import DefaultJSONProvider

import config
from preprocessor import DataPreprocessor
from clustering import CustomerSegmenter
from evaluator import ClusterEvaluator
from auth import DEMO_USERNAME, verify_credentials
from customer_directory import search_directory, suggest_directory
from dataset_manager import (
    validate_and_stage, apply_runtime_config, DatasetError,
    DEFAULT_INCOME_RANGE, DEFAULT_SCORE_RANGE, DEFAULT_K_MAX,
    DEFAULT_K_MIN, DEFAULT_OPTIMAL_K,
)

app = Flask(__name__)


class SafeJSONProvider(DefaultJSONProvider):
    """
    Emit strict, valid JSON. Python's json module by default writes bare
    NaN / Infinity tokens, which browsers' JSON.parse rejects. Uploaded
    datasets can carry blank cells (e.g. a missing Gender) that reach the
    API as NaN, so this provider converts any non-finite float to null and
    forces ensure_ascii off strictness on (allow_nan=False path handled by
    the default() coercion below). This is a serialization safeguard only;
    it changes no pipeline logic.
    """

    @staticmethod
    def default(obj):
        # Coerce non-finite floats (NaN, inf) and numpy/pandas NA to null.
        if isinstance(obj, float) and not math.isfinite(obj):
            return None
        try:
            if pd.isna(obj):
                return None
        except (TypeError, ValueError):
            pass
        return DefaultJSONProvider.default(obj)

    def dumps(self, obj, **kwargs):
        # Recursively replace any non-finite float so the emitted text never
        # contains a bare NaN/Infinity token, regardless of nesting.
        return super().dumps(_clean_nonfinite(obj), **kwargs)


def _clean_nonfinite(value):
    """Deep-replace NaN/inf (and pandas NA) with None inside dicts/lists."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: _clean_nonfinite(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean_nonfinite(v) for v in value]
    try:
        if value is not None and not isinstance(value, (str, bool, int)) and pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


app.json = SafeJSONProvider(app)
# Demo-only: a fixed random secret each process start is fine here since this
# app has one hardcoded account and no persisted user data to protect long-term.
app.secret_key = os.environ.get("FLASK_SECRET_KEY", secrets.token_hex(32))

HOST = "127.0.0.1"
PORT = 5000


# ── Auth helpers ──────────────────────────────────────────────────────────────

def login_required(view_func):
    """Redirect to /login for page routes, or return 401 JSON for API routes."""
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not session.get("logged_in"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "Not authenticated"}), 401
            return redirect(url_for("login", next=request.path))
        return view_func(*args, **kwargs)
    return wrapped

# ── Pipeline state ───────────────────────────────────────────────────────────
# The pipeline is fitted once at startup (identical steps to main.py) and
# cached in-process. Re-fitting per request would be wasteful and would not
# change any result, since RANDOM_SEED makes the pipeline deterministic.
# Re-fitting happens exactly once more per successful dataset upload.
_state = {
    "dataset_label": "Mall_Customers.csv (default)",
    "dataset_is_default": True,
}


def build_pipeline(csv_path: str = None, optimal_k: int = None) -> None:
    """
    Runs the exact same sequence as main.py Steps 1-4, then caches every
    object the API needs. No clustering/preprocessing logic lives here —
    it all still lives in the original modules.

    csv_path / optimal_k let a freshly uploaded dataset be fitted through
    the SAME call path as the default dataset; when omitted, behaviour is
    identical to the original app.py (uses config.DATASET_CSV / OPTIMAL_K).
    """
    path = csv_path or config.DATASET_CSV
    k = optimal_k or config.OPTIMAL_K

    prep = DataPreprocessor(path=path).run()

    seg = CustomerSegmenter(k=k)
    sweep = seg.sweep(prep.scaled)

    ev = ClusterEvaluator(sweep, prep.scaled)
    metrics_df = ev.build_metrics_table()
    suggested_k = ev.suggest_optimal_k()

    seg.fit(prep.scaled, scaler=prep.scaler)
    df_annotated = seg.annotate(prep.clean_df)
    cluster_summary = seg.cluster_summary(df_annotated)

    _state["prep"] = prep
    _state["seg"] = seg
    _state["ev"] = ev
    _state["metrics_df"] = metrics_df
    _state["suggested_k"] = suggested_k
    _state["df_annotated"] = df_annotated
    _state["cluster_summary"] = cluster_summary
    _state["optimal_k"] = k


# ── Auth routes ───────────────────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("logged_in"):
        return redirect(url_for("index"))

    error = None
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if verify_credentials(username, password):
            session["logged_in"] = True
            session["username"] = username.strip()
            next_url = request.args.get("next") or url_for("index")
            return redirect(next_url)
        error = "Incorrect username or password."

    return render_template("login.html", error=error, demo_username=DEMO_USERNAME)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ── Page routes ───────────────────────────────────────────────────────────────

@app.route("/")
@login_required
def index():
    return render_template("index.html", active_page="dashboard")


@app.route("/segments")
@login_required
def segments_page():
    return render_template("segments.html", active_page="segments")


@app.route("/metrics")
@login_required
def metrics_page():
    return render_template("metrics.html", active_page="metrics")


@app.route("/predict")
@login_required
def predict_page():
    return render_template("predict.html", active_page="predict")


@app.route("/analyze")
@login_required
def analyze_page():
    return render_template("analyze.html", active_page="analyze")


@app.route("/search")
@login_required
def search_page_redirect():
    """The Search page was renamed to Analyze; keep the old URL working."""
    return redirect(url_for("analyze_page"))


# ── API routes ────────────────────────────────────────────────────────────────

@app.route("/api/overview")
@login_required
def api_overview():
    """High-level numbers for the top of the dashboard."""
    seg = _state["seg"]
    df = _state["df_annotated"]
    optimal_k = _state["optimal_k"]

    seg_labels = seg.get_segment_labels()
    n_segments = len(set(seg_labels.values()))

    return jsonify({
        "n_customers": int(len(df)),
        "n_features": 2,
        "optimal_k": optimal_k,
        "suggested_k": _state["suggested_k"],
        "n_segments": n_segments,
        "income_range": [float(df["AnnualIncome_k"].min()), float(df["AnnualIncome_k"].max())],
        "score_range": [float(df["SpendingScore"].min()), float(df["SpendingScore"].max())],
        "silhouette": float(_state["metrics_df"].loc[optimal_k, "SilhouetteScore"]),
        "davies_bouldin": float(_state["metrics_df"].loc[optimal_k, "DaviesBouldinIndex"]),
        "wcss": float(_state["metrics_df"].loc[optimal_k, "WCSS"]),
        "dataset_label": _state["dataset_label"],
        "dataset_is_default": _state["dataset_is_default"],
    })


@app.route("/api/customers")
@login_required
def api_customers():
    """Every annotated customer record, for the scatter plot + table."""
    df = _state["df_annotated"]
    seg = _state["seg"]
    seg_labels = seg.get_segment_labels()

    # Stable colour per segment name, taken from the project's own PALETTE
    ordered_names = sorted(set(seg_labels.values()))
    colour_of = {name: config.PALETTE[i % len(config.PALETTE)] for i, name in enumerate(ordered_names)}

    records = []
    for _, row in df.iterrows():
        rec = {
            "customerId": str(row.get("CustomerID", "")),
            "income": float(row["AnnualIncome_k"]),
            "spending": float(row["SpendingScore"]),
            "cluster": int(row["ClusterID"]),
            "segment": row["SegmentLabel"],
            "color": colour_of[row["SegmentLabel"]],
        }
        if "Age" in df.columns:
            rec["age"] = int(row["Age"]) if not pd.isna(row["Age"]) else None
        if "Gender" in df.columns:
            rec["gender"] = None if pd.isna(row["Gender"]) else row["Gender"]
        records.append(rec)

    centers_orig = _state["prep"].scaler.inverse_transform(seg.centers_)
    centroids = [
        {
            "cluster": cid,
            "segment": seg_labels[cid],
            "income": float(centers_orig[cid][0]),
            "spending": float(centers_orig[cid][1]),
            "color": colour_of[seg_labels[cid]],
        }
        for cid in range(seg.k)
    ]

    return jsonify({"customers": records, "centroids": centroids})


@app.route("/api/segments")
@login_required
def api_segments():
    """Per-segment descriptive stats, from clustering.py's own summary method."""
    summary = _state["cluster_summary"]
    seg = _state["seg"]
    seg_labels = seg.get_segment_labels()
    ordered_names = sorted(set(seg_labels.values()))
    colour_of = {name: config.PALETTE[i % len(config.PALETTE)] for i, name in enumerate(ordered_names)}

    df = _state["df_annotated"]
    counts = df["SegmentLabel"].value_counts()

    out = []
    for name in summary.index:
        row = summary.loc[name]
        out.append({
            "segment": name,
            "color": colour_of.get(name, "#999999"),
            "count": int(counts.get(name, 0)),
            "pct": round(100 * counts.get(name, 0) / len(df), 1),
            "incomeMean": float(row[("AnnualIncome_k", "mean")]),
            "incomeMedian": float(row[("AnnualIncome_k", "median")]),
            "incomeStd": float(row[("AnnualIncome_k", "std")]),
            "spendingMean": float(row[("SpendingScore", "mean")]),
            "spendingMedian": float(row[("SpendingScore", "median")]),
            "spendingStd": float(row[("SpendingScore", "std")]),
        })
    return jsonify(out)


@app.route("/api/metrics")
@login_required
def api_metrics():
    """WCSS / Silhouette / Davies-Bouldin across the full k-sweep."""
    metrics_df = _state["metrics_df"]
    ks = metrics_df.index.tolist()
    return jsonify({
        "k": ks,
        "wcss": [None if pd.isna(v) else float(v) for v in metrics_df["WCSS"]],
        "silhouette": [None if pd.isna(v) else float(v) for v in metrics_df["SilhouetteScore"]],
        "daviesBouldin": [None if pd.isna(v) else float(v) for v in metrics_df["DaviesBouldinIndex"]],
        "optimalK": _state["optimal_k"],
        "suggestedK": _state["suggested_k"],
    })


@app.route("/api/predict", methods=["POST"])
@login_required
def api_predict():
    """
    Classify a new (income, spending) pair using the ACTUAL fitted
    scaler + KMeans model — not a re-implementation. This exercises the
    same StandardScaler.transform() -> KMeans.predict() path the model
    uses internally.
    """
    payload = request.get_json(force=True) or {}
    try:
        income = float(payload.get("income"))
        spending = float(payload.get("spending"))
    except (TypeError, ValueError):
        return jsonify({"error": "income and spending must be numbers"}), 400

    lo_i, hi_i = config.INCOME_RANGE
    lo_s, hi_s = config.SCORE_RANGE
    if not (lo_i <= income <= hi_i):
        return jsonify({"error": f"Please enter a yearly income between {lo_i:.0f} and {hi_i:.0f} (in thousands)."}), 400
    if not (lo_s <= spending <= hi_s):
        return jsonify({"error": f"Please enter a spending level between {lo_s:.0f} and {hi_s:.0f}."}), 400

    prep = _state["prep"]
    seg = _state["seg"]
    seg_labels = seg.get_segment_labels()

    X_new = np.array([[income, spending]])
    X_scaled = prep.scaler.transform(X_new)
    cluster_id = int(seg.model.predict(X_scaled)[0])

    centers_orig = prep.scaler.inverse_transform(seg.centers_)
    centroid = centers_orig[cluster_id]
    distance = float(np.linalg.norm(X_scaled[0] - seg.centers_[cluster_id]))

    ordered_names = sorted(set(seg_labels.values()))
    colour_of = {name: config.PALETTE[i % len(config.PALETTE)] for i, name in enumerate(ordered_names)}
    segment_name = seg_labels[cluster_id]

    return jsonify({
        "cluster": cluster_id,
        "segment": segment_name,
        "color": colour_of[segment_name],
        "distanceToCentroid": round(distance, 3),
        "centroid": {"income": float(centroid[0]), "spending": float(centroid[1])},
    })


@app.route("/api/config")
@login_required
def api_config():
    """Expose bounds so the frontend form can validate without duplicating them."""
    return jsonify({
        "incomeRange": list(config.INCOME_RANGE),
        "scoreRange": list(config.SCORE_RANGE),
        "kMin": config.K_MIN,
        "kMax": config.K_MAX - 1,
    })


@app.route("/api/dataset")
@login_required
def api_dataset():
    """Which dataset is currently active (default, or a user upload)."""
    return jsonify({
        "label": _state["dataset_label"],
        "isDefault": _state["dataset_is_default"],
        "nRows": int(len(_state["df_annotated"])),
        "optimalK": _state["optimal_k"],
    })


@app.route("/api/upload", methods=["POST"])
@login_required
def api_upload():
    """
    Accept a CSV/Excel upload, validate + stage it (dataset_manager.py),
    then re-run the SAME build_pipeline() sequence against the staged
    file. Every downstream endpoint (/api/overview, /api/customers,
    /api/segments, /api/metrics, /api/search) reflects the new dataset
    immediately, since they all read from the shared _state cache that
    build_pipeline() just repopulated.
    """
    if "file" not in request.files:
        return jsonify({"error": "No file was uploaded."}), 400

    file_storage = request.files["file"]
    if not file_storage or file_storage.filename == "":
        return jsonify({"error": "No file was selected."}), 400

    try:
        staged = validate_and_stage(file_storage)
    except DatasetError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"Unexpected error reading file: {exc}"}), 400

    # Widen the same config constants a person would edit by hand if they
    # swapped in a new CSV, derived from the uploaded data itself, and push
    # them into the pipeline modules that read them. This does not change
    # any logic in preprocessor.py / clustering.py / evaluator.py.
    apply_runtime_config(
        income_range=staged["income_range"],
        score_range=staged["score_range"],
        k_max=staged["safe_k_max"],
    )

    try:
        build_pipeline(csv_path=staged["csv_path"], optimal_k=staged["safe_optimal_k"])
    except Exception as exc:
        return jsonify({"error": f"We couldn't analyze this file: {exc}"}), 400

    _state["dataset_label"] = staged["original_filename"]
    _state["dataset_is_default"] = False

    return jsonify({
        "message": f"Success — analyzed {staged['n_rows']} customers from {staged['original_filename']}.",
        "nRows": staged["n_rows"],
        "optimalK": _state["optimal_k"],
        "suggestedK": _state["suggested_k"],
        "incomeRange": list(config.INCOME_RANGE),
        "scoreRange": list(config.SCORE_RANGE),
    })


@app.route("/api/reset-dataset", methods=["POST"])
@login_required
def api_reset_dataset():
    """Revert to the original Mall_Customers.csv dataset and config bounds."""
    apply_runtime_config(
        income_range=DEFAULT_INCOME_RANGE,
        score_range=DEFAULT_SCORE_RANGE,
        k_max=DEFAULT_K_MAX,
        k_min=DEFAULT_K_MIN,
    )
    build_pipeline(optimal_k=DEFAULT_OPTIMAL_K)
    _state["dataset_label"] = "Mall_Customers.csv (default)"
    _state["dataset_is_default"] = True
    return jsonify({"message": "Switched back to the sample customer data.", "optimalK": _state["optimal_k"]})


@app.route("/api/search")
@login_required
def api_search():
    """
    Search the hardcoded demo customer directory by name or CustomerID,
    then attach each match's REAL classification by looking up its row
    in the actual annotated DataFrame produced by the fitted pipeline
    (clustering.py's CustomerSegmenter). No classification is invented
    here — it's the same ClusterID/SegmentLabel main.py would produce.

    If a non-default dataset is active, the hardcoded demo directory's
    CustomerIDs likely don't correspond to real rows anymore — matches
    that can't be found in the current DataFrame are simply omitted,
    and the frontend explains why via /api/dataset's isDefault flag.
    """
    query = request.args.get("q", "")
    matches = search_directory(query)

    df = _state["df_annotated"]
    seg = _state["seg"]
    seg_labels = seg.get_segment_labels()
    ordered_names = sorted(set(seg_labels.values()))
    colour_of = {name: config.PALETTE[i % len(config.PALETTE)] for i, name in enumerate(ordered_names)}

    results = []
    for m in matches:
        # CustomerID loads from the CSV as an int (pandas drops leading
        # zeros), while the demo directory keys are zero-padded strings
        # ("0001") to match the CSV file's own formatting — compare as int.
        try:
            row = df[df["CustomerID"] == int(m["customerId"])]
        except (ValueError, KeyError):
            continue
        if row.empty:
            continue
        row = row.iloc[0]
        results.append({
            "customerId": m["customerId"],
            "name": m["name"],
            "age": int(row["Age"]) if "Age" in df.columns and not pd.isna(row["Age"]) else None,
            "gender": row["Gender"] if "Gender" in df.columns else None,
            "income": float(row["AnnualIncome_k"]),
            "spending": float(row["SpendingScore"]),
            "cluster": int(row["ClusterID"]),
            "segment": row["SegmentLabel"],
            "color": colour_of[row["SegmentLabel"]],
        })

    return jsonify({"query": query, "results": results, "dataset_is_default": _state["dataset_is_default"]})


@app.route("/api/search/suggest")
@login_required
def api_search_suggest():
    """
    Lightweight autocomplete: up to 8 name/ID suggestions for whatever
    has been typed so far, from the same hardcoded demo directory
    /api/search matches against. Kept as a separate, tiny endpoint so
    the frontend can call it on every keystroke without re-running a
    full search-and-classify pass each time.
    """
    query = request.args.get("q", "")
    suggestions = suggest_directory(query, limit=8)
    return jsonify({"suggestions": suggestions})


def _open_browser():
    webbrowser.open(f"http://{HOST}:{PORT}")


if __name__ == "__main__":
    print("=" * 60)
    print("  Fitting pipeline (preprocessor -> clustering -> evaluator) ...")
    print("=" * 60)
    build_pipeline()
    print(f"  Pipeline ready. Starting Flask dev server on http://{HOST}:{PORT}")

    # Open the default browser shortly after the server starts listening,
    # rather than before -- app.run() below blocks the main thread, so the
    # browser open is scheduled on a short timer from a background thread.
    # Skipped automatically if this is Flask's debug-mode reloader child
    # process re-executing (avoids opening two tabs).
    if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        threading.Timer(1.25, _open_browser).start()

    app.run(host=HOST, port=PORT, debug=False)
