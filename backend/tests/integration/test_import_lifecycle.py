"""Synthetic imports through the HTTP handlers and real PostGIS worker transactions."""

import asyncio
import io
import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from fastapi import HTTPException, UploadFile
from pyproj import CRS
from sqlalchemy import Engine, delete, func, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_engine
from app.api.v1.imports import commit, errors_csv, undo, upload, validate
from app.core.uploads import UploadSettings
from app.db.models import Asset, ImportBatch, ImportChange, ImportJob, ImportRow
from app.main import app
from app.repositories.import_jobs import cleanup, process_one
from app.repositories.imports import claim, detail
from app.schemas.imports import CommitImport, ValidateImport
from app.services.upload_storage import UploadStorage
from tests.unit.test_import_parsing import packed, shape_members


@pytest.fixture
def storage(
    engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[UploadStorage]:
    monkeypatch.setenv("UPLOAD_STAGING_DIR", str(tmp_path))
    yield UploadStorage(UploadSettings.from_env())
    with Session(engine) as session, session.begin():
        session.execute(delete(Asset).where(Asset.batch_id.is_not(None)))
        for model in (ImportChange, ImportRow, ImportJob, ImportBatch):
            session.execute(delete(model))


def start(
    engine: Engine, storage: UploadStorage, data: bytes, filename="assets.csv", layer="transformer"
) -> UUID:
    with Session(engine) as session:
        before = session.scalar(select(func.count()).select_from(Asset))
    batch = upload(engine, UploadFile(io.BytesIO(data), filename=filename), layer)
    assert batch.job.status == "queued"
    assert process_one(engine, storage)
    with Session(engine) as session:
        assert detail(session, batch.id).job.status == "completed"
    validate(batch.id, engine, ValidateImport())
    assert process_one(engine, storage)
    with Session(engine) as session:
        assert detail(session, batch.id).status == "validated"
        assert session.scalar(select(func.count()).select_from(Asset)) == before
    return batch.id


CSV = b"external_id,latitude,longitude,capacity_kva,install_date\n001,6.5,3.3,250,2020-01-02\n"


def test_upsert_reverse_rollback_and_staging_removal(
    engine: Engine, storage: UploadStorage
) -> None:
    first = start(engine, storage, CSV)
    commit(first, engine, CommitImport())
    process_one(engine, storage)
    assert not storage.path(first).exists()
    second = start(engine, storage, CSV.replace(b"250", b"500"))
    commit(second, engine, CommitImport())
    process_one(engine, storage)
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Asset)) == 1
        assert session.scalar(select(Asset.capacity_kva)) == 500
        assert detail(session, second).row_counts.updated == 1
        assert session.scalar(select(func.count()).select_from(ImportRow)) == 0
    with pytest.raises(HTTPException) as caught:
        undo(first, engine)
    assert caught.value.status_code == 409
    with Session(engine) as session:
        assert session.scalar(select(Asset.capacity_kva)) == 500
    undo(second, engine)
    process_one(engine, storage)
    with Session(engine) as session:
        assert detail(session, second).status == "rolled_back", detail(
            session, second
        ).job.error_code
        assert session.scalar(select(Asset.capacity_kva)) == 250
    undo(first, engine)
    process_one(engine, storage)
    with Session(engine) as session:
        assert detail(session, first).status == "rolled_back"
        assert session.scalar(select(func.count()).select_from(Asset)) == 0


@pytest.mark.parametrize("format", ["json", "geojson", "zip", "multiline"])
def test_all_formats(engine: Engine, storage: UploadStorage, format: str) -> None:
    layer = "pole"
    if format in {"zip", "multiline"}:
        layer = "feeder_line" if format == "multiline" else "pole"
        data = packed(
            shape_members(prj=CRS.from_epsg(32631).to_wkt().encode(), lines=format == "multiline")
        )
        filename = "network.zip"
    elif format == "json":
        layer, filename = "transformer", "records.json"
        data = b'[{"external_id":"001","lat":6.5,"lon":3.3}]'
    else:
        filename = "points.geojson"
        data = json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"external_id": "001"},
                        "geometry": {"type": "Point", "coordinates": [3.3, 6.5]},
                    }
                ],
            }
        ).encode()
    identifier = start(engine, storage, data, filename, layer)
    commit(identifier, engine, CommitImport())
    process_one(engine, storage)
    with Session(engine) as session:
        result = detail(session, identifier)
        assert result.status == "imported", result.job.error_code
        assert result.row_counts.inserted == 1
        assert result.extent is not None
    undo(identifier, engine)
    process_one(engine, storage)
    with Session(engine) as session:
        assert detail(session, identifier).status == "rolled_back"


def test_partial_errors_and_rescore_failure_preserves_import(
    engine: Engine, storage: UploadStorage
) -> None:
    identifier = start(engine, storage, CSV + b"bad,0,0,250,nonsense\n")
    from app.api.v1.imports import get_import, list_imports

    with Session(engine) as session:
        lightweight = get_import(identifier, session, include_errors=False)
        assert not lightweight.errors and lightweight.row_counts.invalid == 1
        assert lightweight.preview[1].errors
        page = list_imports(session, 20, 0)
        assert page.total == 1 and not page.items[0].errors and not page.items[0].preview
        assert get_import(identifier, session).errors
        assert "row_number,field,reason" in bytes(errors_csv(identifier, session).body).decode()
    with pytest.raises(HTTPException) as caught:
        commit(identifier, engine, CommitImport())
    assert caught.value.status_code == 409
    commit(identifier, engine, CommitImport(valid_rows_only=True, rescore=True))
    process_one(engine, storage)
    process_one(engine, storage)
    with Session(engine) as session:
        result = detail(session, identifier)
        assert result.status == "imported" and result.row_counts.invalid == 1
        assert result.job.status == "failed"  # No trained model in this isolated test DB.
        report = bytes(errors_csv(identifier, session).body).decode()
        assert "row_number,field,reason" in report and "nonsense" not in report
        assert session.scalar(select(func.count()).select_from(Asset)) == 1


def test_expiry_and_abandoned_lease_recovery(engine: Engine, storage: UploadStorage) -> None:
    batch = upload(engine, UploadFile(io.BytesIO(CSV), filename="a.csv"), "transformer")
    abandoned = claim(engine)
    assert abandoned
    with Session(engine) as session, session.begin():
        session.get(ImportJob, abandoned[0]).lease_until = datetime.now(UTC) - timedelta(seconds=1)
    process_one(engine, storage)
    with Session(engine) as session, session.begin():
        assert detail(session, batch.id).job.status == "completed"
        session.get(ImportBatch, batch.id).expires_at = datetime.now(UTC) - timedelta(seconds=1)
    cleanup(engine, storage)
    assert not storage.path(batch.id).exists()
    with Session(engine) as session:
        assert detail(session, batch.id).error_code == "STAGING_EXPIRED"
        assert not detail(session, batch.id).preview


def test_upload_limit_and_bad_file(
    engine: Engine, storage: UploadStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("UPLOAD_MAX_BYTES", "8")
    with pytest.raises(HTTPException) as caught:
        upload(engine, UploadFile(io.BytesIO(CSV), filename="a.csv"), "transformer")
    assert caught.value.status_code == 413
    assert not list(storage.root.glob("*.upload"))
    monkeypatch.delenv("UPLOAD_MAX_BYTES")
    batch = upload(engine, UploadFile(io.BytesIO(b"broken"), filename="a.zip"), "pole")
    process_one(engine, storage)
    with Session(engine) as session:
        assert detail(session, batch.id).status == "failed"
        assert "file" in bytes(errors_csv(batch.id, session).body).decode()


def test_multipart_http_flow(engine: Engine, storage: UploadStorage) -> None:
    messages = []
    body = (
        b'--boundary\r\nContent-Disposition: form-data; name="layer_type"\r\n\r\ntransformer\r\n'
        b'--boundary\r\nContent-Disposition: form-data; name="file"; '
        b'filename="../synthetic.csv"\r\n'
        b"Content-Type: application/octet-stream\r\n\r\n" + CSV + b"\r\n--boundary--\r\n"
    )

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        messages.append(message)

    app.dependency_overrides[get_engine] = lambda: engine
    try:
        asyncio.run(
            app(
                {
                    "type": "http",
                    "asgi": {"version": "3.0"},
                    "http_version": "1.1",
                    "method": "POST",
                    "scheme": "http",
                    "path": "/api/v1/imports",
                    "raw_path": b"/api/v1/imports",
                    "root_path": "",
                    "query_string": b"",
                    "headers": [(b"content-type", b"multipart/form-data; boundary=boundary")],
                    "client": ("127.0.0.1", 1234),
                    "server": ("localhost", 8000),
                },
                receive,
                send,
            )
        )
    finally:
        app.dependency_overrides.clear()
    assert messages[0]["status"] == 202
    payload = json.loads(
        b"".join(
            message.get("body", b"")
            for message in messages
            if message["type"] == "http.response.body"
        )
    )
    assert payload["filename"] == "synthetic.csv" and payload["job"]["status"] == "queued"
    process_one(engine, storage)
    with Session(engine) as session:
        assert detail(session, UUID(payload["id"])).format == "csv"


def test_late_parent_resolution_is_undoable(engine: Engine, storage: UploadStorage) -> None:
    child = start(engine, storage, b"external_id,lat,lon,pole_id,feeder_id\nT,6.5,3.3,P,F\n")
    commit(child, engine, CommitImport())
    process_one(engine, storage)
    pole = start(engine, storage, b"external_id,lat,lon\nP,6.5,3.3\n", layer="pole")
    commit(pole, engine, CommitImport())
    process_one(engine, storage)
    feeder = start(
        engine,
        storage,
        b'[{"external_id":"F","geometry":"LINESTRING(3.3 6.5,3.4 6.6)"}]',
        "line.json",
        "feeder_line",
    )
    commit(feeder, engine, CommitImport())
    process_one(engine, storage)
    with Session(engine) as session:
        transformer = session.scalar(select(Asset).where(Asset.type == "transformer"))
        assert transformer.pole_id is not None and transformer.feeder_id is not None
    with pytest.raises(HTTPException):
        undo(pole, engine)
    for identifier in (feeder, pole, child):
        undo(identifier, engine)
        process_one(engine, storage)
        with Session(engine) as session:
            assert detail(session, identifier).status == "rolled_back"


def test_batched_insert_and_upsert(engine: Engine, storage: UploadStorage) -> None:
    data = b"external_id,lat,lon\n" + b"".join(
        f"T-{index},6.5,3.3\n".encode() for index in range(1001)
    )
    first = start(engine, storage, data)
    commit(first, engine, CommitImport())
    process_one(engine, storage)
    second = start(engine, storage, data)
    commit(second, engine, CommitImport())
    process_one(engine, storage)
    with Session(engine) as session:
        result = detail(session, second)
        assert result.row_counts.updated == 1001 and result.row_counts.inserted == 0
        assert result.job.processed == result.job.total == 1001
        assert session.scalar(select(func.count()).select_from(Asset)) == 1001


def test_lost_lease_fences_all_asset_writes(
    engine: Engine, storage: UploadStorage, monkeypatch
) -> None:
    from uuid import uuid4

    from app.repositories import import_jobs

    real_mutate = import_jobs.mutate
    identifier = start(engine, storage, CSV)
    queued = commit(identifier, engine, CommitImport())

    def lose_lease(session, batch, progress):
        real_mutate(session, batch, progress)
        with Session(engine) as other, other.begin():
            job = other.get(ImportJob, queued.job.id)
            job.lease_token = uuid4()
            job.lease_until = datetime.now(UTC) - timedelta(seconds=1)

    monkeypatch.setattr(import_jobs, "mutate", lose_lease)
    process_one(engine, storage)
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Asset)) == 0
        assert detail(session, identifier).status == "validated"
    monkeypatch.setattr(import_jobs, "mutate", real_mutate)
    process_one(engine, storage)
    with Session(engine) as session:
        assert detail(session, identifier).status == "imported"


def test_database_failure_keeps_entire_batch_atomic(engine: Engine, storage: UploadStorage) -> None:
    first = start(
        engine,
        storage,
        b"external_id,lat,lon,install_date,last_maintenance_date\n001,6.5,3.3,2020-01-01,2023-01-01\n",
    )
    commit(first, engine, CommitImport())
    process_one(engine, storage)
    # Row-alone dates pass; merging this with retained maintenance would break the
    # database date constraint. Even the preceding new asset must not be inserted.
    second = start(
        engine,
        storage,
        b"external_id,lat,lon,install_date\n002,6.5,3.3,2020-01-01\n001,6.5,3.3,2022-01-01\n",
    )
    from datetime import date

    with Session(engine) as session, session.begin():
        session.scalar(select(Asset)).last_maintenance_date = date(2021, 1, 1)
    commit(second, engine, CommitImport())
    process_one(engine, storage)
    with Session(engine) as session:
        assert detail(session, second).job.status == "failed"
        assert session.scalar(select(func.count()).select_from(Asset)) == 1
        assert str(session.scalar(select(Asset.install_date))) == "2020-01-01"


def test_feature_limit_rejects_before_asset_writes(
    engine: Engine, storage: UploadStorage, monkeypatch
) -> None:
    monkeypatch.setenv("UPLOAD_MAX_FEATURES", "1")
    data = CSV + b"002,6.5,3.3,250,2020-01-02\n"
    batch = upload(engine, UploadFile(io.BytesIO(data), filename="a.csv"), "transformer")
    process_one(engine, UploadStorage(UploadSettings.from_env()))
    with Session(engine) as session:
        result = detail(session, batch.id)
        assert result.status == "failed" and result.job.error_code == "FEATURE_LIMIT"
        assert session.scalar(select(func.count()).select_from(Asset)) == 0
