"""Create the five build-plan tables, feeder linkage, and spatial indexes."""

import sqlalchemy as sa
from geoalchemy2 import Geometry

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Install PostGIS and the initial schema transactionally."""
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.create_table(
        "assets",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("feeder_id", sa.BigInteger(), sa.ForeignKey("assets.id")),
        sa.Column("geom", Geometry("GEOMETRY", srid=4326, spatial_index=False), nullable=False),
        sa.Column("install_date", sa.Date(), nullable=False),
        sa.Column("capacity_kva", sa.Float(), nullable=False),
        sa.Column("load_factor", sa.Float(), nullable=False),
        sa.Column("material", sa.String(30), nullable=False),
        sa.Column("vegetation_index", sa.Float(), nullable=False),
        sa.Column("last_maintenance_date", sa.Date(), nullable=False),
        sa.CheckConstraint("type IN ('transformer', 'feeder', 'pole')", name="ck_assets_type"),
        sa.CheckConstraint(
            "capacity_kva >= 0 AND capacity_kva < 1000000", name="ck_assets_capacity"
        ),
        sa.CheckConstraint("load_factor >= 0 AND load_factor <= 2", name="ck_assets_load"),
        sa.CheckConstraint(
            "vegetation_index >= 0 AND vegetation_index <= 1", name="ck_assets_vegetation"
        ),
        sa.CheckConstraint("last_maintenance_date >= install_date", name="ck_assets_maintenance"),
        sa.CheckConstraint(
            "ST_IsValid(geom) AND NOT ST_IsEmpty(geom)", name="ck_assets_valid_geom"
        ),
        sa.CheckConstraint(
            "(type = 'feeder' AND GeometryType(geom) = 'LINESTRING' AND feeder_id IS NULL) OR "
            "(type IN ('transformer', 'pole') AND GeometryType(geom) = 'POINT' "
            "AND feeder_id IS NOT NULL)",
            name="ck_assets_geometry_and_parent",
        ),
    )
    op.create_index("ix_assets_geom", "assets", ["geom"], postgresql_using="gist")
    op.create_index("ix_assets_type", "assets", ["type"])
    op.create_index("ix_assets_feeder_id", "assets", ["feeder_id"])
    op.execute("""
        CREATE FUNCTION guard_asset_feeder() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.feeder_id IS NOT NULL THEN
                PERFORM id FROM assets WHERE id = NEW.feeder_id AND type = 'feeder' FOR SHARE;
                IF NOT FOUND THEN
                    RAISE EXCEPTION 'feeder_id must reference a feeder' USING ERRCODE = '23514';
                END IF;
            END IF;
            IF TG_OP = 'UPDATE' AND OLD.type = 'feeder' AND NEW.type <> 'feeder'
                AND EXISTS (SELECT 1 FROM assets WHERE feeder_id = OLD.id) THEN
                RAISE EXCEPTION 'cannot change the type of a referenced feeder'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END $$
    """)
    op.execute("""
        CREATE TRIGGER assets_feeder_guard BEFORE INSERT OR UPDATE OF type, feeder_id
        ON assets FOR EACH ROW EXECUTE FUNCTION guard_asset_feeder()
    """)
    op.create_table(
        "outage_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("asset_id", sa.BigInteger(), sa.ForeignKey("assets.id"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_min", sa.Float(), nullable=False),
        sa.Column("cause", sa.String(40), nullable=False),
        sa.Column("geom", Geometry("POINT", srid=4326, spatial_index=False), nullable=False),
        sa.CheckConstraint(
            "duration_min > 0 AND duration_min < 100000", name="ck_outages_duration"
        ),
        sa.CheckConstraint(
            "ST_IsValid(geom) AND NOT ST_IsEmpty(geom)", name="ck_outages_valid_geom"
        ),
    )
    op.create_index("ix_outages_geom", "outage_events", ["geom"], postgresql_using="gist")
    op.create_index("ix_outages_asset_time", "outage_events", ["asset_id", "started_at"])
    op.create_table(
        "weather_obs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("geom", Geometry("POINT", srid=4326, spatial_index=False), nullable=False),
        sa.Column("rainfall_mm", sa.Float(), nullable=False),
        sa.Column("wind_kph", sa.Float(), nullable=False),
        sa.Column("temp_c", sa.Float(), nullable=False),
        sa.Column("lightning_density", sa.Float(), nullable=False),
        sa.CheckConstraint("rainfall_mm >= 0 AND rainfall_mm <= 1000", name="ck_weather_rain"),
        sa.CheckConstraint("wind_kph >= 0 AND wind_kph <= 500", name="ck_weather_wind"),
        sa.CheckConstraint("temp_c >= -60 AND temp_c <= 65", name="ck_weather_temp"),
        sa.CheckConstraint(
            "lightning_density >= 0 AND lightning_density <= 10000", name="ck_weather_lightning"
        ),
        sa.CheckConstraint(
            "ST_IsValid(geom) AND NOT ST_IsEmpty(geom)", name="ck_weather_valid_geom"
        ),
    )
    op.create_index("ix_weather_geom", "weather_obs", ["geom"], postgresql_using="gist")
    op.create_index("ix_weather_time", "weather_obs", ["observed_at"])
    op.create_table(
        "model_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("model_version", sa.String(64), nullable=False, unique=True),
        sa.Column("trained_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data_hash", sa.String(64), nullable=False),
        sa.Column("features", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column("metrics", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column("git_sha", sa.String(64), nullable=False),
        sa.CheckConstraint("data_hash ~ '^[0-9a-f]{64}$'", name="ck_model_runs_data_hash"),
    )
    op.create_index("ix_model_runs_trained_at", "model_runs", ["trained_at"])
    op.create_table(
        "risk_scores",
        sa.Column("asset_id", sa.BigInteger(), sa.ForeignKey("assets.id"), primary_key=True),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("band", sa.String(10), nullable=False),
        sa.Column(
            "model_version",
            sa.String(64),
            sa.ForeignKey("model_runs.model_version"),
            nullable=False,
        ),
        sa.Column("scored_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("top_factors", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.CheckConstraint("score >= 0 AND score <= 1", name="ck_risk_scores_score"),
        sa.CheckConstraint(
            "band IN ('low', 'medium', 'high', 'critical')", name="ck_risk_scores_band"
        ),
    )
    op.create_index("ix_risk_scores_band", "risk_scores", ["band"])


def downgrade() -> None:
    """Remove application tables while preserving the shared PostGIS extension."""
    for table in ("risk_scores", "model_runs", "weather_obs", "outage_events", "assets"):
        op.drop_table(table)
    op.execute("DROP FUNCTION guard_asset_feeder()")
