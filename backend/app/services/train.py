"""CLI orchestration: snapshot, pure fitting, file artifacts, then a database run record."""

import json
import os
import re
from dataclasses import asdict
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from pathlib import Path
from uuid import uuid4

from ml.features import FEATURE_COLUMNS, FEATURE_SCHEMA_VERSION, build_training_frame
from ml.train import TrainingConfig, fit_models
from sqlalchemy.orm import Session

from app.core.settings import Settings
from app.db.session import make_engine
from app.repositories.model_runs import register_run
from app.repositories.training import read_training_inputs
from app.services.artifacts import remove_unregistered_artifacts, save_artifacts


def dependency_versions() -> dict[str, str]:
    versions = {}
    for package in ("numpy", "pandas", "scikit-learn", "shap", "joblib", "xgboost-cpu", "xgboost"):
        try:
            versions[package] = package_version(package)
        except PackageNotFoundError:
            continue
    return versions


def main() -> None:
    git_sha = os.environ.get("TRAIN_GIT_SHA", "")
    if not re.fullmatch(r"[0-9a-f]{40,64}", git_sha):
        raise SystemExit("Run make train from a committed Git checkout to record the source SHA")
    config = TrainingConfig(random_seed=int(os.environ.get("TRAIN_RANDOM", "42")))
    root = Path(os.environ.get("MODEL_ARTIFACT_DIR", "/app/ml/artifacts"))
    engine = make_engine(Settings.from_env())
    try:
        print("Reading a repeatable-read synthetic training snapshot", flush=True)
        with Session(engine) as session, session.begin():
            inputs = read_training_inputs(session)
        frame = build_training_frame(inputs, config.features)
        print(f"Fitting models on {len(frame)} chronological asset-month rows", flush=True)
        result = fit_models(frame, config)
        trained_at = datetime.now(UTC)
        version = trained_at.strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid4().hex[:12]
        metadata: dict[str, object] = {
            "model_version": version,
            "trained_at": trained_at.isoformat(),
            "data_hash": inputs.data_hash,
            "features": list(FEATURE_COLUMNS),
            "feature_schema": FEATURE_SCHEMA_VERSION,
            "git_sha": git_sha,
            "training_config": asdict(config),
            "dependency_versions": dependency_versions(),
            "synthetic_data_only": True,
        }
        path = save_artifacts(root, version, result, metadata)
        try:
            with Session(engine) as session, session.begin():
                register_run(
                    session,
                    version=version,
                    trained_at=trained_at,
                    data_hash=inputs.data_hash,
                    features=list(FEATURE_COLUMNS),
                    metrics=result.metrics,
                    git_sha=git_sha,
                )
        except Exception:
            remove_unregistered_artifacts(root, version)
            raise
        print(
            json.dumps(
                {
                    "model_version": version,
                    "artifacts": str(path),
                    "data_hash": inputs.data_hash,
                    "metrics": result.metrics,
                },
                indent=2,
            )
        )
        if not result.metrics["quality_gate_passed"]:
            raise SystemExit("Run recorded, but XGBoost did not beat baseline PR-AUC")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
