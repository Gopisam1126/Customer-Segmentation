"""
preprocessor.py
Loads, validates, cleans, and scales the Mall_Customers dataset.
Features used: AnnualIncome_k (Annual Income (k$)) and SpendingScore
(Spending Score (1-100)). Gender and Age columns are retained in
clean_df for optional analysis but are NOT used as clustering features.
"""

import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler

from config import DATASET_CSV, INCOME_RANGE, SCORE_RANGE

# Columns expected in the raw CSV
_RAW_INCOME_COL = "Annual Income (k$)"
_RAW_SCORE_COL  = "Spending Score (1-100)"
_RAW_ID_COL     = "CustomerID"

# Normalised column names used throughout the rest of the pipeline
FEATURE_COLS = ["AnnualIncome_k", "SpendingScore"]


class DataPreprocessor:
    """
    Encapsulates the full preprocessing workflow:
    load → rename → validate → clean → scale.

    Attributes
    ----------
    raw_df    : original loaded DataFrame (unmodified)
    clean_df  : DataFrame after renaming, validation, and cleaning
    features  : NumPy array of raw feature values (before scaling)
    scaled    : NumPy array of StandardScaler-transformed features
    scaler    : fitted StandardScaler instance (for inverse transforms)
    """

    def __init__(self, path: str = DATASET_CSV):
        self.path   = path
        self.scaler = StandardScaler()
        self.raw_df = self.clean_df = None
        self.features = self.scaled = None

    # ── Public API ────────────────────────────────────────────────────────────

    def run(self) -> "DataPreprocessor":
        """Execute the complete preprocessing chain and return self."""
        self.raw_df   = self._load()
        self.clean_df = self._clean(self.raw_df.copy())
        self.features = self.clean_df[FEATURE_COLS].values
        self.scaled   = self._scale(self.features)
        self._report()
        return self

    def get_summary(self) -> pd.DataFrame:
        return self.clean_df[FEATURE_COLS].describe().round(2)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _load(self) -> pd.DataFrame:
        df = pd.read_csv(self.path)

        # Accept either the raw Mall_Customers column names or pre-renamed names
        if _RAW_INCOME_COL in df.columns:
            rename_map = {
                _RAW_INCOME_COL: "AnnualIncome_k",
                _RAW_SCORE_COL:  "SpendingScore",
                _RAW_ID_COL:     "CustomerID",
            }
            # Dataset header may say "Genre" or "Gender" — normalise to "Gender"
            if "Genre" in df.columns:
                rename_map["Genre"] = "Gender"
            df.rename(columns=rename_map, inplace=True)

        assert set(FEATURE_COLS).issubset(df.columns), (
            f"Dataset must contain columns: {FEATURE_COLS}\n"
            f"Found: {list(df.columns)}"
        )
        print(f"[preprocessor] Loaded {len(df)} records from {self.path}")
        return df

    def _clean(self, df: pd.DataFrame) -> pd.DataFrame:
        before = len(df)

        # Drop exact duplicates
        df.drop_duplicates(inplace=True)

        # Drop rows with missing feature values
        df.dropna(subset=FEATURE_COLS, inplace=True)

        # Enforce domain bounds
        df = df[
            df["AnnualIncome_k"].between(*INCOME_RANGE) &
            df["SpendingScore"].between(*SCORE_RANGE)
        ]

        dropped = before - len(df)
        if dropped:
            print(f"[preprocessor] Removed {dropped} invalid/duplicate rows.")
        df.reset_index(drop=True, inplace=True)
        return df

    def _scale(self, X: np.ndarray) -> np.ndarray:
        """Fit StandardScaler on X and return transformed array."""
        return self.scaler.fit_transform(X)

    def _report(self) -> None:
        print(f"[preprocessor] Clean records : {len(self.clean_df)}")
        print(f"[preprocessor] Feature means : {self.scaler.mean_.round(2)}")
        print(f"[preprocessor] Feature stds  : {self.scaler.scale_.round(2)}")


if __name__ == "__main__":
    prep = DataPreprocessor().run()
    print(prep.get_summary())