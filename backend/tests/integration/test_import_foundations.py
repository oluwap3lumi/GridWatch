"""M8 migrated identity, relationships, undo journal and durable private staging."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from alembic.config import Config
from geoalchemy2 import WKTElement
from sqlalchemy import Engine, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from alembic import command
from app.db.models import Asset, ImportBatch, ImportChange, ImportJob, ImportRow
from app.repositories.assets import get_asset
from app.repositories.seed import data_fingerprint


def test_private_batch_staging_jobs_and_journal(session: Session) -> None:
    batch = uuid4()
    session.add(
        ImportBatch(
            id=batch,
            filename="synthetic.csv",
            layer_type="transformer",
            format="csv",
            expires_at=datetime.now(UTC) + timedelta(hours=24),
        )
    )
    session.flush()
    record = session.get(ImportBatch, batch)
    assert record is not None and record.row_counts == {
        "total": 0,
        "valid": 0,
        "invalid": 0,
        "inserted": 0,
        "updated": 0,
    }
    session.add(ImportJob(id=uuid4(), batch_id=batch, operation="inspect"))
    session.add(ImportRow(batch_id=batch, row_number=1, source={"external_id": "T-001"}))
    asset = Asset(
        type="transformer",
        external_id="T-001",
        batch_id=batch,
        geom=WKTElement("POINT(3.3 6.5)", srid=4326),
        revision=1,
    )
    session.add(asset)
    session.flush()
    session.add(
        ImportChange(
            batch_id=batch, asset_id=asset.id, operation="insert", before=None, after_revision=1
        )
    )
    session.flush()
    found = get_asset(session, asset.id)
    assert found is not None and found.properties.install_date is None
    assert found.properties.external_id == "T-001" and found.properties.batch_id == str(batch)
    assert session.scalar(select(ImportJob.status).where(ImportJob.batch_id == batch)) == "queued"
    # Metadata never changes the model's source fingerprint.
    before = data_fingerprint(session)
    asset.last_batch_id = batch
    session.flush()
    assert data_fingerprint(session) == before
    session.refresh(asset)
    assert asset.revision == 2
    session.delete(asset)
    session.flush()
    assert session.get(ImportChange, (batch, asset.id)) is not None


def test_external_identity_is_per_type_and_unique(session: Session) -> None:
    for kind in ("transformer", "pole"):
        session.add(
            Asset(type=kind, external_id="001", geom=WKTElement("POINT(3.3 6.5)", srid=4326))
        )
    session.flush()
    session.add(Asset(type="pole", external_id="001", geom=WKTElement("POINT(3.4 6.5)", srid=4326)))
    with pytest.raises(IntegrityError):
        session.flush()


def test_multipart_feeder_and_optional_relationships(session: Session) -> None:
    feeder = Asset(
        type="feeder",
        geom=WKTElement("MULTILINESTRING((3.3 6.5,3.31 6.51),(3.4 6.5,3.41 6.51))", srid=4326),
    )
    pole = Asset(type="pole", geom=WKTElement("POINT(3.3 6.5)", srid=4326))
    session.add_all([feeder, pole])
    session.flush()
    asset = Asset(
        type="transformer",
        pole_id=pole.id,
        feeder_id=feeder.id,
        geom=WKTElement("POINT(3.3 6.5)", srid=4326),
    )
    session.add(asset)
    session.flush()
    found = get_asset(session, feeder.id)
    assert found is not None and found.geometry.type == "MultiLineString"
    asset.pole_id = feeder.id
    with pytest.raises(IntegrityError):
        session.flush()


def test_generated_ids_do_not_collide_with_seeded_ids(engine: Engine) -> None:
    with engine.begin() as connection:
        next_id = connection.scalar(text("SELECT nextval('asset_id_seq')"))
        highest = connection.scalar(text("SELECT coalesce(max(id),0) FROM assets"))
        assert next_id > highest


def test_downgrade_refuses_to_destroy_import_history(engine: Engine) -> None:
    batch = uuid4()
    with Session(engine) as session, session.begin():
        session.add(
            ImportBatch(
                id=batch,
                filename="synthetic.csv",
                layer_type="transformer",
                expires_at=datetime.now(UTC) + timedelta(hours=24),
            )
        )
    try:
        with pytest.raises(DBAPIError, match="lossless downgrade"):
            command.downgrade(Config("alembic.ini"), "0002")
        with Session(engine) as session:
            assert session.get(ImportBatch, batch) is not None
            assert session.scalar(text("SELECT version_num FROM alembic_version")) == "0004"
    finally:
        with Session(engine) as session, session.begin():
            session.execute(text("DELETE FROM import_batches WHERE id=:id"), {"id": batch})
