"""Validate registered file provenance before exposing or using a trained model."""

from pathlib import Path

from pydantic import RootModel

from app.core.errors import ModelUnavailable
from app.db.models import ModelRun
from app.schemas.risk import ArtifactEvaluation, ArtifactMetadata
from app.services.artifacts import verify_artifacts


class ArtifactMetrics(RootModel[dict[str, float | int]]):
    """Numerical metrics must match their immutable database record exactly."""


def registered_documents(root: Path, run: ModelRun) -> tuple[ArtifactMetadata, ArtifactEvaluation]:
    try:
        path = verify_artifacts(root, run.model_version)
        metadata = ArtifactMetadata.model_validate_json((path / "metadata.json").read_text())
        metrics = ArtifactMetrics.model_validate_json((path / "metrics.json").read_text()).root
        evaluation = ArtifactEvaluation.model_validate_json((path / "evaluation.json").read_text())
        if (
            metadata.model_version != run.model_version
            or metadata.trained_at != run.trained_at
            or metadata.data_hash != run.data_hash
            or metadata.git_sha != run.git_sha
            or metadata.features != run.features
            or metrics != run.metrics
            or metadata.training_config.features.horizon_days != 30
            or metadata.training_config.features.history_days != 365
            or metadata.training_config.features.weather_days != 30
            or set(evaluation.shap.mean_absolute_contribution) != set(run.features)
        ):
            raise ValueError("Artifact provenance does not match its registered run")
        return metadata, evaluation
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ModelUnavailable(
            "Registered model artifacts are missing, invalid, or incompatible"
        ) from exc
