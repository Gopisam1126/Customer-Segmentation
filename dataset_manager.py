"""
dataset_manager.py
Handles user-uploaded datasets (CSV or Excel) for the "Analyze" page's
upload feature, WITHOUT changing any logic in preprocessor.py,
clustering.py, or evaluator.py.

Design:
  - Excel files are converted to a plain CSV first (via pandas' own
    read_excel -> to_csv), so DataPreprocessor._load() only ever sees
    a CSV path, exactly like it does today. No branching on file type
    was added to preprocessor.py itself.
  - The original pipeline hardcodes dataset-shape assumptions in
    config.py: INCOME_RANGE, SCORE_RANGE (used by preprocessor's
    domain-bounds filter) and K_MAX / OPTIMAL_K (used by clustering's
    k-sweep, which needs at least K_MAX-1 rows to fit a KMeans that
    large). If an uploaded dataset has a wider income/score range, or
    fewer rows than the default k-sweep needs, those two modules would
    silently drop rows or crash. Rather than editing their logic, this
    module derives safe values for those same config constants from
    the uploaded file's own data -- the same thing a person would do
    by hand if they swapped in a new CSV and updated config.py
    themselves.
"""

import os
import uuid

import pandas as pd

import config
import preprocessor
import clustering
import evaluator
from preprocessor import FEATURE_COLS

UPLOAD_DIR = os.path.join(config.BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

_RAW_INCOME_COL = "Annual Income (k$)"
_RAW_SCORE_COL = "Spending Score (1-100)"
_RAW_ID_COL = "CustomerID"

ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls"}


class DatasetError(ValueError):
    """Raised when an uploaded file can't be used by the pipeline."""


def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Same column acceptance rule preprocessor.py uses: accept either the
    raw Mall_Customers headers or already-renamed ones. Mirrored here
    (read-only, on a copy) purely so we can validate + compute ranges
    BEFORE handing the file to DataPreprocessor, which still does its
    own renaming internally, unchanged.
    """
    df = df.copy()
    if _RAW_INCOME_COL in df.columns:
        rename_map = {
            _RAW_INCOME_COL: "AnnualIncome_k",
            _RAW_SCORE_COL: "SpendingScore",
            _RAW_ID_COL: "CustomerID",
        }
        if "Genre" in df.columns:
            rename_map["Genre"] = "Gender"
        df.rename(columns=rename_map, inplace=True)
    return df


def _read_any(path: str, original_ext: str) -> pd.DataFrame:
    if original_ext == ".csv":
        return pd.read_csv(path)
    return pd.read_excel(path)


def validate_and_stage(file_storage) -> dict:
    """
    Validate an uploaded file (werkzeug FileStorage) and stage it as a
    plain CSV that DataPreprocessor can load unmodified.

    Returns a dict describing the staged dataset:
      {
        "csv_path": str,               -- path to hand to DataPreprocessor
        "original_filename": str,
        "n_rows": int,
        "income_range": (min, max),
        "score_range": (min, max),
        "safe_k_max": int,              -- exclusive upper bound for the sweep
        "safe_optimal_k": int,          -- OPTIMAL_K clamped to what the data supports
      }

    Raises DatasetError with a human-readable message on any problem
    (bad extension, missing columns, too few rows, unreadable file).
    """
    filename = file_storage.filename or ""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise DatasetError(
            "That file type isn't supported. Please upload an Excel (.xlsx, .xls) or CSV (.csv) file."
        )

    token = uuid.uuid4().hex[:12]
    raw_path = os.path.join(UPLOAD_DIR, f"raw_{token}{ext}")
    file_storage.save(raw_path)

    try:
        df = _read_any(raw_path, ext)
    except Exception as exc:
        raise DatasetError(f"We couldn't open that file. Please check it's a valid spreadsheet. ({exc})") from exc
    finally:
        # The raw upload is no longer needed once read into memory;
        # only the normalised CSV below is kept for the pipeline to use.
        if os.path.exists(raw_path) and ext != ".csv":
            os.remove(raw_path)

    df = _normalise_columns(df)

    missing = [c for c in FEATURE_COLS if c not in df.columns]
    if missing:
        raise DatasetError(
            "Your file is missing a column we need. Please make sure it includes both "
            "a yearly income column (\"Annual Income (k$)\") and a spending column "
            "(\"Spending Score (1-100)\")."
        )

    # Drop rows with missing feature values before computing ranges, so
    # a few blank cells don't stretch the bounds with NaN comparisons.
    numeric_df = df.dropna(subset=FEATURE_COLS)
    if len(numeric_df) < config.K_MIN:
        raise DatasetError(
            f"There are only {len(numeric_df)} usable customer(s) in this file once blank rows "
            f"are removed — we need at least {config.K_MIN} to find meaningful groups."
        )

    income_min = float(numeric_df["AnnualIncome_k"].min())
    income_max = float(numeric_df["AnnualIncome_k"].max())
    score_min = float(numeric_df["SpendingScore"].min())
    score_max = float(numeric_df["SpendingScore"].max())

    # Small buffer so the exact min/max rows survive preprocessor's
    # `between()` bounds check unchanged.
    income_range = (income_min - 0.5, income_max + 0.5)
    score_range = (score_min - 0.5, score_max + 0.5)

    # The k-sweep needs at least (k-1) samples per the largest k tested.
    # Cap the sweep so it never asks KMeans for more clusters than rows.
    n_rows = len(numeric_df)
    safe_k_max = min(config.K_MAX, n_rows)          # exclusive upper bound
    safe_k_max = max(safe_k_max, config.K_MIN + 1)  # always sweep at least K_MIN
    safe_optimal_k = min(config.OPTIMAL_K, safe_k_max - 1)
    safe_optimal_k = max(safe_optimal_k, config.K_MIN)

    csv_path = os.path.join(UPLOAD_DIR, f"dataset_{token}.csv")
    df.to_csv(csv_path, index=False)

    return {
        "csv_path": csv_path,
        "original_filename": filename,
        "n_rows": n_rows,
        "income_range": income_range,
        "score_range": score_range,
        "safe_k_max": safe_k_max,
        "safe_optimal_k": safe_optimal_k,
    }


def apply_runtime_config(income_range, score_range, k_max, k_min=None) -> None:
    """
    Push dataset-derived config values into BOTH config and the pipeline
    modules that destructured those names at import time.

    preprocessor.py does `from config import INCOME_RANGE, SCORE_RANGE`
    and clustering.py / evaluator.py do `from config import ... K_MAX`,
    which binds their OWN module-level names once, at import. Reassigning
    only `config.X` afterwards would not change what those modules use.
    So we set the attribute on each consuming module directly. This adds
    no lines to and changes no logic inside those modules -- it only
    updates the value of a config constant they read, exactly as editing
    config.py by hand and restarting would, but without a restart.
    """
    k_min = config.K_MIN if k_min is None else k_min

    # Keep config in sync too, so any code reading config.X sees the change.
    config.INCOME_RANGE = income_range
    config.SCORE_RANGE = score_range
    config.K_MAX = k_max
    config.K_MIN = k_min

    # preprocessor.py: row-filtering domain bounds
    preprocessor.INCOME_RANGE = income_range
    preprocessor.SCORE_RANGE = score_range

    # clustering.py: k-sweep loop bounds (range(K_MIN, K_MAX))
    clustering.K_MAX = k_max
    clustering.K_MIN = k_min

    # evaluator.py: imported but not used in its logic; kept in sync anyway
    evaluator.K_MAX = k_max
    evaluator.K_MIN = k_min


# Snapshot of the original defaults so a reset can restore them exactly.
DEFAULT_INCOME_RANGE = (15.0, 137.0)
DEFAULT_SCORE_RANGE = (1, 100)
DEFAULT_K_MAX = 11
DEFAULT_K_MIN = 2
DEFAULT_OPTIMAL_K = 5
