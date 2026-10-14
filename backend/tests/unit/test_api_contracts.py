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
