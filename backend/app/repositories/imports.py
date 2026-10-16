"""Private import persistence, transactional mutations and a fenced PostgreSQL queue."""

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

from pydantic import JsonValue
from sqlalchemy import Engine, delete, func, insert, or_, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.db.models import (
    Asset,
    ImportBatch,
    ImportChange,
    ImportJob,
    ImportRow,
    OutageEvent,
    RiskScore,
)
from app.schemas.imports import ImportBatchDetail, ImportHistory, JobProgress, PreviewRow
from app.services.import_records import ParseFailure

CORPUS_LOCK = 5139241308840342595


@dataclass
class Progress:
    total: int = 0
    processed: int = 0


def create_batch(
    engine: Engine, identifier: UUID, filename: str, layer: str, ttl: int
) -> ImportBatchDetail:
    with Session(engine) as session, session.begin():
        session.add(
            ImportBatch(
                id=identifier,
                filename=filename,
                layer_type=layer,
                expires_at=datetime.now(UTC) + timedelta(seconds=ttl),
            )
        )
        session.flush()
        enqueue(session, identifier, "inspect", {})
        return detail(session, identifier)


def schedule_job(
    engine: Engine, batch_id: UUID, operation: str, options: dict[str, JsonValue]
) -> ImportBatchDetail:
    with Session(engine) as session, session.begin():
        enqueue(session, batch_id, operation, options)
        return detail(session, batch_id)


def locked_batch(session: Session, batch_id: UUID) -> ImportBatch:
    batch = session.scalar(select(ImportBatch).where(ImportBatch.id == batch_id).with_for_update())
    if batch is None:
        raise ParseFailure("BATCH_NOT_FOUND")
    return batch


def enqueue(
    session: Session, batch_id: UUID, operation: str, options: dict[str, JsonValue]
) -> ImportJob:
    batch = locked_batch(session, batch_id)
    active = session.scalar(
        select(ImportJob).where(
            ImportJob.batch_id == batch_id, ImportJob.status.in_(["queued", "running"])
        )
    )
    if active is not None:
        raise ParseFailure("JOB_IN_PROGRESS")
    if operation in {"inspect", "validate", "commit"} and batch.expires_at <= datetime.now(UTC):
        raise ParseFailure("STAGING_EXPIRED")
    allowed = {
        "inspect": {"uploaded"},
        "validate": {"uploaded", "validated", "failed"},
        "commit": {"validated"},
        "rollback": {"imported"},
        "rescore": {"imported"},
    }
    if batch.status not in allowed[operation]:
        raise ParseFailure("INVALID_BATCH_STATE")
    if operation == "rollback":
        check_rollback(session, batch)
    if (
        operation == "commit"
        and batch.row_counts.get("invalid")
        and not options.get("valid_rows_only")
    ):
        raise ParseFailure("PARTIAL_IMPORT_REQUIRES_CONSENT")
    job = ImportJob(id=uuid4(), batch_id=batch_id, operation=operation, options=options)
    session.add(job)
    session.flush()
    return job


def detail(
    session: Session, batch_id: UUID, *, include_errors: bool = True, include_preview: bool = True
) -> ImportBatchDetail:
    batch = session.get(ImportBatch, batch_id)
    if batch is None:
        raise ParseFailure("BATCH_NOT_FOUND")
    job = session.scalar(
        select(ImportJob)
        .where(ImportJob.batch_id == batch_id)
        .order_by(ImportJob.created_at.desc(), ImportJob.id.desc())
        .limit(1)
    )
    preview = []
    staged = (
        session.scalars(
            select(ImportRow)
            .where(ImportRow.batch_id == batch_id)
            .order_by(ImportRow.row_number)
            .limit(20)
        )
        if include_preview
        else ()
    )
    for row in staged:
        geometry = (
            json.loads(session.scalar(select(func.ST_AsGeoJSON(row.geom))) or "null")
            if row.geom is not None
            else None
        )
        preview.append(
            PreviewRow.model_validate(
                dict(
                    row_number=row.row_number,
                    properties=row.source,
                    geometry=geometry,
                    errors=row.errors,
                    warnings=row.warnings,
                )
            )
        )
    return ImportBatchDetail.model_validate(
        dict(
            id=batch.id,
            filename=batch.filename,
            format=batch.format,
            layer_type=batch.layer_type,
            status=batch.status,
            row_counts=batch.row_counts,
            detected_columns=batch.detected_columns,
            column_mapping=batch.column_mapping,
            crs_detected=batch.crs_detected,
            crs_selected=batch.crs_selected,
            created_at=batch.created_at,
            completed_at=batch.completed_at,
            expires_at=batch.expires_at,
            preview=preview,
            errors=batch.error_report.get("errors", []) if include_errors else [],
            extent=batch.error_report.get("extent"),
            error_code=batch.error_report.get("code"),
            warnings=batch.error_report.get("warnings", []),
            job=JobProgress.model_validate(
                dict(
                    id=job.id,
                    operation=job.operation,
                    status=job.status,
                    processed=job.processed,
                    total=job.total,
                    error_code=job.error_code,
                )
            )
            if job
            else None,
        )
    )


def history(session: Session, limit: int, offset: int) -> ImportHistory:
    ids = session.scalars(
        select(ImportBatch.id)
        .order_by(ImportBatch.created_at.desc(), ImportBatch.id)
        .limit(limit)
        .offset(offset)
    )
    return ImportHistory(
        items=[
            detail(session, value, include_errors=False, include_preview=False) for value in ids
        ],
        total=session.scalar(select(func.count()).select_from(ImportBatch)) or 0,
    )


def claim(engine: Engine) -> tuple[UUID, UUID] | None:
    with Session(engine) as session, session.begin():
        now = datetime.now(UTC)
        job = session.scalar(
            select(ImportJob)
            .where(
                or_(
                    ImportJob.status == "queued",
                    (ImportJob.status == "running") & (ImportJob.lease_until < now),
                )
            )
            .order_by(ImportJob.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if job is None:
            return None
        token = uuid4()
        job.status, job.lease_token = "running", token
        job.lease_until = now + timedelta(seconds=120)
        job.attempts += 1
        return job.id, token


def snapshot(session: Session, asset_id: int) -> dict[str, JsonValue]:
    # Explicit EWKB avoids the PostGIS JSON geometry cast and permits lossless undo.
    value: dict[str, JsonValue] = session.execute(
        text(
            "SELECT to_jsonb(a) || jsonb_build_object('geom', "
            "encode(ST_AsEWKB(a.geom),'hex')) FROM assets a WHERE id=:id"
        ),
        {"id": asset_id},
    ).scalar_one()
    return value


def journal(
    session: Session, batch_id: UUID, asset: Asset, before: dict[str, JsonValue] | None
) -> None:
    change = session.get(ImportChange, (batch_id, asset.id))
    if change is None:
        session.add(
            ImportChange(
                batch_id=batch_id,
                asset_id=asset.id,
                operation="insert" if before is None else "update",
                before=before,
                after_revision=asset.revision,
            )
        )
    else:
        change.after_revision = asset.revision


def mutate(session: Session, batch: ImportBatch, job: Progress) -> None:
    session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": CORPUS_LOCK})
    kind = "feeder" if batch.layer_type == "feeder_line" else batch.layer_type
    inserted = updated = 0
    parents = {
        (asset_type, external): identifier
        for identifier, asset_type, external in session.execute(
            select(Asset.id, Asset.type, Asset.external_id).where(
                Asset.type.in_(["pole", "feeder"]), Asset.external_id.is_not(None)
            )
        )
    }
    optional = (
        "install_date",
        "capacity_kva",
        "load_factor",
        "material",
        "vegetation_index",
        "last_maintenance_date",
        "external_feeder_id",
        "external_pole_id",
    )
    for rows in session.scalars(
        select(ImportRow)
        .where(ImportRow.batch_id == batch.id, ImportRow.valid)
        .order_by(ImportRow.row_number)
    ).partitions(1000):
        external_ids = [str((row.normalized or {})["external_id"]) for row in rows]
        old: dict[str, dict[str, JsonValue]] = {}
        for value in session.execute(
            text(
                "SELECT to_jsonb(a) || jsonb_build_object('geom', "
                "encode(ST_AsEWKB(a.geom),'hex')) FROM assets a "
                "WHERE type=:kind AND external_id=ANY(:ids)"
            ),
            {"kind": kind, "ids": external_ids},
        ).scalars():
            old[str(value["external_id"])] = value
        records: list[dict[str, object]] = []
        for row, external_id in zip(rows, external_ids, strict=True):
            before = old.get(external_id)
            attrs = row.normalized or {}
            record: dict[str, object] = {
                "type": kind,
                "external_id": external_id,
                "geom": row.geom,
                "batch_id": batch.id,
                "last_batch_id": batch.id,
                "revision": 1,
            }
            for field in optional:
                value = attrs.get(field, (before or {}).get(field))
                record[field] = (
                    date.fromisoformat(value)
                    if field.endswith("date") and isinstance(value, str)
                    else value
                )
            for field, parent_type in (("feeder", "feeder"), ("pole", "pole")):
                ref = record["external_" + field + "_id"]
                record[field + "_id"] = (
                    parents.get((parent_type, str(ref)))
                    if ref is not None
                    else (before or {}).get(field + "_id")
                )
            records.append(record)
        statement = pg_insert(Asset).values(records)
        statement = statement.on_conflict_do_update(
            index_elements=[Asset.type, Asset.external_id],
            set_={
                field: getattr(statement.excluded, field)
                for field in (*optional, "geom", "last_batch_id", "pole_id", "feeder_id")
            },
        )
        written = session.execute(
            statement.returning(Asset.id, Asset.external_id, Asset.revision)
        ).all()
        changes = []
        for identifier, external, revision in written:
            before = old.get(external)
            inserted += before is None
            updated += before is not None
            changes.append(
                dict(
                    batch_id=batch.id,
                    asset_id=identifier,
                    operation="insert" if before is None else "update",
                    before=before,
                    after_revision=revision,
                )
            )
        session.execute(insert(ImportChange), changes)
        job.processed += len(rows)
    # A newly imported parent can fulfil an earlier upload's unresolved reference.
    for field, parent_type in (("feeder", "feeder"), ("pole", "pole")):
        if kind != parent_type:
            continue
        children = session.scalars(
            select(Asset).where(
                getattr(Asset, "external_" + field + "_id").is_not(None),
                getattr(Asset, field + "_id").is_(None),
            )
        ).all()
        for child in children:
            parent = session.scalar(
                select(Asset.id).where(
                    Asset.type == kind,
                    Asset.external_id == getattr(child, "external_" + field + "_id"),
                )
            )
            if parent is not None:
                before = snapshot(session, child.id)
                setattr(child, field + "_id", parent)
                child.last_batch_id = batch.id
                session.flush()
                session.refresh(child)
                journal(session, batch.id, child, before)
    session.execute(delete(RiskScore))
    extent = session.execute(
        text(
            "SELECT ST_XMin(e),ST_YMin(e),ST_XMax(e),ST_YMax(e) FROM "
            "(SELECT ST_Extent(a.geom)::box3d e FROM assets a "
            "JOIN import_changes c ON c.asset_id=a.id "
            "WHERE c.batch_id=:id) q"
        ),
        {"id": batch.id},
    ).one()
    batch.error_report = {
        **batch.error_report,
        "extent": list(extent) if extent[0] is not None else None,
    }
    batch.row_counts = {**batch.row_counts, "inserted": inserted, "updated": updated}
    batch.status, batch.completed_at = "imported", datetime.now(UTC)
    session.execute(delete(ImportRow).where(ImportRow.batch_id == batch.id))


def check_rollback(session: Session, batch: ImportBatch) -> list[ImportChange]:
    session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": CORPUS_LOCK})
    changes = session.scalars(select(ImportChange).where(ImportChange.batch_id == batch.id)).all()
    conflict = session.scalar(
        select(ImportChange.asset_id)
        .outerjoin(Asset, Asset.id == ImportChange.asset_id)
        .where(
            ImportChange.batch_id == batch.id,
            or_(
                Asset.id.is_(None),
                Asset.last_batch_id.is_distinct_from(batch.id),
                Asset.revision != ImportChange.after_revision,
            ),
        )
        .limit(1)
    )
    if conflict is not None:
        raise ParseFailure("ROLLBACK_CONFLICT")
    inserted_ids = select(ImportChange.asset_id).where(
        ImportChange.batch_id == batch.id, ImportChange.operation == "insert"
    )
    changed_ids = select(ImportChange.asset_id).where(ImportChange.batch_id == batch.id)
    if changes:
        dependent = session.scalar(
            select(Asset.id)
            .where(
                or_(Asset.feeder_id.in_(inserted_ids), Asset.pole_id.in_(inserted_ids)),
                Asset.id.not_in(changed_ids),
            )
            .limit(1)
        )
        outage = session.scalar(
            select(OutageEvent.id).where(OutageEvent.asset_id.in_(inserted_ids)).limit(1)
        )
        if dependent is not None or outage is not None:
            raise ParseFailure("ROLLBACK_CONFLICT")
    return list(changes)


def rollback(session: Session, batch: ImportBatch) -> None:
    changes = check_rollback(session, batch)
    session.execute(delete(RiskScore))
    # Restore children before removing parent inserts; all writes remain one transaction.
    for change in changes:
        if change.before is None:
            continue
        data = dict(change.before)
        data.pop("id")
        data.pop("revision")
        fields = list(data)
        assignments = ",".join(f'"{field}" = :{field}' for field in fields)
        # Column names originate in our own table schema, never source properties.
        session.execute(
            text(f"UPDATE assets SET {assignments} WHERE id=:asset_id"),
            {**data, "asset_id": change.asset_id},
        )
        restored = session.get(Asset, change.asset_id, populate_existing=True)
        assert restored is not None
        if restored.last_batch_id is not None:
            previous = session.get(ImportChange, (restored.last_batch_id, restored.id))
            if previous:
                previous.after_revision = restored.revision
    ids = [change.asset_id for change in changes if change.before is None]
    # Clear references among inserted rows first. External dependants cause FK failure,
    # safely rolling back the entire transaction instead of erasing later data.
    if ids:
        session.execute(
            text("UPDATE assets SET feeder_id=NULL,pole_id=NULL WHERE id=ANY(:ids)"), {"ids": ids}
        )
        session.execute(text("DELETE FROM assets WHERE id=ANY(:ids)"), {"ids": ids})
    batch.status, batch.completed_at = "rolled_back", datetime.now(UTC)
    session.execute(delete(ImportRow).where(ImportRow.batch_id == batch.id))
