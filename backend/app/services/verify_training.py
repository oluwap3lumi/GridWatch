"""Verify two registered runs, artifact integrity, and reloaded-model reproducibility."""

import hashlib
import json
import os
from pathlib import Path

import numpy as np
from ml.features import build_training_frame
from ml.predict import predict_probabilities
from ml.split import temporal_split
from sqlalchemy.orm import Session

from app.core.settings import Settings
from app.db.session import make_engine
from app.repositories.model_runs import recent_runs
from app.repositories.training import read_training_inputs
from app.services.artifacts import load_artifacts


def main() -> None:
    root = Path(os.environ.get("MODEL_ARTIFACT_DIR", "/app/ml/artifacts"))
    engine = make_engine(Settings.from_env())
    try:
        with Session(engine, expire_on_commit=False) as session, session.begin():
            runs = recent_runs(session)
        if len(runs) != 2:
            raise ValueError("Run make train twice before verifying reproducibility")
        if runs[0].data_hash != runs[1].data_hash or runs[0].git_sha != runs[1].git_sha:
            raise ValueError("Comparison requires the same data and source revision")
        if runs[0].features != runs[1].features or runs[0].metrics != runs[1].metrics:
            raise ValueError("Training metrics or feature lists differ")
        with Session(engine) as session, session.begin():
            inputs = read_training_inputs(session)
        if inputs.data_hash != runs[0].data_hash:
            raise ValueError("Current database does not match the trained data hash")
        bundles = [load_artifacts(root, run.model_version) for run in runs]
        validation = temporal_split(
            build_training_frame(inputs, bundles[0].feature_config)
        ).validation
        predictions = [predict_probabilities(bundle, validation) for bundle in bundles]
        np.testing.assert_array_equal(predictions[0], predictions[1])
        for run in runs:
            directory = root / run.model_version
            metadata = json.loads((directory / "metadata.json").read_text())
            metrics = json.loads((directory / "metrics.json").read_text())
            report = json.loads((directory / "evaluation.json").read_text())
            prediction_hash = hashlib.sha256(predictions[0].astype("<f8").tobytes()).hexdigest()
            if (
                metadata["data_hash"] != run.data_hash
                or metadata["git_sha"] != run.git_sha
                or metadata["features"] != run.features
                or metrics != run.metrics
                or report["validation_prediction_hash"] != prediction_hash
                or metadata["trained_at"] != run.trained_at.isoformat()
            ):
                raise ValueError("Artifact metadata does not match its database record")
        print(
            json.dumps(
                {
                    "verified_versions": [run.model_version for run in runs],
                    "identical_metrics": True,
                    "identical_reloaded_predictions": True,
                    "validation_rows": len(validation),
                    "artifact_checksums": "passed",
                },
                indent=2,
            )
        )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
