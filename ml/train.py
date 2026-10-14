"""Deterministic CPU fitting and temporal comparison, without DB or file access."""

from dataclasses import dataclass, field
from typing import Protocol, cast

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.frozen import FrozenEstimator
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

from ml.evaluate import LabelArray, probability_metrics, reliability_bins, shap_summary
from ml.features import FEATURE_COLUMNS, FEATURE_SCHEMA_VERSION, FeatureConfig, FloatArray
from ml.split import temporal_split


class ProbabilityModel(Protocol):
    def predict_proba(self, features: pd.DataFrame) -> object: ...


@dataclass(frozen=True)
class TrainingConfig:
    random_seed: int = 42
    features: FeatureConfig = field(default_factory=FeatureConfig)


@dataclass(frozen=True)
class ModelBundle:
    model: ProbabilityModel
    baseline: ProbabilityModel
    raw_xgboost: XGBClassifier
    feature_names: tuple[str, ...] = FEATURE_COLUMNS
    feature_schema: str = FEATURE_SCHEMA_VERSION
    feature_config: FeatureConfig = field(default_factory=FeatureConfig)


@dataclass(frozen=True)
class TrainingResult:
    bundle: ModelBundle
    metrics: dict[str, float | int]
    report: dict[str, object]


def model_matrix(frame: pd.DataFrame) -> pd.DataFrame:
    missing = set(FEATURE_COLUMNS) - set(frame.columns)
    if missing:
        raise ValueError(f"Missing model features: {sorted(missing)}")
    matrix = frame.loc[:, list(FEATURE_COLUMNS)].astype(float)
    if not np.isfinite(matrix.to_numpy(dtype=float)).all():
        raise ValueError("Model features must be finite")
    return matrix


def probabilities(model: ProbabilityModel, matrix: pd.DataFrame) -> FloatArray:
    return np.asarray(model.predict_proba(matrix), dtype=np.float64)[:, 1]


def fit_models(frame: pd.DataFrame, config: TrainingConfig) -> TrainingResult:
    """Select on tuning AP, fit on training only, calibrate separately, then evaluate once."""
    split = temporal_split(frame)
    train_x, tune_x = model_matrix(split.train), model_matrix(split.tune)
    train_y = split.train.target.to_numpy(dtype=np.int64)
    tune_y = split.tune.target.to_numpy(dtype=np.int64)
    baseline_candidates = []
    for regularization in (0.01, 0.1, 1.0, 10.0):
        candidate = make_pipeline(
            StandardScaler(),
            LogisticRegression(C=regularization, max_iter=1000, random_state=config.random_seed),
        ).fit(train_x, train_y)
        score = float(average_precision_score(tune_y, probabilities(candidate, tune_x)))
        baseline_candidates.append((score, regularization, candidate))
    baseline_score, baseline_c, baseline = max(baseline_candidates, key=lambda item: item[0])
    xgb_candidates: list[tuple[float, dict[str, int | float], XGBClassifier]] = []
    for depth in (1, 2, 3):
        for trees in (100, 300, 600):
            params: dict[str, int | float] = {
                "max_depth": depth,
                "n_estimators": trees,
                "learning_rate": 0.03,
                "min_child_weight": 20,
                "reg_lambda": 10.0,
            }
            candidate_xgb = XGBClassifier(
                **params,
                objective="binary:logistic",
                eval_metric="logloss",
                tree_method="hist",
                n_jobs=1,
                random_state=config.random_seed,
            )
            candidate_xgb.fit(train_x, train_y)
            score = float(
                average_precision_score(tune_y, candidate_xgb.predict_proba(tune_x)[:, 1])
            )
            xgb_candidates.append((score, params, candidate_xgb))
    xgb_score, xgb_params, xgboost = max(xgb_candidates, key=lambda item: item[0])
    calibration_x = model_matrix(split.calibration)
    calibration_y = split.calibration.target.to_numpy(dtype=np.int64)
    calibrated_baseline = CalibratedClassifierCV(FrozenEstimator(baseline), method="sigmoid").fit(
        calibration_x, calibration_y
    )
    calibrated_xgb = CalibratedClassifierCV(FrozenEstimator(xgboost), method="sigmoid").fit(
        calibration_x, calibration_y
    )
    validation_x = model_matrix(split.validation)
    validation_y: LabelArray = split.validation.target.to_numpy(dtype=np.int64)
    baseline_probs = probabilities(calibrated_baseline, validation_x)
    xgb_probs = probabilities(calibrated_xgb, validation_x)
    baseline_metrics = probability_metrics(validation_y, baseline_probs)
    xgb_metrics = probability_metrics(validation_y, xgb_probs)
    raw_metrics = probability_metrics(validation_y, probabilities(xgboost, validation_x))
    metrics = {
        **{f"baseline_{key}": value for key, value in baseline_metrics.items()},
        **{f"xgboost_{key}": value for key, value in xgb_metrics.items()},
        **{f"raw_xgboost_{key}": value for key, value in raw_metrics.items()},
        "pr_auc_lift": float(xgb_metrics["pr_auc"]) - float(baseline_metrics["pr_auc"]),
    }
    report: dict[str, object] = {
        "selected_parameters": {"baseline_C": baseline_c, "xgboost": xgb_params},
        "tuning_pr_auc": {"baseline": baseline_score, "xgboost": xgb_score},
        "partitions": {
            name: {
                "first_cutoff": group.cutoff.min().isoformat(),
                "last_cutoff": group.cutoff.max().isoformat(),
                "last_label_end": group.target_end.max().isoformat(),
                "rows": len(group),
                "positives": int(group.target.sum()),
            }
            for name, group in (
                ("train", split.train),
                ("tune", split.tune),
                ("calibration", split.calibration),
                ("validation", split.validation),
            )
        },
        "calibration": {
            "method": "held-out sigmoid",
            "baseline": reliability_bins(validation_y, baseline_probs),
            "xgboost": reliability_bins(validation_y, xgb_probs),
        },
        "shap": shap_summary(xgboost, validation_x),
        "quality_gate_passed": metrics["pr_auc_lift"] > 0,
    }
    return TrainingResult(
        ModelBundle(
            cast(ProbabilityModel, calibrated_xgb),
            cast(ProbabilityModel, calibrated_baseline),
            xgboost,
            feature_config=config.features,
        ),
        metrics,
        report,
    )
