"""Single-process durable worker; PostgreSQL row locks fence expired job leases."""

import time
from datetime import UTC, datetime, timedelta
from threading import Event, Thread
from uuid import UUID, uuid4

from geoalchemy2 import WKTElement
from shapely.geometry import shape
from sqlalchemy import Engine, delete, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import get_artifact_root
from app.core.errors import (
    ModelNotFound,
    ModelUnavailable,
    ScoringConflict,
    ScoringDefaultsRequired,
)
from app.db.models import Asset, ImportBatch, ImportJob, ImportRow
from app.repositories.imports import Progress, claim, locked_batch, mutate, rollback
from app.schemas.imports import LayerType, ValidateImport
from app.services.import_parsing import parse_upload
from app.services.import_records import ParseFailure
from app.services.import_validation import column_mapping, issue, suggest_mapping, validate_upload
from app.services.upload_storage import UploadStorage


def process_one(engine: Engine, storage: UploadStorage) -> bool:
    claimed = claim(engine)
    if claimed is None:
        return False
    job_id, token = claimed
    progress, stopped = Progress(), Event()

    def heartbeat() -> None:
        while not stopped.wait(1):
            try:
                with Session(engine) as tracking, tracking.begin():
                    tracking.execute(
                        update(ImportJob)
                        .where(
                            ImportJob.id == job_id,
                            ImportJob.lease_token == token,
                            ImportJob.status == "running",
                        )
                        .values(
                            lease_until=datetime.now(UTC) + timedelta(seconds=120),
                            total=progress.total,
                            processed=progress.processed,
                        )
                    )
            except Exception:
                pass  # Lease expiry and the final token check fence a disconnected worker.

    monitor = Thread(target=heartbeat, daemon=True)
    monitor.start()
    batch_id: UUID | None = None
    try:
        with Session(engine) as session, session.begin():
            job = session.get(ImportJob, job_id)
            assert job is not None
            if job.lease_token != token or job.status != "running":
                return True
            batch_id = job.batch_id
            batch = locked_batch(session, batch_id)
            if job.operation in {
                "inspect",
                "validate",
                "commit",
            } and batch.expires_at <= datetime.now(UTC):
                raise ParseFailure("STAGING_EXPIRED")
            if job.operation in {"inspect", "validate"}:
                parsed = parse_upload(
                    storage.path(batch_id).read_bytes(), batch.filename, storage.settings
                )
                batch.format, batch.detected_columns = parsed.format, list(parsed.columns)
                batch.crs_detected = parsed.crs_detected
                batch.error_report = {"warnings": list(parsed.warnings)}
                session.execute(delete(ImportRow).where(ImportRow.batch_id == batch_id))
                progress.total = len(parsed.rows)
                if job.operation == "inspect":
                    batch.column_mapping = suggest_mapping(parsed.columns)
                    records = [
                        dict(batch_id=batch_id, row_number=row.number, source=row.properties)
                        for row in parsed.rows
                    ]
                    batch.row_counts = dict(
                        total=len(records), valid=0, invalid=0, inserted=0, updated=0
                    )
                else:
                    options = ValidateImport.model_validate(job.options)
                    # The database constraint restricts this to the closed layer vocabulary.
                    from typing import cast

                    layer_value = cast(LayerType, batch.layer_type)
                    poles = frozenset(
                        session.scalars(
                            select(Asset.external_id).where(
                                Asset.type == "pole", Asset.external_id.is_not(None)
                            )
                        )
                    )
                    feeders = frozenset(
                        session.scalars(
                            select(Asset.external_id).where(
                                Asset.type == "feeder", Asset.external_id.is_not(None)
                            )
                        )
                    )
                    rows = validate_upload(
                        parsed,
                        layer_value,
                        options,
                        known_poles=frozenset(x for x in poles if x is not None),
                        known_feeders=frozenset(x for x in feeders if x is not None),
                    )
                    kind = "feeder" if layer_value == "feeder_line" else layer_value
                    existing_dates = {
                        external: (installed, maintained)
                        for external, installed, maintained in session.execute(
                            select(
                                Asset.external_id, Asset.install_date, Asset.last_maintenance_date
                            ).where(Asset.type == kind, Asset.external_id.is_not(None))
                        )
                    }
                    for row in rows:
                        prior = existing_dates.get(str(row.attributes.get("external_id")))
                        if prior and row.valid:
                            installed = row.attributes.get("install_date") or (
                                prior[0].isoformat() if prior[0] else None
                            )
                            maintained = row.attributes.get("last_maintenance_date") or (
                                prior[1].isoformat() if prior[1] else None
                            )
                            if (
                                isinstance(installed, str)
                                and isinstance(maintained, str)
                                and installed > maintained
                            ):
                                issue(row, "last_maintenance_date", "DATE_ORDER")
                    records = [
                        dict(
                            batch_id=batch_id,
                            row_number=row.number,
                            source=source.properties,
                            normalized=row.attributes,
                            geom=WKTElement(shape(row.geometry.model_dump()).wkt, srid=4326)
                            if row.geometry
                            else None,
                            valid=row.valid,
                            errors=[issue.model_dump(mode="json") for issue in row.errors],
                            warnings=[issue.model_dump(mode="json") for issue in row.warnings],
                        )
                        for source, row in zip(parsed.rows, rows, strict=True)
                    ]
                    batch.column_mapping = column_mapping(parsed.columns, options.column_mapping)
                    batch.crs_selected = options.source_crs
                    batch.row_counts = dict(
                        total=len(rows),
                        valid=sum(row.valid for row in rows),
                        invalid=sum(not row.valid for row in rows),
                        inserted=0,
                        updated=0,
                    )
                    batch.error_report = {
                        "warnings": list(parsed.warnings),
                        "errors": [
                            issue.model_dump(mode="json") for row in rows for issue in row.errors
                        ],
                    }
                    batch.status = "validated"
                for start in range(0, len(records), 1000):
                    session.execute(insert(ImportRow), records[start : start + 1000])
                    progress.processed = min(start + 1000, progress.total)
            elif job.operation == "commit":
                count = batch.row_counts.get("valid")
                progress.total = count if isinstance(count, int) else 0
                if not progress.total:
                    raise ParseFailure("NO_VALID_ROWS")
                mutate(session, batch, progress)
            elif job.operation == "rollback":
                rollback(session, batch)
            elif job.operation == "rescore":
                from app.services.scoring import rescore

                # Its own asset/scoring transactions; failure preserves the imported batch.
                rescore(
                    engine,
                    get_artifact_root(),
                    accept_scoring_defaults=job.options.get("accept_scoring_defaults") is True,
                )
            stopped.set()
            monitor.join()
            session.refresh(job, with_for_update=True)
            if job.lease_token != token or job.status != "running":
                raise ParseFailure("LEASE_LOST")
            job.processed, job.total = progress.processed, progress.total
            job.status, job.completed_at = "completed", datetime.now(UTC)
            batch.error_report = {
                key: value for key, value in batch.error_report.items() if key != "code"
            }
            job.lease_until = None
            if job.operation == "commit" and job.options.get("rescore"):
                session.add(
                    ImportJob(
                        id=uuid4(),
                        batch_id=batch_id,
                        operation="rescore",
                        options={
                            "accept_scoring_defaults": job.options.get(
                                "accept_scoring_defaults", False
                            )
                        },
                    )
                )
        if batch_id is not None:
            with Session(engine) as session:
                completed_batch = session.get(ImportBatch, batch_id)
                if completed_batch and completed_batch.status in {"imported", "rolled_back"}:
                    storage.delete(batch_id)
    except Exception as error:
        stopped.set()
        monitor.join()
        code = (
            error.code
            if isinstance(error, ParseFailure)
            else {
                ModelNotFound: "MODEL_NOT_FOUND",
                ModelUnavailable: "MODEL_UNAVAILABLE",
                ScoringConflict: "SCORING_CONFLICT",
                ScoringDefaultsRequired: "SCORING_DEFAULTS_REQUIRED",
                IntegrityError: "IMPORT_CONSTRAINT",
            }.get(type(error), "IMPORT_FAILED")
        )
        with Session(engine) as session, session.begin():
            job = session.get(ImportJob, job_id, with_for_update=True)
            if job is not None and job.lease_token == token and job.status == "running":
                job.status, job.error_code, job.completed_at = "failed", code, datetime.now(UTC)
                batch = locked_batch(session, job.batch_id)
                if job.operation in {"inspect", "validate", "commit"}:
                    batch.status = "failed"
                batch.error_report = {**batch.error_report, "code": code}
        # Never log exception text, arguments, filenames, SQL or source content.
    finally:
        stopped.set()
        monitor.join()
    return True


def cleanup(engine: Engine, storage: UploadStorage) -> None:
    """Retry terminal-file deletion and expire staging without deleting undo history."""
    with Session(engine) as session, session.begin():
        batches = session.scalars(
            select(ImportBatch)
            .where(
                (ImportBatch.expires_at < datetime.now(UTC))
                | ImportBatch.status.in_(["imported", "rolled_back"])
            )
            .with_for_update(skip_locked=True)
        ).all()
        for batch in batches:
            active = session.scalar(
                select(ImportJob).where(
                    ImportJob.batch_id == batch.id, ImportJob.status.in_(["running", "queued"])
                )
            )
            if active is not None:
                continue
            storage.delete(batch.id)
            session.execute(delete(ImportRow).where(ImportRow.batch_id == batch.id))
            if batch.status not in {"imported", "rolled_back"}:
                batch.status = "failed"
                batch.error_report = {**batch.error_report, "code": "STAGING_EXPIRED"}
        # UUID-only orphan files can remain if the API dies before batch creation.
        if storage.root.exists():
            for path in storage.root.glob("*.upload"):
                try:
                    identifier = UUID(hex=path.stem)
                except ValueError:
                    continue
                if (
                    path.is_symlink()
                    or time.time() - path.stat().st_mtime < storage.settings.ttl_seconds
                ):
                    continue
                if session.get(ImportBatch, identifier) is None:
                    storage.delete(identifier)
