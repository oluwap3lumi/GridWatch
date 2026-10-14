"""Training snapshots come from a real, isolated PostGIS database."""

from data.generator.config import GeneratorConfig
from data.generator.dataset import generate_dataset
from ml.features import FEATURE_COLUMNS, FeatureConfig, build_training_frame
from sqlalchemy import Engine, delete
from sqlalchemy.orm import Session

from app.db.models import Asset, OutageEvent, WeatherObservation
from app.repositories.seed import replace_demo_data
from app.repositories.training import read_training_inputs


def test_readonly_snapshot_matches_seeded_rows(engine: Engine) -> None:
    dataset = generate_dataset(
        GeneratorConfig(asset_count=60, feeder_count=4, transformer_count=12)
    )
    try:
        with Session(engine) as session, session.begin():
            result = replace_demo_data(session, dataset)
        with Session(engine) as session, session.begin():
            inputs = read_training_inputs(session)
            assert inputs.data_hash == result.database_hash
            assert len(inputs.assets) == 60
            assert len(inputs.weather) == 2920
            assert len(inputs.outages) == len(dataset.outages)
        frame = build_training_frame(inputs, FeatureConfig())
        assert frame.cutoff.nunique() == 12
        assert set(frame.target) == {0, 1}
        assert set(FEATURE_COLUMNS).issubset(frame.columns)
    finally:
        with Session(engine) as session, session.begin():
            for model in (OutageEvent, WeatherObservation, Asset):
                session.execute(delete(model))
