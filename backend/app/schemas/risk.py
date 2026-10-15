"""Typed risk aggregates, hotspot GeoJSON, and model/scoring metadata."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, FiniteFloat

from app.schemas.assets import PageMetadata
from app.schemas.base import ApiModel
from app.schemas.spatial import PointGeometry


class BandCounts(ApiModel):
    low: int = Field(default=0, ge=0)
    medium: int = Field(default=0, ge=0)
    high: int = Field(default=0, ge=0)
    critical: int = Field(default=0, ge=0)


class ScoringStamp(ApiModel):
    model_version: str
    scored_at: datetime
    prediction_cutoff: datetime | None
    horizon_days: Literal[30] = 30


class RescoreResponse(ScoringStamp):
    scored_assets: int = Field(ge=0)
    unscored_assets: int = Field(ge=0)
    counts_by_band: BandCounts


class FeederSummary(ApiModel):
    feeder_id: int
    total_assets: int = Field(ge=0)
    scored_assets: int = Field(ge=0)
    unscored_assets: int = Field(ge=0)
    counts_by_band: BandCounts


class RiskSummary(ApiModel):
    total_assets: int = Field(ge=0)
    scored_assets: int = Field(ge=0)
    unscored_assets: int = Field(ge=0)
    counts_by_band: BandCounts
    by_feeder: list[FeederSummary]
    scoring: ScoringStamp | None


class HotspotProperties(ApiModel):
    asset_count: int = Field(ge=3)
    asset_ids: list[int]
    mean_score: FiniteFloat = Field(ge=0, le=1)
    max_score: FiniteFloat = Field(ge=0, le=1)
    counts_by_band: BandCounts


class HotspotFeature(ApiModel):
    type: Literal["Feature"] = "Feature"
    id: int
    geometry: PointGeometry
    properties: HotspotProperties


class HotspotCollection(ApiModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[HotspotFeature]
    pagination: PageMetadata
    radius_m: Literal[500] = 500
    minimum_assets: Literal[3] = 3


class FeatureImportance(ApiModel):
    feature: str
    mean_absolute_contribution: FiniteFloat = Field(ge=0)


class ModelInfo(ApiModel):
    model_version: str
    trained_at: datetime
    data_hash: str
    git_sha: str
    features: list[str]
    metrics: dict[str, float | int]
    feature_importance: list[FeatureImportance]
    explanation_space: Literal["uncalibrated XGBoost log-odds"] = "uncalibrated XGBoost log-odds"
    horizon_days: Literal[30] = 30
    scored_model_version: str | None


class ModelVersion(ApiModel):
    """Registered evaluation record; passing the gate does not verify artifact availability."""

    model_version: str
    trained_at: datetime
    data_hash: str
    git_sha: str
    features: list[str]
    metrics: dict[str, float | int]
    quality_gate_passed: bool


class ModelHistory(ApiModel):
    items: list[ModelVersion]
    pagination: PageMetadata


class ArtifactHistoryConfig(BaseModel):
    horizon_days: int
    history_days: int
    weather_days: int


class ArtifactTrainingConfig(BaseModel):
    random_seed: int
    features: ArtifactHistoryConfig


class ArtifactMetadata(BaseModel):
    model_version: str
    trained_at: datetime
    data_hash: str
    git_sha: str
    features: list[str]
    feature_schema: str
    training_config: ArtifactTrainingConfig
    dependency_versions: dict[str, str]
    synthetic_data_only: Literal[True]


class ArtifactShapReport(BaseModel):
    method: Literal["exact TreeSHAP"]
    output_space: Literal["uncalibrated XGBoost log-odds"]
    sample_rows: int = Field(gt=0)
    mean_absolute_contribution: dict[str, FiniteFloat]


class ArtifactEvaluation(BaseModel):
    shap: ArtifactShapReport
