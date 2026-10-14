"""Asset, outage, and paginated GeoJSON contracts for the v1 API."""

from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, FiniteFloat

from app.schemas.spatial import AssetGeometry, PointGeometry


class AssetKind(StrEnum):
    transformer = "transformer"
    feeder = "feeder"
    pole = "pole"


class RiskBand(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class RiskFactor(BaseModel):
    feature: str
    feature_value: FiniteFloat
    contribution: FiniteFloat
    contribution_unit: Literal["log_odds"] = "log_odds"


class RiskSnapshot(BaseModel):
    score: FiniteFloat = Field(ge=0, le=1)
    band: RiskBand
    model_version: str
    scored_at: datetime
    prediction_cutoff: datetime | None
    horizon_days: Literal[30] = 30
    top_factors: list[RiskFactor]


class AssetProperties(BaseModel):
    type: AssetKind
    feeder_id: int | None
    install_date: date
    capacity_kva: FiniteFloat
    load_factor: FiniteFloat
    material: str
    vegetation_index: FiniteFloat
    last_maintenance_date: date
    risk: RiskSnapshot | None


class AssetFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    id: int
    geometry: AssetGeometry
    properties: AssetProperties


class PageMetadata(BaseModel):
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    next_offset: int | None


class AssetCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[AssetFeature]
    pagination: PageMetadata


class OutageProperties(BaseModel):
    asset_id: int
    started_at: datetime
    duration_min: FiniteFloat
    cause: str


class OutageFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    id: int
    geometry: PointGeometry
    properties: OutageProperties


class OutageCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[OutageFeature]
    pagination: PageMetadata


class AssetDetail(BaseModel):
    asset: AssetFeature
    outages: OutageCollection


class ErrorResponse(BaseModel):
    detail: str
