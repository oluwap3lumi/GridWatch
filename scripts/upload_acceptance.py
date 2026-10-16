"""Synthetic sample acceptance against an explicitly selected, fresh seeded test stack."""

import json
import os
import sys
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

from app.schemas.assets import AssetCollection  # noqa: E402
from app.schemas.imports import ImportBatchDetail, ImportHistory, LayerType  # noqa: E402
from app.schemas.risk import RescoreResponse, RiskSummary  # noqa: E402


def main() -> None:
    base = os.environ["GRIDWATCH_UPLOAD_ACCEPTANCE_URL"].rstrip("/")
    if urlparse(base).hostname not in {"localhost", "127.0.0.1"}:
        raise SystemExit("Acceptance requires an explicitly selected loopback test deployment")

    def fetch(
        path: str, body: bytes | None = None, content_type: str = "application/json"
    ) -> bytes:
        with urlopen(
            Request(base + "/api/v1" + path, data=body, headers={"Content-Type": content_type}),
            timeout=180,
        ) as response:
            return bytes(response.read())

    def batch(
        path: str, body: bytes | None = None, content_type: str = "application/json"
    ) -> ImportBatchDetail:
        return ImportBatchDetail.model_validate_json(fetch(path, body, content_type))

    def wait(identifier: UUID) -> ImportBatchDetail:
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            current = batch(f"/imports/{identifier}?include_errors=false")
            if current.job and current.job.status in {"completed", "failed"}:
                assert current.job.status == "completed", current.job.error_code
                return current
            time.sleep(0.25)
        raise TimeoutError("UPLOAD_ACCEPTANCE_JOB_TIMEOUT")

    # This script changes scores. Refuse any deployment with prior import history
    # or a corpus other than the default, already-scored synthetic reference.
    assert ImportHistory.model_validate_json(fetch("/imports")).total == 0
    before = RiskSummary.model_validate_json(fetch("/risk/summary"))
    assert before.total_assets == before.scored_assets == 3000
    original = AssetCollection.model_validate_json(fetch("/assets?limit=500"))
    assert all(feature.properties.batch_id is None for feature in original.features)
    identifiers = []
    cases: list[tuple[str, LayerType, int, int, int]] = [
        ("transformers.csv", "transformer", 8, 0, 0),
        ("poles.geojson", "pole", 8, 0, 0),
        ("feeder_lines.geojson", "feeder_line", 2, 0, 0),
        ("poles_shapefile.zip", "pole", 0, 8, 0),
        ("transformers.csv", "transformer", 0, 8, 0),
        ("broken_transformers.csv", "transformer", 0, 1, 4),
    ]
    for name, layer, inserted, updated, invalid in cases:
        boundary = uuid4().hex
        data = (ROOT / "data" / "samples" / name).read_bytes()
        multipart = (
            (
                f'--{boundary}\r\nContent-Disposition: form-data; name="layer_type"\r\n\r\n'
                f'{layer}\r\n--{boundary}\r\nContent-Disposition: form-data; name="file"; '
                f'filename="{name}"\r\nContent-Type: application/octet-stream\r\n\r\n'
            ).encode()
            + data
            + f"\r\n--{boundary}--\r\n".encode()
        )
        initial = batch("/imports", multipart, f"multipart/form-data; boundary={boundary}")
        identifiers.append(initial.id)
        inspected = wait(initial.id)
        assert inspected.detected_columns and inspected.crs_detected
        batch(f"/imports/{initial.id}/validate", b"{}")
        validated = wait(initial.id)
        assert validated.row_counts.invalid == invalid
        assert validated.row_counts.valid == inserted + updated
        if invalid:
            try:
                batch(f"/imports/{initial.id}/commit", b"{}")
            except HTTPError as error:
                assert error.code == 409
            else:
                raise AssertionError("PARTIAL_CONSENT_WAS_NOT_REQUIRED")
        batch(
            f"/imports/{initial.id}/commit", json.dumps({"valid_rows_only": bool(invalid)}).encode()
        )
        imported = wait(initial.id)
        assert imported.status == "imported"
        assert imported.row_counts.inserted == inserted and imported.row_counts.updated == updated
        assert imported.extent is not None and not imported.preview
        report = fetch(f"/imports/{initial.id}/errors.csv")
        assert report.startswith(b"row_number,field,reason")
        if invalid:
            assert len(report.splitlines()) > 1 and b"invalid-date" not in report

    assets = AssetCollection.model_validate_json(fetch("/assets?limit=500"))
    assert assets.pagination.total == 3018
    uploaded = [feature for feature in assets.features if feature.properties.batch_id is not None]
    # Seeded IDs occupy the first pages; explicitly fetch the uploaded tail.
    if not uploaded:
        tail = AssetCollection.model_validate_json(fetch("/assets?limit=500&offset=3000"))
        uploaded = tail.features
    assert len(uploaded) == 18
    assert all(
        feature.properties.pole_id is not None and feature.properties.feeder_id is not None
        for feature in uploaded
        if feature.properties.type == "transformer"
    )
    scored = RescoreResponse.model_validate_json(fetch("/risk/rescore", b"{}"))
    assert scored.scored_assets == 3018
    try:
        batch(f"/imports/{identifiers[0]}/rollback", b"{}")
    except HTTPError as error:
        assert error.code == 409
    else:
        raise AssertionError("DEPENDENCY_CONFLICT_WAS_NOT_DETECTED")
    for identifier in reversed(identifiers):
        batch(f"/imports/{identifier}/rollback", b"{}")
        assert wait(identifier).status == "rolled_back"
    after = RiskSummary.model_validate_json(fetch("/risk/summary"))
    assert after.total_assets == 3000 and after.scored_assets == 0
    restored = RescoreResponse.model_validate_json(fetch("/risk/rescore", b"{}"))
    assert restored.scored_assets == 3000
    final = RiskSummary.model_validate_json(fetch("/risk/summary"))
    assert final.counts_by_band == before.counts_by_band
    print("PASS upload acceptance: formats=3 batches=6 inserted=18 duplicate_inserts=0 invalid=4")
    print("PASS relationships, error CSV, 3018 scores, reverse rollback, restored 3000 scores")


if __name__ == "__main__":
    main()
