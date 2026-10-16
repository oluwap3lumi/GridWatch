"""Deployment-local upload lifecycle. Never trust client filenames or MIME types."""

import csv
import io
import re
from typing import Annotated
from uuid import UUID, uuid4

from data.generator.assets import generate_assets
from data.generator.config import GeneratorConfig
from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response

from app.api.dependencies import DatabaseEngine, ReadSession
from app.core.uploads import UploadSettings
from app.repositories.imports import create_batch, detail, history, schedule_job
from app.schemas.imports import (
    CommitImport,
    ImportBatchDetail,
    ImportExample,
    ImportExampleFeature,
    ImportHistory,
    LayerType,
    ValidateImport,
)
from app.schemas.spatial import LineGeometry, PointGeometry
from app.services.import_records import ParseFailure
from app.services.upload_storage import UploadStorage, UploadTooLarge

router = APIRouter(prefix="/imports", tags=["imports"])


def failure(error: ParseFailure) -> HTTPException:
    return HTTPException(
        status_code=404 if error.code == "BATCH_NOT_FOUND" else 409, detail=error.code
    )


@router.post("", response_model=ImportBatchDetail, status_code=202)
def upload(
    engine: DatabaseEngine,
    file: Annotated[UploadFile, File()],
    layer_type: Annotated[LayerType, Form()],
) -> ImportBatchDetail:
    settings = UploadSettings.from_env()
    storage, identifier = UploadStorage(settings), uuid4()
    filename = re.sub(
        r"[\x00-\x1f\x7f]", "", (file.filename or "upload").replace("\\", "/").split("/")[-1]
    )[-512:]
    try:
        storage.write(identifier, iter(lambda: file.file.read(65536), b""))
        return create_batch(
            engine, identifier, filename or "upload", layer_type, settings.ttl_seconds
        )
    except UploadTooLarge:
        raise HTTPException(status_code=413, detail="UPLOAD_TOO_LARGE") from None
    except Exception:
        storage.delete(identifier)
        raise
    finally:
        file.file.close()


@router.get("", response_model=ImportHistory)
def list_imports(
    session: ReadSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ImportHistory:
    return history(session, limit, offset)


@router.get(
    "/templates/{layer_type}.csv",
    response_class=Response,
    responses={200: {"content": {"text/csv": {"schema": {"type": "string"}}}}},
)
def template(layer_type: LayerType) -> Response:
    header = (
        "external_id,geometry\n"
        if layer_type == "feeder_line"
        else (
            "external_id,latitude,longitude,capacity_kva,install_date,load_factor,"
            "pole_id,feeder_id,last_maintenance_date\n"
        )
    )
    return Response(
        header,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="template.csv"'},
    )


@router.get("/templates/{layer_type}.geojson", response_model=ImportExample)
def example(layer_type: LayerType, response: Response) -> ImportExample:
    """Generate a small, independently importable synthetic example."""
    kind = "feeder" if layer_type == "feeder_line" else layer_type
    asset = next(
        item
        for item in generate_assets(
            GeneratorConfig(asset_count=10, feeder_count=1, transformer_count=2)
        )
        if item.type == kind
    )
    response.headers["Content-Disposition"] = 'attachment; filename="example.geojson"'
    return ImportExample(
        features=[
            ImportExampleFeature(
                geometry=LineGeometry(coordinates=list(asset.coordinates))
                if kind == "feeder"
                else PointGeometry(coordinates=asset.coordinates[0]),
                properties={
                    "external_id": f"demo-{layer_type}-{asset.id}",
                    "install_date": asset.install_date.isoformat(),
                    "capacity_kva": asset.capacity_kva,
                    "load_factor": min(asset.load_factor, 1.5),
                    "vegetation_index": asset.vegetation_index,
                    "material": asset.material,
                    "last_maintenance_date": asset.last_maintenance_date.isoformat(),
                },
            )
        ]
    )


@router.get("/{batch_id}", response_model=ImportBatchDetail)
def get_import(
    batch_id: UUID, session: ReadSession, include_errors: bool = True
) -> ImportBatchDetail:
    try:
        return detail(session, batch_id, include_errors=include_errors)
    except ParseFailure as error:
        raise failure(error) from None


@router.post("/{batch_id}/validate", response_model=ImportBatchDetail, status_code=202)
def validate(
    batch_id: UUID, engine: DatabaseEngine, options: ValidateImport | None = None
) -> ImportBatchDetail:
    return schedule(
        engine, batch_id, "validate", (options or ValidateImport()).model_dump(mode="json")
    )


@router.post("/{batch_id}/commit", response_model=ImportBatchDetail, status_code=202)
def commit(
    batch_id: UUID, engine: DatabaseEngine, options: CommitImport | None = None
) -> ImportBatchDetail:
    return schedule(engine, batch_id, "commit", (options or CommitImport()).model_dump(mode="json"))


@router.post("/{batch_id}/rollback", response_model=ImportBatchDetail, status_code=202)
def undo(batch_id: UUID, engine: DatabaseEngine) -> ImportBatchDetail:
    return schedule(engine, batch_id, "rollback", {})


def schedule(
    engine: DatabaseEngine, batch_id: UUID, operation: str, options: dict[str, object]
) -> ImportBatchDetail:
    from pydantic import JsonValue, TypeAdapter

    try:
        return schedule_job(
            engine, batch_id, operation, TypeAdapter(dict[str, JsonValue]).validate_python(options)
        )
    except ParseFailure as error:
        raise failure(error) from None


@router.get(
    "/{batch_id}/errors.csv",
    response_class=Response,
    responses={200: {"content": {"text/csv": {"schema": {"type": "string"}}}}},
)
def errors_csv(batch_id: UUID, session: ReadSession) -> Response:
    batch = get_import(batch_id, session)
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["row_number", "field", "reason"])
    for issue in batch.errors:
        writer.writerow([issue.row_number, issue.field, issue.reason])
    if batch.error_code:
        writer.writerow(["", "file", batch.error_code])
    return Response(
        output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="errors.csv"'},
    )
