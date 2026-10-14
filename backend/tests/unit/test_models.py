"""Metrics, fitting determinism, prediction contracts, and exact SHAP additivity."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from ml.evaluate import probability_metrics, tree_explanation
from ml.features import FEATURE_COLUMNS
from ml.predict import predict_probabilities, score_features
from ml.split import temporal_split
from ml.train import TrainingConfig, fit_models
from xgboost import DMatrix

from app.services.artifacts import (
    load_artifacts,
    remove_unregistered_artifacts,
    save_artifacts,
    version_path,
)


def synthetic_frame() -> pd.DataFrame:
    rng = np.random.default_rng(42)
    rows = []
    for month in range(1, 13):
        cutoff = datetime(2025, month, 1, tzinfo=UTC)
        for index in range(100):
            first, second = rng.uniform(size=2)
            row: dict[str, object] = dict.fromkeys(FEATURE_COLUMNS, 0.0)
            row.update(
                asset_age_years=first * 50,
                vegetation_index=second,
                asset_id=index,
                cutoff=cutoff,
                target_end=cutoff + timedelta(days=30),
                target=int((first > 0.5) != (second > 0.5)),
            )
            rows.append(row)
    return pd.DataFrame(rows)


def test_metrics_and_invalid_probabilities() -> None:
    labels = np.array([0, 1, 0, 1], dtype=np.int64)
    metrics = probability_metrics(labels, np.array([0.1, 0.8, 0.2, 0.9]))
    assert metrics["roc_auc"] == 1
    assert metrics["pr_auc"] == 1
    assert metrics["precision_at_top_k"] == 1
    assert metrics["top_k"] == 1
    assert metrics["brier_score"] == pytest.approx(0.025)
    assert metrics["expected_calibration_error"] == pytest.approx(0.15)
    with pytest.raises(ValueError, match="finite"):
        probability_metrics(labels, np.array([0.1, np.nan, 0.2, 0.9]))


def test_training_reproducibility_shap_and_prediction_contract(tmp_path: Path) -> None:
    frame = synthetic_frame()
    first = fit_models(frame, TrainingConfig())
    second = fit_models(frame, TrainingConfig())
    assert first.metrics == second.metrics
    assert first.report == second.report
    validation = temporal_split(frame).validation
    probabilities = predict_probabilities(first.bundle, validation)
    np.testing.assert_array_equal(probabilities, predict_probabilities(second.bundle, validation))
    assert ((probabilities >= 0) & (probabilities <= 1)).all()
    scored = score_features(first.bundle, validation)
    np.testing.assert_array_equal([prediction.score for prediction in scored], probabilities)
    assert [prediction.asset_id for prediction in scored] == list(validation.asset_id)
    for prediction in scored:
        assert len(prediction.factors) <= 5
        assert [abs(factor.contribution) for factor in prediction.factors] == sorted(
            (abs(factor.contribution) for factor in prediction.factors), reverse=True
        )
    explanation = tree_explanation(first.bundle.raw_xgboost, validation)
    margin = first.bundle.raw_xgboost.get_booster().predict(
        DMatrix(validation.loc[:, list(FEATURE_COLUMNS)].astype(float)), output_margin=True
    )
    np.testing.assert_allclose(
        np.asarray(explanation.base_values) + np.asarray(explanation.values).sum(axis=1),
        margin,
        atol=1e-5,
    )
    with pytest.raises(ValueError, match="contract"):
        predict_probabilities(replace(first.bundle, feature_schema="future"), validation)
    with pytest.raises(ValueError, match="Missing"):
        predict_probabilities(first.bundle, validation.drop(columns=[FEATURE_COLUMNS[0]]))
    path = save_artifacts(tmp_path, "test-run", first, {"synthetic_data_only": True})
    np.testing.assert_array_equal(
        probabilities, predict_probabilities(load_artifacts(tmp_path, "test-run"), validation)
    )
    with pytest.raises(FileExistsError):
        save_artifacts(tmp_path, "test-run", second, {})
    (path / "metrics.json").write_text("{}")
    with pytest.raises(ValueError, match="checksum"):
        load_artifacts(tmp_path, "test-run")
    (path / "manifest.json").write_text("null")
    with pytest.raises(ValueError, match="manifest"):
        load_artifacts(tmp_path, "test-run")
    save_artifacts(tmp_path, "unregistered", second, {})
    remove_unregistered_artifacts(tmp_path, "unregistered")
    assert path.exists() and not (tmp_path / "unregistered").exists()
    with pytest.raises(ValueError, match="Invalid"):
        version_path(tmp_path, "../escape")
