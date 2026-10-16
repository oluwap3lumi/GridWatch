"""Exercise the HTTP upload flow against an explicitly selected empty test deployment."""

import csv
import io
import os
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

from app.schemas.assets import AssetCollection  # noqa: E402
from app.schemas.imports import ImportBatchDetail  # noqa: E402

from data.generator.assets import generate_assets  # noqa: E402
from data.generator.config import GeneratorConfig  # noqa: E402


def main() -> None:
    base = os.environ["GRIDWATCH_IMPORT_SMOKE_URL"].rstrip("/")

    def fetch(
        path: str, data: bytes | None = None, content_type: str = "application/json"
    ) -> bytes:
        request = Request(
            base + "/api/v1" + path, data=data, headers={"Content-Type": content_type}
        )
        with urlopen(request, timeout=30) as response:
            return bytes(response.read())

    def batch(
        path: str, data: bytes | None = None, content_type: str = "application/json"
    ) -> ImportBatchDetail:
        return ImportBatchDetail.model_validate_json(fetch(path, data, content_type))

    def wait(identifier: UUID) -> ImportBatchDetail:
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            current = batch(f"/imports/{identifier}")
            if current.job and current.job.status in {"completed", "failed"}:
                assert current.job.status == "completed", current.job.error_code
                return current
            time.sleep(0.25)
        raise TimeoutError("Import smoke job timeout")

    deadline = time.monotonic() + 120
    while True:
        try:
            fetch("/ready")
            break
        except Exception:
            if time.monotonic() >= deadline:
                raise TimeoutError("Import smoke deployment readiness timeout") from None
            time.sleep(0.25)
    # Refuse to change a populated deployment. The documented target is test-db.
    assert AssetCollection.model_validate_json(fetch("/assets")).pagination.total == 0
    asset = next(
        item
        for item in generate_assets(
            GeneratorConfig(asset_count=10, feeder_count=1, transformer_count=2)
        )
        if item.type == "transformer"
    )
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["external_id", "latitude", "longitude"])
    writer.writerow(["synthetic-smoke-transformer", asset.location[1], asset.location[0]])
    data = output.getvalue().encode()
    multipart = (
        b'--smoke\r\nContent-Disposition: form-data; name="layer_type"\r\n\r\ntransformer\r\n'
        b'--smoke\r\nContent-Disposition: form-data; name="file"; filename="synthetic.csv"\r\n\r\n'
        + data
        + b"\r\n--smoke--\r\n"
    )
    initial = batch("/imports", multipart, "multipart/form-data; boundary=smoke")
    inspected = wait(initial.id)
    assert inspected.format == "csv" and inspected.row_counts.total == 1
    batch(f"/imports/{initial.id}/validate", b"{}")
    validated = wait(initial.id)
    assert validated.row_counts.valid == 1 and validated.preview[0].geometry is not None
    batch(f"/imports/{initial.id}/commit", b"{}")
    imported = wait(initial.id)
    assert imported.status == "imported" and imported.row_counts.inserted == 1
    assert imported.extent is not None and not imported.preview
    assert AssetCollection.model_validate_json(fetch("/assets")).pagination.total == 1
    assert fetch(f"/imports/{initial.id}/errors.csv").startswith(b"row_number,field,reason")
    batch(f"/imports/{initial.id}/rollback", b"{}")
    assert wait(initial.id).status == "rolled_back"
    assert AssetCollection.model_validate_json(fetch("/assets")).pagination.total == 0
    print("PASS import HTTP/worker smoke: inspected=1 validated=1 inserted=1 rolled_back=1")


if __name__ == "__main__":
    main()
