"""Validate migrated schema, spatial indexes, constraints, and reversible DDL."""

from datetime import UTC, date, datetime

import pytest
from alembic.config import Config
from geoalchemy2 import WKTElement
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from alembic import command
from app.db.models import Asset, OutageEvent


def add_feeder(session: Session) -> None:
    session.add(
        Asset(
            id=1,
            type="feeder",
            feeder_id=None,
            geom=WKTElement("LINESTRING(3.3 6.5,3.31 6.51)", srid=4326),
            install_date=date(2000, 1, 1),
            capacity_kva=20000,
            load_factor=0.9,
            material="aluminium",
            vegetation_index=0.5,
            last_maintenance_date=date(2024, 1, 1),
        )
    )
    session.flush()


def transformer(asset_id: int = 2, feeder_id: int = 1) -> Asset:
    return Asset(
        id=asset_id,
        type="transformer",
        feeder_id=feeder_id,
        geom=WKTElement("POINT(3.305 6.505)", srid=4326),
        install_date=date(2005, 1, 1),
        capacity_kva=500,
        load_factor=1.1,
        material="steel",
        vegetation_index=0.7,
        last_maintenance_date=date(2024, 1, 1),
    )


def test_schema_and_spatial_indexes(engine: Engine) -> None:
    assert set(inspect(engine).get_table_names()) >= {
        "assets",
        "outage_events",
        "weather_obs",
        "risk_scores",
        "model_runs",
        "alembic_version",
    }
    with engine.connect() as connection:
        version = connection.scalar(text("SELECT version_num FROM alembic_version"))
        assert version == "0001"
        indexes = connection.execute(
            text("SELECT tablename, indexdef FROM pg_indexes WHERE schemaname = 'public'")
        ).all()
        for table in ("assets", "outage_events", "weather_obs"):
            assert any(
                name == table and "USING gist (geom)" in definition for name, definition in indexes
            )


def test_geometry_roundtrip_and_meter_query(session: Session) -> None:
    add_feeder(session)
    session.add(transformer())
    session.flush()
    row = session.execute(
        text("SELECT ST_SRID(geom), ST_IsValid(geom), GeometryType(geom) FROM assets WHERE id=2")
    ).one()
    assert tuple(row) == (4326, True, "POINT")
    assert (
        session.scalar(
            text(
                "SELECT count(*) FROM assets WHERE ST_DWithin(geom::geography, "
                "ST_SetSRID(ST_MakePoint(3.305,6.505),4326)::geography, 1)"
            )
        )
        == 2
    )


@pytest.mark.parametrize("kind", ["wrong_parent", "wrong_geometry", "wrong_srid", "invalid_load"])
def test_invalid_assets_are_rejected(session: Session, kind: str) -> None:
    add_feeder(session)
    session.add(transformer())
    session.flush()
    invalid = transformer(3)
    if kind == "wrong_parent":
        invalid.feeder_id = 2
    elif kind == "wrong_geometry":
        invalid.geom = WKTElement("LINESTRING(3.3 6.5,3.31 6.51)", srid=4326)
    elif kind == "wrong_srid":
        invalid.geom = WKTElement("POINT(3.305 6.505)", srid=3857)
    else:
        invalid.load_factor = -0.1
    session.add(invalid)
    # Wrong SRID is a PostGIS data error; all are SQLAlchemy DBAPI errors.
    from sqlalchemy.exc import DBAPIError

    with pytest.raises(DBAPIError):
        session.flush()


def test_missing_asset_foreign_key_is_rejected(session: Session) -> None:
    session.add(
        OutageEvent(
            id=1,
            asset_id=999,
            started_at=datetime(2025, 1, 1, tzinfo=UTC),
            duration_min=30,
            cause="storm",
            geom=WKTElement("POINT(3.3 6.5)", srid=4326),
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()


def test_migration_downgrade_and_upgrade(engine: Engine) -> None:
    config = Config("alembic.ini")
    command.downgrade(config, "base")
    assert "assets" not in inspect(engine).get_table_names()
    command.upgrade(config, "head")
    assert "risk_scores" in inspect(engine).get_table_names()
    command.check(config)
