"""
config.py
Central configuration for the Customer Segmentation pipeline.
Uses the Mall_Customers real-world dataset.
"""

import os

# ── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
DATA_DIR    = os.path.join(BASE_DIR, "data")
OUTPUT_DIR  = os.path.join(BASE_DIR, "outputs")
DATASET_CSV = os.path.join(DATA_DIR, "Mall_Customers.csv")

# ── Dataset ───────────────────────────────────────────────────────────────────
RANDOM_SEED  = 42
INCOME_RANGE = (15.0, 137.0)   # annual income in thousands (USD)
SCORE_RANGE  = (1, 100)        # spending score (1 = lowest, 100 = highest)

# ── Clustering ────────────────────────────────────────────────────────────────
K_MIN           = 2            # smallest k for elbow / silhouette sweep
K_MAX           = 11           # exclusive upper bound for the sweep
OPTIMAL_K       = 5            # determined from elbow + silhouette analysis
KMEANS_INIT     = "k-means++"
KMEANS_N_INIT   = 20           # independent runs per k value
KMEANS_MAX_ITER = 400

# ── Visualization ─────────────────────────────────────────────────────────────
FIGURE_DPI = 150
PALETTE    = [
    "#E63946", "#457B9D", "#2A9D8F",
    "#E9C46A", "#F4A261", "#6A0572",
    "#264653", "#A8DADC",
]

# Human-readable labels assigned to clusters after inspection
# Assigned based on centroid positions in Income-Spending space:
#   Cluster ordering is determined at runtime; labels are mapped post-fit
#   via assign_segment_labels() in clustering.py
SEGMENT_LABELS = {
    0: "Cautious Savers",      # Low income, Low spending
    1: "Budget Buyers",        # Low income, High spending
    2: "Moderate Spenders",    # Middle income, Moderate spending
    3: "High Value",           # High income, High spending
    4: "Lavish Shoppers",      # High income, Low spending
}