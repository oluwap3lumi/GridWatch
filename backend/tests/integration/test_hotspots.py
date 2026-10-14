"""Hotspot membership uses real geography distances in metres, not degree thresholds."""

from datetime import UTC, datetime

import pytest
from data.generator.config import GeneratorConfig
from data.generator.dataset import generate_dataset
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.models import ModelRun, RiskScore
from app.repositories.risk import hotspots, risk_summary
from app.repositories.seed import replace_demo_data
from app.schemas.spatial import BoundingBox


def test_hotspot_transitivity_noise_and_geography_units(session: Session) -> None:
    session.begin()
    seeded = replace_demo_data(
        session,
        generate_dataset(
            GeneratorConfig(asset_count=60, feeder_count=4, transformer_count=12, days=30)
        ),
    )
    stamp = datetime(2026, 1, 1, tzinfo=UTC)
    session.add(
        ModelRun(
            model_version="spatial-test",
            trained_at=stamp,
            data_hash=seeded.database_hash,
            features=[],
            metrics={},
            git_sha="a" * 40,
        )
    )
    session.flush()
    locations = {
        5: (3.300, 6.5),
        6: (3.304, 6.5),
        7: (3.308, 6.5),
        8: (3.4, 6.6),
        9: (3.4001, 6.6),
        10: (3.302, 6.5),
    }
    for asset_id, (lon, lat) in locations.items():
        session.execute(
            text("UPDATE assets SET geom=ST_SetSRID(ST_MakePoint(:lon,:lat),4326) WHERE id=:id"),
            {"lon": lon, "lat": lat, "id": asset_id},
        )
        score, band = (0.12, "critical") if asset_id == 6 else (0.09, "high")
        if asset_id == 10:
            score, band = 0.07, "medium"
        session.add(
            RiskScore(
                asset_id=asset_id,
                score=score,
                band=band,
                model_version="spatial-test",
                scored_at=stamp,
                prediction_cutoff=stamp,
                top_factors=[],
            )
        )
    session.flush()
    distance = session.scalar(
        text(
            "SELECT ST_Distance(a.geom::geography,b.geom::geography) FROM assets a,assets b "
            "WHERE a.id=5 AND b.id=6"
        )
    )
    assert 440 < distance < 450
    collection = hotspots(session, limit=100, offset=0)
    assert collection.pagination.total == 1
    hotspot = collection.features[0]
    assert hotspot.id == 5
    assert hotspot.properties.asset_ids == [5, 6, 7]
    assert hotspot.properties.asset_count == 3
    assert hotspot.properties.mean_score == pytest.approx(0.1)
    assert hotspot.properties.counts_by_band.high == 2
    assert hotspot.properties.counts_by_band.critical == 1
    assert hotspot.geometry.coordinates[0] == pytest.approx(3.304, abs=0.0001)
    assert hotspots(session, limit=100, offset=1).features == []
    assert hotspots(session, limit=100, offset=0, bbox=BoundingBox.parse("0,0,1,1")).features == []
    summary = risk_summary(session)
    assert summary.total_assets == 60 and summary.scored_assets == 6
    assert summary.counts_by_band.medium == 1 and summary.counts_by_band.high == 4
