"""Asset, outage, and paginated GeoJSON contracts for the v1 API."""

from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, FiniteFloat

from app.schemas.base import ApiModel
from app.schemas.inference import InferenceDetails
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


class RiskFactor(ApiModel):
    feature: str
    feature_value: FiniteFloat
    contribution: FiniteFloat
    contribution_unit: Literal["log_odds"] = "log_odds"


class RiskSnapshot(InferenceDetails):
    score: FiniteFloat = Field(ge=0, le=1)
    band: RiskBand
    model_version: str
    scored_at: datetime
    prediction_cutoff: datetime | None
    horizon_days: Literal[30] = 30
    top_factors: list[RiskFactor]


class AssetProperties(ApiModel):
    type: AssetKind
    feeder_id: int | None
    external_id: str | None = None
    pole_id: int | None = None
    batch_id: str | None = None
    install_date: date | None
    capacity_kva: FiniteFloat | None
    load_factor: FiniteFloat | None
    material: str | None
    vegetation_index: FiniteFloat | None
    last_maintenance_date: date | None
    risk: RiskSnapshot | None


class AssetFeature(ApiModel):
    type: Literal["Feature"] = "Feature"
    id: int
    geometry: AssetGeometry
    properties: AssetProperties


class PageMetadata(ApiModel):
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    next_offset: int | None


class AssetCollection(ApiModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[AssetFeature]
    pagination: PageMetadata


class OutageProperties(ApiModel):
    asset_id: int
    started_at: datetime
    duration_min: FiniteFloat
    cause: str


class OutageFeature(ApiModel):
    type: Literal["Feature"] = "Feature"
    id: int
    geometry: PointGeometry
    properties: OutageProperties


class OutageCollection(ApiModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[OutageFeature]
    pagination: PageMetadata


class AssetDetail(ApiModel):
    asset: AssetFeature
    outages: OutageCollection


class ErrorResponse(ApiModel):
    detail: str
