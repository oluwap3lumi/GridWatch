"""Typed SQLAlchemy models for the build-plan schema; Alembic owns all DDL."""

from datetime import date, datetime

from geoalchemy2 import Geometry, WKBElement
from sqlalchemy import BigInteger, CheckConstraint, DateTime, Float, ForeignKey, Index, String
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
            "(type = 'feeder' AND GeometryType(geom) = 'LINESTRING' AND feeder_id IS NULL) OR "
            "(type IN ('transformer', 'pole') AND GeometryType(geom) = 'POINT' "
            "AND feeder_id IS NOT NULL)",
            name="ck_assets_geometry_and_parent",
        ),
        Index("ix_assets_geom", "geom", postgresql_using="gist"),
        Index("ix_assets_type", "type"),
        Index("ix_assets_feeder_id", "feeder_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    type: Mapped[str] = mapped_column(String(20))
    feeder_id: Mapped[int | None] = mapped_column(ForeignKey("assets.id"))
    geom: Mapped[WKBElement] = mapped_column(Geometry("GEOMETRY", srid=4326, spatial_index=False))
    install_date: Mapped[date]
    capacity_kva: Mapped[float] = mapped_column(Float)
    load_factor: Mapped[float] = mapped_column(Float)
    material: Mapped[str] = mapped_column(String(30))
    vegetation_index: Mapped[float] = mapped_column(Float)
    last_maintenance_date: Mapped[date]


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
