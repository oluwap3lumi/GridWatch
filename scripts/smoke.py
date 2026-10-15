"""HTTP, scoring, typed GeoJSON, model provenance, and PostGIS checks for the running stack."""

import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.schemas.assets import AssetCollection, AssetDetail, OutageCollection  # noqa: E402
from app.schemas.risk import (  # noqa: E402
    HotspotCollection,
    ModelHistory,
    ModelInfo,
    RescoreResponse,
    RiskSummary,
)


def main() -> None:
    """Verify every application endpoint and matching scores across the running full stack."""
    api = f"http://localhost:{os.getenv('API_PORT', '8000')}"
    web = f"http://localhost:{os.getenv('WEB_PORT', '5173')}"
    for url in (f"{api}/health", f"{api}/api/v1/health", f"{web}/api/v1/health"):
        with urlopen(url, timeout=10) as response:
            assert response.status == 200
            assert json.load(response) == {"status": "ok"}
        print(f"PASS {url}")
    with urlopen(web, timeout=10) as response:
        assert response.status == 200
        assert 'id="root"' in response.read().decode()
    print(f"PASS {web} entry point")
    with urlopen(f"{api}/api/v1/model", timeout=30) as response:
        model = ModelInfo.model_validate_json(response.read())
    assert model.metrics["quality_gate_passed"] == 1
    assert model.metrics["pr_auc_lift"] > 0
    assert len(model.features) == len(model.feature_importance)
    print(f"PASS model {model.model_version}: verified provenance and SHAP importance")
    with urlopen(f"{api}/api/v1/model/history?limit=500", timeout=30) as response:
        history = ModelHistory.model_validate_json(response.read())
    assert history.pagination.total > 0
    assert len({item.model_version for item in history.items}) == len(history.items)
    print(f"PASS registered model history: {history.pagination.total} versions")
    with urlopen(Request(f"{api}/api/v1/risk/rescore", method="POST"), timeout=180) as response:
        scored = RescoreResponse.model_validate_json(response.read())
    assert scored.model_version == model.model_version
    assert scored.scored_assets > 0 and scored.prediction_cutoff is not None
    print(
        f"PASS rescore: {scored.scored_assets} assets, "
        f"cutoff {scored.prediction_cutoff.isoformat()}"
    )
    with urlopen(f"{api}/api/v1/risk/summary", timeout=30) as response:
        summary = RiskSummary.model_validate_json(response.read())
    assert summary.scored_assets == scored.scored_assets
    assert sum(summary.counts_by_band.model_dump().values()) == summary.scored_assets
    assert sum(feeder.total_assets for feeder in summary.by_feeder) == summary.total_assets
    assert summary.counts_by_band == scored.counts_by_band
    print(f"PASS risk summary: {summary.counts_by_band.model_dump()}")
    with urlopen(f"{api}/api/v1/assets?limit=5&min_risk=0", timeout=30) as response:
        assets = AssetCollection.model_validate_json(response.read())
    assert len(assets.features) > 0 and assets.pagination.total == scored.scored_assets
    assert all(feature.properties.risk is not None for feature in assets.features)
    asset_id = assets.features[0].id
    with urlopen(f"{api}/api/v1/assets/{asset_id}?limit=5", timeout=30) as response:
        detail = AssetDetail.model_validate_json(response.read())
    assert detail.asset.id == asset_id and detail.asset.properties.risk is not None
    assert detail.asset.properties.risk.model_version == scored.model_version
    print("PASS assets: typed GeoJSON, pagination, risk filters, and detail/history")
    with urlopen(f"{api}/api/v1/outages?limit=5", timeout=30) as response:
        outages = OutageCollection.model_validate_json(response.read())
    assert len(outages.features) > 0
    print("PASS outages: typed paginated GeoJSON")
    with urlopen(f"{api}/api/v1/risk/hotspots?limit=500", timeout=60) as response:
        clusters = HotspotCollection.model_validate_json(response.read())
    assert all(feature.properties.asset_count >= 3 for feature in clusters.features)
    print(f"PASS hotspots: {clusters.pagination.total} geography-based clusters")
    with urlopen(f"{api}/api/v1/model", timeout=30) as response:
        current = ModelInfo.model_validate_json(response.read())
    assert current.scored_model_version == scored.model_version
    result = subprocess.run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "db",
            "sh",
            "-c",
            'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "SELECT PostGIS_Version()"',
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip().startswith("3.")
    print(f"PASS PostGIS: {result.stdout.strip()}")


if __name__ == "__main__":
    main()
