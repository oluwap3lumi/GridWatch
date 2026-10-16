"""Spatial validation and generated API contracts, without database mocks."""

import pytest
from scripts.openapi_types import generate_types, render_type

from app.main import app
from app.schemas.spatial import BoundingBox


@pytest.mark.parametrize("value", ["0,0,1", "1,0,0,1", "0,1,1,0", "nan,0,1,1", "181,0,182,1"])
def test_invalid_bounding_boxes(value: str) -> None:
    with pytest.raises(ValueError):
        BoundingBox.parse(value)


def test_generated_contracts_cover_geojson_and_nullable_risk() -> None:
    document = app.openapi()
    output = generate_types(document)
    assert "export type Position = [number, number]" in output
    assert "export type AssetGeometry = (PointGeometry) | (LineGeometry)" in output
    assert '"risk": (RiskSnapshot) | (null)' in output
    assert '"GET /api/v1/assets/{asset_id}"' in output
    assert "any" not in output
    assert (
        render_type({"type": "object", "additionalProperties": {"type": "number"}})
        == "Record<string, number>"
    )
    with pytest.raises(ValueError, match="Unsupported"):
        render_type({"type": "made-up"})


def test_openapi_paths_references_and_serialized_defaults() -> None:
    document = app.openapi()
    assert set(document["paths"]) == {
        "/api/v1/health",
        "/api/v1/ready",
        "/api/v1/metrics",
        "/api/v1/assets",
        "/api/v1/assets/{asset_id}",
        "/api/v1/outages",
        "/api/v1/risk/summary",
        "/api/v1/risk/hotspots",
        "/api/v1/risk/rescore",
        "/api/v1/model",
        "/api/v1/model/history",
        "/api/v1/imports",
        "/api/v1/imports/templates/{layer_type}.csv",
        "/api/v1/imports/templates/{layer_type}.geojson",
        "/api/v1/imports/{batch_id}",
        "/api/v1/imports/{batch_id}/validate",
        "/api/v1/imports/{batch_id}/commit",
        "/api/v1/imports/{batch_id}/rollback",
        "/api/v1/imports/{batch_id}/errors.csv",
    }
    components = document["components"]["schemas"]
    assert "type" in components["PointGeometry"]["required"]
    assert "low" in components["BandCounts"]["required"]
    assert "horizon_days" in components["RescoreResponse"]["required"]

    def check(value: object) -> None:
        if isinstance(value, dict):
            if "$ref" in value:
                assert value["$ref"].removeprefix("#/components/schemas/") in components
            for child in value.values():
                check(child)
        elif isinstance(value, list):
            for child in value:
                check(child)

    check(document)
    for path in document["paths"].values():
        for operation in path.values():
            assert all(
                parameter["name"] not in {"session", "engine", "root"}
                for parameter in operation.get("parameters", [])
            )
