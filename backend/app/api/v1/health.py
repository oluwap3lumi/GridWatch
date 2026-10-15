"""Versioned API liveness endpoint."""

from fastapi import APIRouter, Response
from sqlalchemy.exc import SQLAlchemyError

from app.api.dependencies import DatabaseEngine
from app.core.observability import metrics
from app.repositories.readiness import database_ready
from app.schemas.health import HealthResponse
from app.schemas.operations import MetricsResponse, ReadinessResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    """Report that the API process is serving requests."""
    return HealthResponse()


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={503: {"model": ReadinessResponse}},
    tags=["health"],
)
def ready(engine: DatabaseEngine, response: Response) -> ReadinessResponse:
    """Require PostGIS and migrated serving tables, without requiring demo data."""
    try:
        available = database_ready(engine)
    except SQLAlchemyError:
        available = False
    if not available:
        response.status_code = 503
    return ReadinessResponse(status="ready" if available else "not_ready")


@router.get("/metrics", response_model=MetricsResponse, tags=["operations"])
def request_metrics() -> MetricsResponse:
    """Process-local HTTP counters and cumulative durations; includes no request IDs."""
    return metrics.snapshot()
