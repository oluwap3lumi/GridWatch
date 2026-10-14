"""Typed asset GeoJSON and bounded per-asset outage history."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query

from app.api.dependencies import ReadSession
from app.api.v1.queries import BBoxQuery, Limit, Offset
from app.repositories.assets import get_asset, list_assets, list_outages
from app.schemas.assets import AssetCollection, AssetDetail, AssetKind, ErrorResponse, RiskBand

router = APIRouter(tags=["assets"])


@router.get("/assets", response_model=AssetCollection)
def assets(
    session: ReadSession,
    bbox: BBoxQuery,
    kind: Annotated[AssetKind | None, Query(alias="type")] = None,
    min_risk: Annotated[float | None, Query(ge=0, le=1)] = None,
    band: RiskBand | None = None,
    limit: Limit = 100,
    offset: Offset = 0,
) -> AssetCollection:
    """Return stable ID-ordered GeoJSON; risk filters exclude unscored assets."""
    return list_assets(
        session, limit=limit, offset=offset, kind=kind, bbox=bbox, min_risk=min_risk, band=band
    )


@router.get(
    "/assets/{asset_id}", response_model=AssetDetail, responses={404: {"model": ErrorResponse}}
)
def asset_detail(
    asset_id: Annotated[int, Path(ge=1)],
    session: ReadSession,
    limit: Limit = 100,
    offset: Offset = 0,
) -> AssetDetail:
    """Return geometry, static attributes, current risk, and paginated outage history."""
    asset = get_asset(session, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    return AssetDetail(
        asset=asset,
        outages=list_outages(
            session,
            limit=limit,
            offset=offset,
            asset_id=asset_id,
        ),
    )
