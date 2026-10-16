"""Closed import log vocabulary; private upload data never enters event messages."""

import logging
from enum import StrEnum
from uuid import UUID


class ImportEvent(StrEnum):
    uploaded = "UPLOAD_RECEIVED"
    validated = "VALIDATION_COMPLETED"
    committed = "IMPORT_COMMITTED"
    rolled_back = "IMPORT_ROLLED_BACK"
    expired = "UPLOAD_EXPIRED"
    failed = "IMPORT_FAILED"


class ImportError(StrEnum):
    too_large = "UPLOAD_TOO_LARGE"
    invalid_file = "INVALID_FILE"
    invalid_crs = "INVALID_CRS"
    conflict = "IMPORT_CONFLICT"
    internal = "IMPORT_INTERNAL_ERROR"


def log_import(
    event: ImportEvent, batch_id: UUID, *, count: int = 0, error: ImportError | None = None
) -> None:
    if not isinstance(event, ImportEvent) or not isinstance(batch_id, UUID):
        raise ValueError("Invalid import log identifiers")
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        raise ValueError("Invalid import log count")
    if error is not None and not isinstance(error, ImportError):
        raise ValueError("Invalid import log error code")
    logging.getLogger("gridwatch.imports").info(
        event.value, extra={"batch_id": batch_id, "count": count, "error_code": error}
    )
