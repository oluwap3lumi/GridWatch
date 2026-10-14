"""Pure prediction using the saved feature contract and calibrated estimator."""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ml.evaluate import tree_explanation
from ml.features import FEATURE_COLUMNS, FEATURE_SCHEMA_VERSION, FloatArray
from ml.train import ModelBundle, model_matrix, probabilities


def predict_probabilities(bundle: ModelBundle, features: pd.DataFrame) -> FloatArray:
    if bundle.feature_names != FEATURE_COLUMNS or bundle.feature_schema != FEATURE_SCHEMA_VERSION:
        raise ValueError("Model feature contract does not match this feature builder")
    return probabilities(bundle.model, model_matrix(features))


@dataclass(frozen=True)
class FactorContribution:
    feature: str
    feature_value: float
    contribution: float


@dataclass(frozen=True)
class AssetPrediction:
    asset_id: int
    score: float
    factors: tuple[FactorContribution, ...]


def score_features(bundle: ModelBundle, features: pd.DataFrame) -> tuple[AssetPrediction, ...]:
    """Return calibrated probabilities and the five strongest signed raw-log-odds factors."""
    scores = predict_probabilities(bundle, features)
    explanation = tree_explanation(bundle.raw_xgboost, model_matrix(features))
    contributions = np.asarray(explanation.values, dtype=np.float64)
    values = model_matrix(features).to_numpy(dtype=float)
    ids = features.asset_id.to_numpy(dtype=np.int64)
    predictions = []
    for index, asset_id in enumerate(ids):
        ranked = np.argsort(-np.abs(contributions[index]), kind="stable")[:5]
        factors = tuple(
            FactorContribution(
                feature=FEATURE_COLUMNS[int(column)],
                feature_value=float(values[index, column]),
                contribution=float(contributions[index, column]),
            )
            for column in ranked
            if contributions[index, column] != 0
        )
        predictions.append(AssetPrediction(int(asset_id), float(scores[index]), factors))
    return tuple(predictions)
