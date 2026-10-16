"""Private staging bounds, cleanup, configuration and closed log vocabulary."""

import json
import logging
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.import_logging import ImportError, ImportEvent, log_import
from app.core.observability import JsonFormatter
from app.core.uploads import UploadSettings
from app.schemas.imports import CommitImport, ImportBatchDetail, RowCounts
from app.schemas.spatial import MultiLineGeometry
from app.services.upload_storage import UploadStorage, UploadTooLarge


def test_limits_ttl_and_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("UPLOAD_STAGING_DIR", str(tmp_path))
    monkeypatch.setenv("UPLOAD_TTL_SECONDS", "3600")
    settings = UploadSettings.from_env()
    assert settings.staging_dir == tmp_path
    assert settings.ttl_seconds == 3600
    assert settings.max_bytes == 25 * 1024 * 1024 and settings.max_features == 100_000
    monkeypatch.setenv("UPLOAD_TTL_SECONDS", "0")
    with pytest.raises(ValueError, match="ttl_seconds"):
        UploadSettings.from_env()


def test_staging_limit_cleanup_and_no_overwrite(tmp_path: Path) -> None:
    store = UploadStorage(UploadSettings(staging_dir=tmp_path, max_bytes=4))
    batch = uuid4()
    assert store.write(batch, [b"ab", b"cd"]) == 4
    assert store.path(batch).read_bytes() == b"abcd"
    with pytest.raises(FileExistsError):
        store.write(batch, [b"x"])
    assert store.path(batch).read_bytes() == b"abcd"
    store.delete(batch)
    store.delete(batch)
    with pytest.raises(UploadTooLarge, match="^UPLOAD_TOO_LARGE$"):
        store.write(batch, [b"abcd", b"e"])
    assert not store.path(batch).exists()

    def interrupted():
        yield b"a"
        raise OSError("synthetic interrupted stream")

    with pytest.raises(OSError):
        store.write(batch, interrupted())
    assert not store.path(batch).exists()


def test_staging_rejects_symlink_escape(tmp_path: Path) -> None:
    store = UploadStorage(UploadSettings(staging_dir=tmp_path / "staging"))
    store.root.mkdir()
    outside = tmp_path / "synthetic-secret.txt"
    outside.write_text("synthetic private content")
    batch = uuid4()
    link = store.root / f"{batch.hex}.upload"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("Creating symlinks requires privileges on this Windows installation")
    with pytest.raises(ValueError, match="Unsafe"):
        store.delete(batch)
    assert outside.read_text() == "synthetic private content"


def test_import_logs_drop_messages_coordinates_and_exceptions(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="gridwatch.imports")
    batch = uuid4()
    log_import(ImportEvent.failed, batch, count=3, error=ImportError.invalid_file)
    formatted = json.loads(JsonFormatter().format(caplog.records[-1]))
    assert formatted == {
        "event": "IMPORT_FAILED",
        "batch_id": str(batch),
        "count": 3,
        "error_code": "INVALID_FILE",
    }
    try:
        raise ValueError("synthetic-coordinate=3.3,6.5")
    except ValueError:
        logging.getLogger("gridwatch.imports.parser").exception(
            "private filename and row %s", "3.3,6.5", extra={"coordinates": [3.3, 6.5]}
        )
    assert json.loads(JsonFormatter().format(caplog.records[-1])) == {"event": "IMPORT_EVENT"}
    for name in ("pyproj", "shapefile", "shapely", "python_multipart", "sqlalchemy.engine"):
        record = logging.LogRecord(name, logging.ERROR, "", 0, {"lat": 3.3}, (), None)
        assert json.loads(JsonFormatter().format(record)) == {"event": "IMPORT_EVENT"}


def test_contracts_reject_invalid_geometry_and_negative_counts() -> None:
    assert CommitImport().valid_rows_only is False
    with pytest.raises(ValidationError):
        RowCounts(total=-1)
    with pytest.raises(ValidationError):
        MultiLineGeometry(coordinates=[[(3.3, 6.5)]])
    # Import contracts are typed even before routes are added in the lifecycle slice.
    assert "preview" in ImportBatchDetail.model_json_schema()["properties"]
