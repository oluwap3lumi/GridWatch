"""Latest available passing model metadata, distinct from the last scored version."""

from fastapi import APIRouter, HTTPException

from app.api.dependencies import ArtifactRoot, ReadSession
from app.api.v1.queries import Limit, Offset
from app.core.errors import ModelUnavailable, ScoringConflict
from app.repositories.model_runs import latest_passing_run, model_history
from app.repositories.risk import scoring_stamp
from app.schemas.assets import ErrorResponse
from app.schemas.risk import FeatureImportance, ModelHistory, ModelInfo
from app.services.model_registry import registered_documents

router = APIRouter(tags=["model"])


@router.get("/model/history", response_model=ModelHistory)
def history(session: ReadSession, limit: Limit = 100, offset: Offset = 0) -> ModelHistory:
    """Registered run history, including failed gates; does not deserialize model files."""
    return model_history(session, limit=limit, offset=offset)


@router.get(
    "/model",
    response_model=ModelInfo,
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
def model_info(session: ReadSession, root: ArtifactRoot) -> ModelInfo:
    """Read verified provenance, validation metrics, and mean absolute raw TreeSHAP importance."""
    run = latest_passing_run(session)
    if run is None:
        raise HTTPException(status_code=404, detail="No passing trained model is available")
    try:
        _, evaluation = registered_documents(root, run)
        stamp = scoring_stamp(session)
    except ModelUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ScoringConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    importance = sorted(
        evaluation.shap.mean_absolute_contribution.items(), key=lambda item: (-item[1], item[0])
    )
    return ModelInfo(
        model_version=run.model_version,
        trained_at=run.trained_at,
        data_hash=run.data_hash,
        git_sha=run.git_sha,
        features=run.features,
        metrics=run.metrics,
        feature_importance=[
            FeatureImportance(feature=name, mean_absolute_contribution=value)
            for name, value in importance
        ],
        scored_model_version=None if stamp is None else stamp.model_version,
    )
