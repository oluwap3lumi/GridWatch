"""Committed synthetic examples are reproducible and exercise the real parsers."""

import io
import zipfile
from pathlib import Path

import pytest
from data.generator import samples

from app.core.uploads import UploadSettings
from app.schemas.imports import ValidateImport
from app.services.import_parsing import parse_upload
from app.services.import_validation import validate_upload

sample_files = samples.sample_files


def test_sample_bytes_match_generator() -> None:
    root = Path(samples.__file__).resolve().parents[1] / "samples"
    first, second = sample_files(), sample_files()
    assert first == second
    assert all((root / name).read_bytes() == data for name, data in first.items())
    with zipfile.ZipFile(io.BytesIO(first["poles_shapefile.zip"])) as archive:
        assert all(entry.create_system == 3 for entry in archive.infolist())


@pytest.mark.parametrize(
    ("name", "layer", "count", "invalid"),
    [
        ("transformers.csv", "transformer", 8, 0),
        ("poles.geojson", "pole", 8, 0),
        ("feeder_lines.geojson", "feeder_line", 2, 0),
        ("poles_shapefile.zip", "pole", 8, 0),
        ("broken_transformers.csv", "transformer", 5, 4),
    ],
)
def test_samples_parse_and_validate(name, layer, count, invalid) -> None:
    parsed = parse_upload(sample_files()[name], name, UploadSettings())
    rows = validate_upload(parsed, layer, ValidateImport())
    assert len(rows) == count
    assert sum(bool(row.errors) for row in rows) == invalid
    if name.endswith(".zip"):
        assert "32631" in (parsed.crs_detected or "")
        expected = parse_upload(sample_files()["poles.geojson"], "poles.geojson", UploadSettings())
        expected_rows = validate_upload(expected, "pole", ValidateImport())
        for actual, original in zip(rows, expected_rows, strict=True):
            assert actual.geometry is not None and original.geometry is not None
            assert actual.geometry.coordinates == pytest.approx(original.geometry.coordinates)
