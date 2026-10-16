"""Import lifecycle contracts; routes will expose these as M8 progresses."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, JsonValue

from app.schemas.base import ApiModel
from app.schemas.spatial import AssetGeometry

type ImportFormat = Literal["csv", "shapefile", "geojson"]
type LayerType = Literal["transformer", "pole", "feeder_line"]
type BatchStatus = Literal["uploaded", "validated", "imported", "failed", "rolled_back"]
type JobOperation = Literal["inspect", "validate", "commit", "rollback", "rescore", "cleanup"]
type JobStatus = Literal["queued", "running", "completed", "failed"]


class RowCounts(ApiModel):
    total: int = Field(default=0, ge=0)
    valid: int = Field(default=0, ge=0)
    invalid: int = Field(default=0, ge=0)
    inserted: int = Field(default=0, ge=0)
    updated: int = Field(default=0, ge=0)


class RowIssue(ApiModel):
    row_number: int = Field(ge=1)
    field: str
    code: str
    reason: str


class PreviewRow(ApiModel):
    row_number: int = Field(ge=1)
    properties: dict[str, JsonValue]
    geometry: AssetGeometry | None = None
    errors: list[RowIssue] = Field(default_factory=list)
    warnings: list[RowIssue] = Field(default_factory=list)


class JobProgress(ApiModel):
    id: UUID
    operation: JobOperation
    status: JobStatus
    processed: int = Field(ge=0)
    total: int = Field(ge=0)
    error_code: str | None = None


class ImportBatchDetail(ApiModel):
    id: UUID
    filename: str
    format: ImportFormat | None
    layer_type: LayerType
    status: BatchStatus
    row_counts: RowCounts
    detected_columns: list[str]
    column_mapping: dict[str, str]
    crs_detected: str | None
    crs_selected: str | None
    created_at: datetime
    completed_at: datetime | None
    expires_at: datetime
    preview: list[PreviewRow] = Field(default_factory=list, max_length=20)
    job: JobProgress | None = None
    errors: list[RowIssue] = Field(default_factory=list)
    extent: list[float] | None = None
    error_code: str | None = None
    warnings: list[str] = Field(default_factory=list)


class ImportHistory(ApiModel):
    items: list[ImportBatchDetail]
    total: int


class ImportExampleFeature(ApiModel):
    type: Literal["Feature"] = "Feature"
    geometry: AssetGeometry
    properties: dict[str, JsonValue]


class ImportExample(ApiModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[ImportExampleFeature]


class ValidateImport(ApiModel):
    column_mapping: dict[str, str] = Field(default_factory=dict)
    source_crs: str | None = Field(default=None, max_length=4096)
    date_format: Literal["auto", "day_first", "month_first"] = "auto"


class CommitImport(ApiModel):
    valid_rows_only: bool = False
    rescore: bool = False
    accept_scoring_defaults: bool = False
