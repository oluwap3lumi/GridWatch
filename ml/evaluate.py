"""Pure probability metrics, reliability bins, and exact TreeSHAP summaries."""

import math
from typing import TypedDict

import numpy as np
import pandas as pd
import shap
from numpy.typing import NDArray
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score
from xgboost import DMatrix, XGBClassifier

from ml.features import FEATURE_COLUMNS, FloatArray

type LabelArray = NDArray[np.int64]


class ReliabilityBin(TypedDict):
    lower: float
    upper: float
    count: int
    mean_probability: float
    observed_rate: float


def reliability_bins(labels: LabelArray, probabilities: FloatArray) -> list[ReliabilityBin]:
    bins: list[ReliabilityBin] = []
    assignments = np.minimum((probabilities * 10).astype(int), 9)
    for index in range(10):
        mask = assignments == index
        if mask.any():
            bins.append(
                ReliabilityBin(
                    lower=index / 10,
                    upper=(index + 1) / 10,
                    count=int(mask.sum()),
                    mean_probability=float(probabilities[mask].mean()),
                    observed_rate=float(labels[mask].mean()),
                )
            )
    return bins


def probability_metrics(labels: LabelArray, probabilities: FloatArray) -> dict[str, float | int]:
    """PR-AUC means average precision; top-k is the highest-risk 5% of asset-month rows."""
    if labels.ndim != 1 or labels.shape != probabilities.shape or not labels.size:
        raise ValueError(
            "Labels and probabilities must be nonempty, matching one-dimensional arrays"
        )
    if set(np.unique(labels)) != {0, 1}:
        raise ValueError("Evaluation requires both binary classes")
    if not np.isfinite(probabilities).all() or ((probabilities < 0) | (probabilities > 1)).any():
        raise ValueError("Probabilities must be finite and between zero and one")
    k = max(1, math.ceil(len(labels) * 0.05))
    ranked = np.argsort(-probabilities, kind="stable")[:k]
    bins = reliability_bins(labels, probabilities)
    ece = sum(b["count"] * abs(b["mean_probability"] - b["observed_rate"]) for b in bins) / len(
        labels
    )
    return {
        "roc_auc": float(roc_auc_score(labels, probabilities)),
        "pr_auc": float(average_precision_score(labels, probabilities)),
        "brier_score": float(brier_score_loss(labels, probabilities)),
        "log_loss": float(log_loss(labels, probabilities, labels=[0, 1])),
        "expected_calibration_error": ece,
        "precision_at_top_k": float(labels[ranked].mean()),
        "top_k": k,
        "rows": len(labels),
        "positives": int(labels.sum()),
        "prevalence": float(labels.mean()),
    }


def tree_explanation(model: XGBClassifier, features: pd.DataFrame) -> shap.Explanation:
    """XGBoost's exact TreeSHAP in raw log-odds space, before sigmoid calibration."""
    matrix = features.loc[:, list(FEATURE_COLUMNS)]
    contributions = np.asarray(
        model.get_booster().predict(DMatrix(matrix), pred_contribs=True), dtype=np.float64
    )
    return shap.Explanation(
        values=contributions[:, :-1],
        base_values=contributions[:, -1],
        data=matrix.to_numpy(dtype=float),
        feature_names=list(FEATURE_COLUMNS),
    )


def shap_summary(model: XGBClassifier, features: pd.DataFrame) -> dict[str, object]:
    count = min(512, len(features))
    indices = np.linspace(0, len(features) - 1, count, dtype=int)
    explanation = tree_explanation(model, features.iloc[indices])
    importance = np.abs(np.asarray(explanation.values)).mean(axis=0)
    return {
        "method": "exact TreeSHAP",
        "output_space": "uncalibrated XGBoost log-odds",
        "sample_rows": count,
        "mean_absolute_contribution": {
            name: float(value) for name, value in zip(FEATURE_COLUMNS, importance, strict=True)
        },
    }
