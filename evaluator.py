"""
evaluator.py
Quantitative cluster quality assessment using three complementary metrics:
  • WCSS / Elbow curve  – internal compactness
  • Silhouette Score    – cohesion vs. separation balance
  • Davies-Bouldin Index – average inter-cluster similarity (lower is better)
"""

import numpy as np
import pandas as pd
from sklearn.metrics import silhouette_score, davies_bouldin_score

from config import K_MIN, K_MAX


class ClusterEvaluator:
    """
    Compute and tabulate evaluation metrics across all k values tested
    during the sweep phase of CustomerSegmenter.
    """

    def __init__(self, sweep_results: dict, X_scaled: np.ndarray):
        self.sweep  = sweep_results
        self.X      = X_scaled
        self._table = None

    # ── Public API ────────────────────────────────────────────────────────────

    def build_metrics_table(self) -> pd.DataFrame:
        """
        Compute silhouette and Davies-Bouldin scores for every k in the sweep.
        """
        rows = []
        for k, res in sorted(self.sweep.items()):
            labels = res["model"].labels_
            sil = silhouette_score(self.X, labels) if k > 1 else np.nan
            dbi = davies_bouldin_score(self.X, labels) if k > 1 else np.nan
            rows.append({
                "k":                  k,
                "WCSS":               round(res["wcss"], 2),
                "SilhouetteScore":    round(sil, 4) if not np.isnan(sil) else np.nan,
                "DaviesBouldinIndex": round(dbi, 4) if not np.isnan(dbi) else np.nan,
            })

        self._table = pd.DataFrame(rows).set_index("k")
        print("[evaluator] Metrics table computed.")
        return self._table

    def suggest_optimal_k(self) -> int:
        """
        Identify the k with the highest silhouette score as a data-driven
        recommendation (complements visual elbow inspection).
        """
        if self._table is None:
            self.build_metrics_table()
        best_k = int(self._table["SilhouetteScore"].idxmax())
        print(f"[evaluator] Suggested optimal k = {best_k}  "
              f"(silhouette = {self._table.loc[best_k, 'SilhouetteScore']:.4f})")
        return best_k

    def wcss_series(self) -> tuple:
        """Return (k_values, wcss_values) lists suitable for plotting."""
        ks   = sorted(self.sweep.keys())
        wcss = [self.sweep[k]["wcss"] for k in ks]
        return ks, wcss

    def get_table(self) -> pd.DataFrame:
        if self._table is None:
            self.build_metrics_table()
        return self._table


if __name__ == "__main__":
    from preprocessor import DataPreprocessor
    from clustering   import CustomerSegmenter

    prep = DataPreprocessor().run()
    seg  = CustomerSegmenter()
    seg.sweep(prep.scaled)

    ev = ClusterEvaluator(seg._sweep_results, prep.scaled)
    print(ev.build_metrics_table())
    ev.suggest_optimal_k()