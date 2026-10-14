"""Bound-parameter asset/outage queries; GeoJSON comes from PostGIS in EPSG:4326."""

from datetime import datetime

from pydantic import RootModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Asset, OutageEvent, RiskScore
from app.schemas.assets import (
    AssetCollection,
    AssetFeature,
    AssetKind,
    AssetProperties,
    OutageCollection,
    OutageFeature,
    OutageProperties,
    PageMetadata,
    RiskBand,
    RiskFactor,
    RiskSnapshot,
)
from app.schemas.spatial import AssetGeometry, BoundingBox, PointGeometry


class GeometryValue(RootModel[AssetGeometry]):
    """Validate a PostGIS geometry without an untyped JSON boundary."""


def page_metadata(total: int, limit: int, offset: int) -> PageMetadata:
    return PageMetadata(
        total=total,
        limit=limit,
        offset=offset,
        next_offset=offset + limit if offset + limit < total else None,
    )


def asset_feature(asset: Asset, risk: RiskScore | None, geometry: str) -> AssetFeature:
    snapshot = (
        None
        if risk is None
        else RiskSnapshot(
            score=risk.score,
            band=RiskBand(risk.band),
            model_version=risk.model_version,
            scored_at=risk.scored_at,
            prediction_cutoff=risk.prediction_cutoff,
            top_factors=[RiskFactor.model_validate(factor) for factor in risk.top_factors],
        )
    )
    return AssetFeature(
        id=asset.id,
        geometry=GeometryValue.model_validate_json(geometry).root,
        properties=AssetProperties(
            type=AssetKind(asset.type),
            feeder_id=asset.feeder_id,
            install_date=asset.install_date,
            capacity_kva=asset.capacity_kva,
            load_factor=asset.load_factor,
            material=asset.material,
            vegetation_index=asset.vegetation_index,
            last_maintenance_date=asset.last_maintenance_date,
            risk=snapshot,
        ),
    )


def list_assets(
    session: Session,
    *,
    limit: int,
    offset: int,
    kind: AssetKind | None = None,
    bbox: BoundingBox | None = None,
    min_risk: float | None = None,
    band: RiskBand | None = None,
) -> AssetCollection:
    query = select(Asset, RiskScore, func.ST_AsGeoJSON(Asset.geom)).outerjoin(
        RiskScore, RiskScore.asset_id == Asset.id
    )
    if kind is not None:
        query = query.where(Asset.type == kind.value)
    if bbox is not None:
        query = query.where(
            func.ST_Intersects(
                Asset.geom, func.ST_MakeEnvelope(bbox.west, bbox.south, bbox.east, bbox.north, 4326)
            )
        )
    if min_risk is not None:
        query = query.where(RiskScore.score >= min_risk)
    if band is not None:
        query = query.where(RiskScore.band == band.value)
    total = int(session.scalar(select(func.count()).select_from(query.subquery())) or 0)
    records = session.execute(query.order_by(Asset.id).limit(limit).offset(offset))
    return AssetCollection(
        features=[asset_feature(asset, risk, geometry) for asset, risk, geometry in records],
        pagination=page_metadata(total, limit, offset),
    )


def get_asset(session: Session, asset_id: int) -> AssetFeature | None:
    record = session.execute(
        select(Asset, RiskScore, func.ST_AsGeoJSON(Asset.geom))
        .outerjoin(RiskScore, RiskScore.asset_id == Asset.id)
        .where(Asset.id == asset_id)
    ).one_or_none()
    return None if record is None else asset_feature(*record)


def list_outages(
    session: Session,
    *,
    limit: int,
    offset: int,
    asset_id: int | None = None,
    bbox: BoundingBox | None = None,
    started_after: datetime | None = None,
    started_before: datetime | None = None,
) -> OutageCollection:
    query = select(OutageEvent, func.ST_AsGeoJSON(OutageEvent.geom))
    if asset_id is not None:
        query = query.where(OutageEvent.asset_id == asset_id)
    if bbox is not None:
        query = query.where(
            func.ST_Intersects(
                OutageEvent.geom,
                func.ST_MakeEnvelope(bbox.west, bbox.south, bbox.east, bbox.north, 4326),
            )
        )
    if started_after is not None:
        query = query.where(OutageEvent.started_at >= started_after)
    if started_before is not None:
        query = query.where(OutageEvent.started_at < started_before)
    total = int(session.scalar(select(func.count()).select_from(query.subquery())) or 0)
    records = session.execute(
        query.order_by(OutageEvent.started_at.desc(), OutageEvent.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return OutageCollection(
        features=[
            OutageFeature(
                id=event.id,
                geometry=PointGeometry.model_validate_json(geometry),
                properties=OutageProperties(
                    asset_id=event.asset_id,
                    started_at=event.started_at,
                    duration_min=event.duration_min,
                    cause=event.cause,
                ),
            )
            for event, geometry in records
        ],
        pagination=page_metadata(total, limit, offset),
    )
