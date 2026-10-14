"""Pure prediction using the saved feature contract and calibrated estimator."""

import pandas as pd

from ml.features import FEATURE_COLUMNS, FEATURE_SCHEMA_VERSION, FloatArray
from ml.train import ModelBundle, model_matrix, probabilities


def predict_probabilities(bundle: ModelBundle, features: pd.DataFrame) -> FloatArray:
    if bundle.feature_names != FEATURE_COLUMNS or bundle.feature_schema != FEATURE_SCHEMA_VERSION:
        raise ValueError("Model feature contract does not match this feature builder")
    return probabilities(bundle.model, model_matrix(features))
