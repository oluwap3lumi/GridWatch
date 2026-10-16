"""Typed SQLAlchemy models for the build-plan schema; Alembic owns all DDL."""

from datetime import date, datetime
from uuid import UUID

from geoalchemy2 import Geometry, WKBElement
from pydantic import JsonValue
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Shared metadata used by Alembic, never by create_all."""


class Asset(Base):
    """Synthetic feeder lines, transformer points, and pole points in EPSG:4326."""

    __tablename__ = "assets"
    __table_args__ = (
        CheckConstraint("type IN ('transformer', 'feeder', 'pole')", name="ck_assets_type"),
        CheckConstraint("capacity_kva >= 0 AND capacity_kva < 1000000", name="ck_assets_capacity"),
        CheckConstraint("load_factor >= 0 AND load_factor <= 2", name="ck_assets_load"),
        CheckConstraint(
            "vegetation_index >= 0 AND vegetation_index <= 1", name="ck_assets_vegetation"
        ),
        CheckConstraint("last_maintenance_date >= install_date", name="ck_assets_maintenance"),
        CheckConstraint("ST_IsValid(geom) AND NOT ST_IsEmpty(geom)", name="ck_assets_valid_geom"),
        CheckConstraint(
            "(type = 'feeder' AND GeometryType(geom) IN ('LINESTRING','MULTILINESTRING') "
            "AND feeder_id IS NULL AND pole_id IS NULL) OR "
            "(type IN ('transformer', 'pole') AND GeometryType(geom) = 'POINT' "
            "AND (type = 'transformer' OR pole_id IS NULL))",
            name="ck_assets_geometry_and_parent",
        ),
        Index("ix_assets_geom", "geom", postgresql_using="gist"),
        Index("ix_assets_type", "type"),
        Index("ix_assets_feeder_id", "feeder_id"),
        Index("ix_assets_pole_id", "pole_id"),
        Index("ix_assets_batch_id", "batch_id"),
        Index("ix_assets_last_batch_id", "last_batch_id"),
        Index("ix_assets_external_id", "type", "external_id", unique=True),
        CheckConstraint("revision >= 0", name="ck_assets_revision"),
        CheckConstraint(
            "external_id IS NULL OR length(btrim(external_id)) > 0", name="ck_assets_external_id"
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, server_default=text("nextval('asset_id_seq'::regclass)")
    )
    type: Mapped[str] = mapped_column(String(20))
    feeder_id: Mapped[int | None] = mapped_column(ForeignKey("assets.id"))
    pole_id: Mapped[int | None] = mapped_column(ForeignKey("assets.id"))
    external_id: Mapped[str | None] = mapped_column(String(255))
    external_feeder_id: Mapped[str | None] = mapped_column(String(255))
    external_pole_id: Mapped[str | None] = mapped_column(String(255))
    batch_id: Mapped[UUID | None] = mapped_column(ForeignKey("import_batches.id"))
    last_batch_id: Mapped[UUID | None] = mapped_column(ForeignKey("import_batches.id"))
    revision: Mapped[int] = mapped_column(BigInteger, server_default="0")
    geom: Mapped[WKBElement] = mapped_column(Geometry("GEOMETRY", srid=4326, spatial_index=False))
    install_date: Mapped[date | None]
    capacity_kva: Mapped[float | None] = mapped_column(Float)
    load_factor: Mapped[float | None] = mapped_column(Float)
    material: Mapped[str | None] = mapped_column(String(30))
    vegetation_index: Mapped[float | None] = mapped_column(Float)
    last_maintenance_date: Mapped[date | None]


class OutageEvent(Base):
    """Synthetic events located at a point on the affected asset."""

    __tablename__ = "outage_events"
    __table_args__ = (
        CheckConstraint("duration_min > 0 AND duration_min < 100000", name="ck_outages_duration"),
        CheckConstraint("ST_IsValid(geom) AND NOT ST_IsEmpty(geom)", name="ck_outages_valid_geom"),
        Index("ix_outages_geom", "geom", postgresql_using="gist"),
        Index("ix_outages_asset_time", "asset_id", "started_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration_min: Mapped[float] = mapped_column(Float)
    cause: Mapped[str] = mapped_column(String(40))
    geom: Mapped[WKBElement] = mapped_column(Geometry("POINT", srid=4326, spatial_index=False))


class WeatherObservation(Base):
    """Daily synthetic point observations, with UTC timestamps and physical units."""

    __tablename__ = "weather_obs"
    __table_args__ = (
        CheckConstraint("rainfall_mm >= 0 AND rainfall_mm <= 1000", name="ck_weather_rain"),
        CheckConstraint("wind_kph >= 0 AND wind_kph <= 500", name="ck_weather_wind"),
        CheckConstraint("temp_c >= -60 AND temp_c <= 65", name="ck_weather_temp"),
        CheckConstraint(
            "lightning_density >= 0 AND lightning_density <= 10000", name="ck_weather_lightning"
        ),
        CheckConstraint("ST_IsValid(geom) AND NOT ST_IsEmpty(geom)", name="ck_weather_valid_geom"),
        Index("ix_weather_geom", "geom", postgresql_using="gist"),
        Index("ix_weather_time", "observed_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    geom: Mapped[WKBElement] = mapped_column(Geometry("POINT", srid=4326, spatial_index=False))
    rainfall_mm: Mapped[float] = mapped_column(Float)
    wind_kph: Mapped[float] = mapped_column(Float)
    temp_c: Mapped[float] = mapped_column(Float)
    lightning_density: Mapped[float] = mapped_column(Float)


class ModelRun(Base):
    """Immutable provenance and evaluation metrics for each versioned model run."""

    __tablename__ = "model_runs"
    __table_args__ = (
        CheckConstraint("data_hash ~ '^[0-9a-f]{64}$'", name="ck_model_runs_data_hash"),
        Index("ix_model_runs_trained_at", "trained_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    model_version: Mapped[str] = mapped_column(String(64), unique=True)
    trained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    data_hash: Mapped[str] = mapped_column(String(64))
    features: Mapped[list[str]] = mapped_column(JSONB)
    metrics: Mapped[dict[str, float | int]] = mapped_column(JSONB)
    git_sha: Mapped[str] = mapped_column(String(64))


class RiskScore(Base):
    """Latest scored prediction per asset, with its historical cutoff and explanations."""

    __tablename__ = "risk_scores"
    __table_args__ = (
        CheckConstraint("score >= 0 AND score <= 1", name="ck_risk_scores_score"),
        CheckConstraint(
            "band IN ('low', 'medium', 'high', 'critical')", name="ck_risk_scores_band"
        ),
        Index("ix_risk_scores_band", "band"),
    )

    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), primary_key=True)
    score: Mapped[float] = mapped_column(Float)
    band: Mapped[str] = mapped_column(String(10))
    model_version: Mapped[str] = mapped_column(ForeignKey("model_runs.model_version"))
    scored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    prediction_cutoff: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    top_factors: Mapped[list[dict[str, str | float]]] = mapped_column(JSONB)


class ImportBatch(Base):
    """Private import history; preview/row data lives in expiring staged rows."""

    __tablename__ = "import_batches"
    __table_args__ = (
        CheckConstraint("format IN ('csv','shapefile','geojson')", name="ck_import_batches_format"),
        CheckConstraint(
            "layer_type IN ('transformer','pole','feeder_line')", name="ck_import_batches_layer"
        ),
        CheckConstraint(
            "status IN ('uploaded','validated','imported','failed','rolled_back')",
            name="ck_import_batches_status",
        ),
        Index("ix_import_batches_created_at", "created_at"),
        Index("ix_import_batches_expires_at", "expires_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    filename: Mapped[str] = mapped_column(String(512))
    format: Mapped[str | None] = mapped_column(String(16))
    layer_type: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), server_default="uploaded")
    row_counts: Mapped[dict[str, JsonValue]] = mapped_column(
        JSONB,
        server_default=text(
            "jsonb_build_object('total',0,'valid',0,'invalid',0,'inserted',0,'updated',0)"
        ),
    )
    detected_columns: Mapped[list[str]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    column_mapping: Mapped[dict[str, str]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb")
    )
    crs_detected: Mapped[str | None] = mapped_column(String(4096))
    crs_selected: Mapped[str | None] = mapped_column(String(4096))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    error_report: Mapped[dict[str, JsonValue]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb")
    )


class ImportJob(Base):
    """Durable job state; leases allow a separate worker to recover interrupted tasks."""

    __tablename__ = "import_jobs"
    __table_args__ = (
        CheckConstraint(
            "operation IN ('inspect','validate','commit','rollback','rescore','cleanup')",
            name="ck_import_jobs_operation",
        ),
        CheckConstraint(
            "status IN ('queued','running','completed','failed')", name="ck_import_jobs_status"
        ),
        CheckConstraint(
            "processed >= 0 AND total >= 0 AND processed <= total AND attempts >= 0",
            name="ck_import_jobs_progress",
        ),
        Index("ix_import_jobs_queue", "status", "created_at"),
        Index("ix_import_jobs_batch_id", "batch_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    batch_id: Mapped[UUID] = mapped_column(ForeignKey("import_batches.id", ondelete="CASCADE"))
    operation: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), server_default="queued")
    processed: Mapped[int] = mapped_column(Integer, server_default="0")
    total: Mapped[int] = mapped_column(Integer, server_default="0")
    attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    lease_token: Mapped[UUID | None] = mapped_column(Uuid)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    options: Mapped[dict[str, JsonValue]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    error_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ImportRow(Base):
    """Expiring staged content, never logged; removed after commit/rollback/expiry."""

    __tablename__ = "import_rows"
    __table_args__ = (CheckConstraint("row_number > 0", name="ck_import_rows_number"),)
    batch_id: Mapped[UUID] = mapped_column(
        ForeignKey("import_batches.id", ondelete="CASCADE"), primary_key=True
    )
    row_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[dict[str, JsonValue]] = mapped_column(JSONB)
    normalized: Mapped[dict[str, JsonValue] | None] = mapped_column(JSONB)
    geom: Mapped[WKBElement | None] = mapped_column(
        Geometry("GEOMETRY", srid=4326, spatial_index=False)
    )
    valid: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    errors: Mapped[list[dict[str, JsonValue]]] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb")
    )
    warnings: Mapped[list[dict[str, JsonValue]]] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb")
    )


class ImportChange(Base):
    """Persistent undo journal; asset_id intentionally survives deletion of an inserted asset."""

    __tablename__ = "import_changes"
    __table_args__ = (
        CheckConstraint("operation IN ('insert','update')", name="ck_import_changes_operation"),
        CheckConstraint("after_revision > 0", name="ck_import_changes_revision"),
        CheckConstraint(
            "(operation = 'insert' AND before IS NULL) OR "
            "(operation = 'update' AND before IS NOT NULL)",
            name="ck_import_changes_before",
        ),
    )
    batch_id: Mapped[UUID] = mapped_column(ForeignKey("import_batches.id"), primary_key=True)
    asset_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    operation: Mapped[str] = mapped_column(String(16))
    before: Mapped[dict[str, JsonValue] | None] = mapped_column(JSONB(none_as_null=True))
    after_revision: Mapped[int] = mapped_column(BigInteger)
