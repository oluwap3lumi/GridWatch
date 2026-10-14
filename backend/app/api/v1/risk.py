"""Typed risk summaries, geography hotspots, and synchronous atomic rescoring."""

from fastapi import APIRouter, HTTPException

from app.api.dependencies import ArtifactRoot, DatabaseEngine, ReadSession
from app.api.v1.queries import BBoxQuery, Limit, Offset
from app.core.errors import ModelNotFound, ModelUnavailable, ScoringConflict
from app.repositories.risk import hotspots, risk_summary
from app.schemas.assets import ErrorResponse
from app.schemas.risk import HotspotCollection, RescoreResponse, RiskSummary
from app.services.scoring import rescore

router = APIRouter(prefix="/risk", tags=["risk"])


@router.get("/summary", response_model=RiskSummary, responses={409: {"model": ErrorResponse}})
def summary(session: ReadSession) -> RiskSummary:
    """Count all assets by demo risk band and feeder, including explicit unscored counts."""
    try:
        return risk_summary(session)
    except ScoringConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/hotspots", response_model=HotspotCollection)
def risk_hotspots(
    session: ReadSession,
    bbox: BBoxQuery,
    limit: Limit = 100,
    offset: Offset = 0,
) -> HotspotCollection:
    """Cluster high/critical assets connected within 500 metres; omit groups smaller than 3."""
    return hotspots(session, bbox=bbox, limit=limit, offset=offset)


@router.post(
    "/rescore",
    response_model=RescoreResponse,
    responses={409: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
def risk_rescore(engine: DatabaseEngine, root: ArtifactRoot) -> RescoreResponse:
    """Recompute the fleet's 30-day predictions using the latest registered passing model."""
    try:
        return rescore(engine, root)
    except (ModelNotFound, ScoringConflict) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ModelUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
