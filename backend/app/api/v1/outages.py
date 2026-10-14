"""Paginated outage GeoJSON with half-open UTC time and bounding-box filters."""

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.dependencies import ReadSession
from app.api.v1.queries import BBoxQuery, Limit, Offset, TimeBounds
from app.repositories.assets import list_outages
from app.schemas.assets import OutageCollection

router = APIRouter(tags=["outages"])


@router.get("/outages", response_model=OutageCollection)
def outages(
    session: ReadSession,
    bbox: BBoxQuery,
    bounds: TimeBounds,
    asset_id: Annotated[int | None, Query(ge=1)] = None,
    limit: Limit = 100,
    offset: Offset = 0,
) -> OutageCollection:
    """Return newest-first events, breaking timestamp ties by descending event ID."""
    return list_outages(
        session,
        limit=limit,
        offset=offset,
        asset_id=asset_id,
        bbox=bbox,
        started_after=bounds[0],
        started_before=bounds[1],
    )
