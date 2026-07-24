"""
clustering.py
Wraps scikit-learn KMeans with a clean interface for fitting, predicting,
and extracting cluster metadata across a configurable range of k values.

Key change vs. original: segment labels are assigned dynamically based on
centroid positions (Income × Spending quadrant) rather than fixed integer
mappings, so the labels remain correct regardless of KMeans's internal
cluster ordering.
"""

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans

from config import (
    OPTIMAL_K, K_MIN, K_MAX,
    KMEANS_INIT, KMEANS_N_INIT, KMEANS_MAX_ITER,
    RANDOM_SEED,
)


def _assign_labels_from_centroids(centers_orig: np.ndarray) -> dict:
    """
    Dynamically assigns a human-readable segment label to each cluster
    based on its centroid position in (Income, Spending) space.

    Quadrant rules (applied to EACH centroid relative to the global median):
        High Income  + High Spending  → "High Value"
        High Income  + Low  Spending  → "Lavish Shoppers"
        Low  Income  + High Spending  → "Budget Buyers"
        Low  Income  + Low  Spending  → "Cautious Savers"
        Middle (neither extreme)      → "Moderate Spenders"

    Returns dict: {cluster_id (int) → label (str)}
    """
    inc_med = np.median(centers_orig[:, 0])
    sco_med = np.median(centers_orig[:, 1])

    labels = {}
    for cid, (inc, sco) in enumerate(centers_orig):
        high_inc = inc >= inc_med
        high_sco = sco >= sco_med
        if high_inc and high_sco:
            labels[cid] = "High Value"
        elif high_inc and not high_sco:
            labels[cid] = "Lavish Shoppers"
        elif not high_inc and high_sco:
            labels[cid] = "Budget Buyers"
        else:
            labels[cid] = "Cautious Savers"

    # If there are multiple clusters in the same quadrant, relabel the one
    # closest to the overall centroid as "Moderate Spenders"
    from collections import Counter
    counts = Counter(labels.values())
    for label, cnt in counts.items():
        if cnt > 1:
            # Find the cluster closest to the global mean centre
            global_mean = centers_orig.mean(axis=0)
            dists = np.linalg.norm(centers_orig - global_mean, axis=1)
            duplicates = [cid for cid, lbl in labels.items() if lbl == label]
            closest = min(duplicates, key=lambda c: dists[c])
            labels[closest] = "Moderate Spenders"

    return labels


class CustomerSegmenter:
    """
    Fits KMeans for multiple k values and exposes the chosen model's output.

    Parameters
    ----------
    k : number of clusters to fit; defaults to OPTIMAL_K from config
    """

    def __init__(self, k: int = OPTIMAL_K):
        self.k             = k
        self.model         = None
        self.labels_       = None
        self.centers_      = None   # cluster centres in scaled space
        self._seg_labels   = {}     # {cluster_id → segment name}
        self._sweep_results: dict = {}

    # ── Public API ────────────────────────────────────────────────────────────

    def sweep(self, X_scaled: np.ndarray) -> dict:
        """
        Fit KMeans for every k in [K_MIN, K_MAX) and store WCSS per k.
        Used by the evaluator to draw the elbow curve.
        """
        for k in range(K_MIN, K_MAX):
            km = self._build_kmeans(k)
            km.fit(X_scaled)
            self._sweep_results[k] = {"wcss": km.inertia_, "model": km}
        print(f"[clustering] Sweep complete for k ∈ [{K_MIN}, {K_MAX - 1}]")
        return self._sweep_results

    def fit(self, X_scaled: np.ndarray, scaler=None) -> "CustomerSegmenter":
        """
        Fit the final model with self.k on the scaled feature matrix.
        Pass the fitted scaler to enable dynamic label assignment from
        centroid positions in original feature space.
        """
        if self.k in self._sweep_results:
            self.model = self._sweep_results[self.k]["model"]
        else:
            self.model = self._build_kmeans(self.k)
            self.model.fit(X_scaled)

        self.labels_  = self.model.labels_
        self.centers_ = self.model.cluster_centers_

        # Assign human-readable labels based on centroid geometry
        if scaler is not None:
            centers_orig = scaler.inverse_transform(self.centers_)
            self._seg_labels = _assign_labels_from_centroids(centers_orig)
        else:
            # Fallback: generic names
            self._seg_labels = {i: f"Cluster {i}" for i in range(self.k)}

        print(f"[clustering] Fitted KMeans with k={self.k}  "
              f"| WCSS={self.model.inertia_:.2f}")
        print(f"[clustering] Segment mapping: {self._seg_labels}")
        return self

    def annotate(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Append ClusterID and SegmentLabel columns to a copy of df.
        """
        out = df.copy()
        out["ClusterID"]    = self.labels_
        out["SegmentLabel"] = out["ClusterID"].map(self._seg_labels)
        return out

    def cluster_summary(self, df_annotated: pd.DataFrame) -> pd.DataFrame:
        """Return per-cluster descriptive statistics for the raw features."""
        return (
            df_annotated
            .groupby("SegmentLabel")[["AnnualIncome_k", "SpendingScore"]]
            .agg(["mean", "median", "std", "count"])
            .round(2)
        )

    def get_segment_labels(self) -> dict:
        return self._seg_labels

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _build_kmeans(k: int) -> KMeans:
        return KMeans(
            n_clusters=k,
            init=KMEANS_INIT,
            n_init=KMEANS_N_INIT,
            max_iter=KMEANS_MAX_ITER,
            random_state=RANDOM_SEED,
        )


if __name__ == "__main__":
    from preprocessor import DataPreprocessor
    prep = DataPreprocessor().run()
    seg  = CustomerSegmenter()
    seg.sweep(prep.scaled)
    seg.fit(prep.scaled, scaler=prep.scaler)
    df_out = seg.annotate(prep.clean_df)
    print(seg.cluster_summary(df_out))