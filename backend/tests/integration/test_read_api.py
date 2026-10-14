"""Read API filters, GeoJSON, pagination, and errors against real PostGIS."""

import asyncio
import json
from collections.abc import Iterator
from typing import Any
from urllib.parse import urlencode

import pytest
from data.generator.config import GeneratorConfig
from data.generator.dataset import generate_dataset
from sqlalchemy import Engine, delete
from sqlalchemy.orm import Session

from app.api.dependencies import get_engine
from app.db.models import Asset, OutageEvent, WeatherObservation
from app.main import app
from app.repositories.seed import replace_demo_data
from app.schemas.assets import AssetCollection, AssetDetail, OutageCollection


def request(
    path: str, query: dict[str, str | int | float] | None = None, method: str = "GET"
) -> tuple[int, dict[str, Any]]:
    messages: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        messages.append(message)

    asyncio.run(
        app(
            {
                "type": "http",
                "asgi": {"version": "3.0"},
                "http_version": "1.1",
                "method": method,
                "scheme": "http",
                "path": path,
                "raw_path": path.encode(),
                "query_string": urlencode(query or {}).encode(),
                "root_path": "",
                "headers": [],
                "client": ("127.0.0.1", 1234),
                "server": ("localhost", 8000),
            },
            receive,
            send,
        )
    )
    return messages[0]["status"], json.loads(
        b"".join(
            message.get("body", b"")
            for message in messages
            if message["type"] == "http.response.body"
        )
    )


@pytest.fixture
def api_data(engine: Engine) -> Iterator[None]:
    dataset = generate_dataset(
        GeneratorConfig(asset_count=60, feeder_count=4, transformer_count=12, days=90)
    )
    app.dependency_overrides[get_engine] = lambda: engine
    try:
        with Session(engine) as session, session.begin():
            replace_demo_data(session, dataset)
        yield
    finally:
        app.dependency_overrides.clear()
        with Session(engine) as session, session.begin():
            for model in (OutageEvent, WeatherObservation, Asset):
                session.execute(delete(model))


@pytest.mark.usefixtures("api_data")
def test_assets_geojson_filters_pagination_and_details() -> None:
    status, payload = request("/api/v1/assets", {"limit": 7})
    assert status == 200
    first = AssetCollection.model_validate(payload)
    assert first.pagination.total == 60 and first.pagination.next_offset == 7
    assert [feature.id for feature in first.features] == list(range(1, 8))
    assert first.features[0].geometry.type == "LineString"
    assert first.features[-1].geometry.type == "Point"
    assert all(feature.properties.risk is None for feature in first.features)
    _, payload = request("/api/v1/assets", {"type": "transformer", "offset": 5, "limit": 5})
    page = AssetCollection.model_validate(payload)
    assert page.pagination.total == 12
    assert all(feature.properties.type.value == "transformer" for feature in page.features)
    for query in ({"bbox": "0,0,1,1"}, {"band": "high"}, {"min_risk": 0.0}, {"offset": 999}):
        _, payload = request("/api/v1/assets", query)
        assert payload["features"] == []
    status, payload = request("/api/v1/assets/5", {"limit": 2})
    assert status == 200
    assert AssetDetail.model_validate(payload).asset.id == 5
    assert request("/api/v1/assets/999999")[0] == 404


@pytest.mark.usefixtures("api_data")
def test_outage_geojson_time_bbox_and_asset_filters() -> None:
    status, payload = request("/api/v1/outages", {"limit": 500})
    assert status == 200
    events = OutageCollection.model_validate(payload)
    assert events.features and events.pagination.total == len(events.features)
    assert [f.properties.started_at for f in events.features] == sorted(
        (f.properties.started_at for f in events.features), reverse=True
    )
    event = events.features[0]
    timestamp = event.properties.started_at.isoformat()
    _, payload = request("/api/v1/outages", {"started_after": timestamp})
    assert event.id in [f["id"] for f in payload["features"]]
    _, payload = request("/api/v1/outages", {"started_before": timestamp})
    assert event.id not in [f["id"] for f in payload["features"]]
    _, payload = request("/api/v1/outages", {"asset_id": event.properties.asset_id})
    assert all(
        f["properties"]["asset_id"] == event.properties.asset_id for f in payload["features"]
    )
    _, payload = request("/api/v1/outages", {"bbox": "0,0,1,1"})
    assert payload["features"] == []


@pytest.mark.usefixtures("api_data")
@pytest.mark.parametrize(
    "path,query",
    [
        ("/api/v1/assets", {"limit": 501}),
        ("/api/v1/assets", {"offset": -1}),
        ("/api/v1/assets", {"type": "customer"}),
        ("/api/v1/assets", {"min_risk": 1.1}),
        ("/api/v1/assets", {"bbox": "nan,0,1,1"}),
        ("/api/v1/outages", {"started_after": "2025-01-01"}),
        (
            "/api/v1/outages",
            {"started_after": "2025-02-01T00:00:00Z", "started_before": "2025-01-01T00:00:00Z"},
        ),
    ],
)
def test_invalid_query_returns_422(path: str, query: dict[str, str | int | float]) -> None:
    status, payload = request(path, query)
    assert status == 422
    assert isinstance(payload["detail"], list)


@pytest.mark.usefixtures("api_data")
def test_no_model_and_unscored_http_states() -> None:
    assert request("/api/v1/model")[0] == 404
    status, summary = request("/api/v1/risk/summary")
    assert status == 200
    assert summary["unscored_assets"] == 60 and summary["scoring"] is None
    assert request("/api/v1/risk/hotspots")[1]["features"] == []
    status, error = request("/api/v1/risk/rescore", method="POST")
    assert status == 409 and "make train" in error["detail"]
