"""Load actual synthetic corpora into PostGIS and verify repeatability and atomicity."""

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from data.generator.config import GeneratorConfig
from data.generator.dataset import generate_dataset
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import ModelRun, RiskScore
from app.repositories.seed import data_fingerprint, replace_demo_data


def config(seed: int = 42) -> GeneratorConfig:
    return GeneratorConfig(
        seed=seed, asset_count=240, feeder_count=6, transformer_count=60, days=90
    )


def test_seed_counts_geometry_clustering_and_references(session: Session) -> None:
    dataset = generate_dataset(config())
    with session.begin():
        result = replace_demo_data(session, dataset)
        assert (result.assets, result.weather, result.outages) == (240, 540, len(dataset.outages))
        assert result.outages > 0
        assert result.data_hash == dataset.data_hash()
        for table in ("assets", "weather_obs", "outage_events"):
            assert (
                session.scalar(
                    text(
                        f"SELECT count(*) FROM {table} WHERE NOT ST_IsValid(geom) "
                        "OR ST_IsEmpty(geom) OR ST_SRID(geom) <> 4326 "
                        "OR NOT ST_CoveredBy(geom, ST_MakeEnvelope(3.25,6.42,3.55,6.65,4326))"
                    )
                )
                == 0
            )
        assert (
            session.scalar(
                text(
                    "SELECT count(*) FROM assets a JOIN assets f ON f.id=a.feeder_id "
                    "WHERE f.type <> 'feeder' "
                    "OR NOT ST_DWithin(a.geom::geography,f.geom::geography,500)"
                )
            )
            == 0
        )
        assert (
            session.scalar(
                text(
                    "SELECT count(*) FROM outage_events o JOIN assets a ON a.id=o.asset_id "
                    "WHERE o.started_at::date < a.install_date OR o.duration_min <= 0"
                )
            )
            == 0
        )
        assert session.scalar(select(func.count()).select_from(ModelRun)) == 0
        assert session.scalar(select(func.count()).select_from(RiskScore)) == 0


def test_reseeding_preserves_complete_persisted_snapshot(session: Session) -> None:
    dataset = generate_dataset(config())
    with session.begin():
        first = replace_demo_data(session, dataset)
        second = replace_demo_data(session, generate_dataset(config()))
        assert second == first
        different = replace_demo_data(session, generate_dataset(config(43)))
        assert different.database_hash != first.database_hash
        # Smaller configuration removes stale IDs, rather than silently appending duplicates.
        smaller = replace(config(), asset_count=120, transformer_count=30)
        reduced = replace_demo_data(session, generate_dataset(smaller))
        assert reduced.assets == 120
        assert session.scalar(text("SELECT max(id) FROM assets")) == 120


def test_failed_load_rolls_back_to_previous_dataset(session: Session) -> None:
    dataset = generate_dataset(config())
    with session.begin():
        loaded = replace_demo_data(session, dataset)
        invalid = replace(
            dataset, assets=(replace(dataset.assets[0], load_factor=-1), *dataset.assets[1:])
        )
        with pytest.raises(IntegrityError), session.begin_nested():
            replace_demo_data(session, invalid)
        assert data_fingerprint(session) == loaded.database_hash


def test_reseed_refuses_to_invalidate_trained_models(session: Session) -> None:
    dataset = generate_dataset(config())
    with session.begin():
        loaded = replace_demo_data(session, dataset)
        session.add(
            ModelRun(
                model_version="synthetic-test",
                trained_at=datetime(2025, 1, 1, tzinfo=UTC),
                data_hash="a" * 64,
                features=["age"],
                metrics={"auc": 0.7},
                git_sha="0" * 40,
            )
        )
        session.flush()
        with pytest.raises(ValueError, match="model runs"):
            replace_demo_data(session, dataset)
        assert data_fingerprint(session) == loaded.database_hash
