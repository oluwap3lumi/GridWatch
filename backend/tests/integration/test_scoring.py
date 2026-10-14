"""Full synthetic training and scoring, plus rollback, corruption, and concurrency guards."""

from collections.abc import Iterator
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest
from data.generator.config import GeneratorConfig
from data.generator.dataset import generate_dataset
from ml.features import FEATURE_COLUMNS, FEATURE_SCHEMA_VERSION, build_training_frame
from ml.predict import AssetPrediction
from ml.train import ModelBundle, TrainingConfig, fit_models
from sqlalchemy import Engine, delete, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ModelUnavailable, ScoringConflict
from app.db.models import Asset, ModelRun, OutageEvent, RiskScore, WeatherObservation
from app.repositories.model_runs import register_run
from app.repositories.risk import risk_summary, scoring_lock
from app.repositories.seed import replace_demo_data
from app.repositories.training import read_training_inputs
from app.services.artifacts import save_artifacts
from app.services.risk_policy import risk_band
from app.services.scoring import rescore
from app.services.train import dependency_versions


@pytest.fixture(scope="module")
def trained_registry(engine: Engine, tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    root = tmp_path_factory.mktemp("model-registry")
    config = TrainingConfig()
    try:
        with Session(engine) as session, session.begin():
            replace_demo_data(session, generate_dataset(GeneratorConfig()))
        with Session(engine) as session, session.begin():
            inputs = read_training_inputs(session)
        result = fit_models(build_training_frame(inputs, config.features), config)
        assert result.metrics["quality_gate_passed"] == 1
        stamp = datetime.now(UTC)
        save_artifacts(
            root,
            "test-scoring",
            result,
            {
                "model_version": "test-scoring",
                "trained_at": stamp.isoformat(),
                "data_hash": inputs.data_hash,
                "features": list(FEATURE_COLUMNS),
                "feature_schema": FEATURE_SCHEMA_VERSION,
                "git_sha": "b" * 40,
                "training_config": asdict(config),
                "dependency_versions": dependency_versions(),
                "synthetic_data_only": True,
            },
        )
        with Session(engine) as session, session.begin():
            register_run(
                session,
                version="test-scoring",
                trained_at=stamp,
                data_hash=inputs.data_hash,
                features=list(FEATURE_COLUMNS),
                metrics=result.metrics,
                git_sha="b" * 40,
            )
        yield root
    finally:
        with Session(engine) as session, session.begin():
            for model in (RiskScore, ModelRun, OutageEvent, WeatherObservation, Asset):
                session.execute(delete(model))


@pytest.fixture
def scoring_data(trained_registry: Path, engine: Engine) -> Iterator[Path]:
    with Session(engine) as session, session.begin():
        session.execute(delete(RiskScore))
    yield trained_registry
    with Session(engine) as session, session.begin():
        session.execute(delete(RiskScore))


def snapshot(engine: Engine) -> list[tuple[object, ...]]:
    with Session(engine) as session:
        return [
            tuple(row)
            for row in session.execute(
                select(
                    RiskScore.asset_id,
                    RiskScore.score,
                    RiskScore.band,
                    RiskScore.model_version,
                    RiskScore.prediction_cutoff,
                    RiskScore.top_factors,
                ).order_by(RiskScore.asset_id)
            )
        ]


def test_rescore_populates_reproducible_complete_batch(scoring_data: Path, engine: Engine) -> None:
    result = rescore(engine, scoring_data)
    assert result.model_version == "test-scoring"
    assert result.scored_assets == 3000 and result.unscored_assets == 0
    assert result.prediction_cutoff == datetime(2026, 1, 1, tzinfo=UTC)
    assert sum(result.counts_by_band.model_dump().values()) == 3000
    first = snapshot(engine)
    for _, score, band, _, _, factors in first:
        assert risk_band(float(score)).value == band
        assert len(factors) <= 5
        assert all(factor["contribution_unit"] == "log_odds" for factor in factors)
    with Session(engine) as session:
        summary = risk_summary(session)
        assert len(summary.by_feeder) == 20
        assert sum(feeder.total_assets for feeder in summary.by_feeder) == 3000
        assert summary.counts_by_band == result.counts_by_band
    rescore(engine, scoring_data)
    assert snapshot(engine) == first


def test_competing_rescore_is_rejected_and_lock_released(
    scoring_data: Path, engine: Engine
) -> None:
    with scoring_lock(engine), pytest.raises(ScoringConflict, match="Another"):
        rescore(engine, scoring_data)
    assert rescore(engine, scoring_data).scored_assets == 3000


def test_failed_score_insert_preserves_previous_batch(
    scoring_data: Path,
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rescore(engine, scoring_data)
    previous = snapshot(engine)
    monkeypatch.setattr("ml.predict.score_features", lambda *_: (AssetPrediction(999999, 0.1, ()),))
    with pytest.raises(IntegrityError):
        rescore(engine, scoring_data)
    assert snapshot(engine) == previous


def test_changed_corpus_and_corrupt_artifacts_preserve_previous_batch(
    scoring_data: Path, engine: Engine
) -> None:
    rescore(engine, scoring_data)
    previous = snapshot(engine)
    with Session(engine) as session:
        original = session.scalar(select(Asset.load_factor).where(Asset.id == 1))
    try:
        with Session(engine) as session, session.begin():
            session.execute(text("UPDATE assets SET load_factor=load_factor+0.001 WHERE id=1"))
        with pytest.raises(ScoringConflict, match="does not match"):
            rescore(engine, scoring_data)
        assert snapshot(engine) == previous
    finally:
        with Session(engine) as session, session.begin():
            session.execute(
                text("UPDATE assets SET load_factor=:value WHERE id=1"), {"value": original}
            )
    metrics = scoring_data / "test-scoring" / "metrics.json"
    saved = metrics.read_bytes()
    try:
        metrics.write_text("{}")
        with pytest.raises(ModelUnavailable, match="artifacts"):
            rescore(engine, scoring_data)
        assert snapshot(engine) == previous
    finally:
        metrics.write_bytes(saved)


def test_changed_corpus_during_prediction_is_rejected(
    scoring_data: Path,
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ml.predict as predictor

    rescore(engine, scoring_data)
    previous = snapshot(engine)
    original_predict = predictor.score_features
    with Session(engine) as session:
        original_load = session.scalar(select(Asset.load_factor).where(Asset.id == 1))

    def concurrent_change(bundle: ModelBundle, frame: pd.DataFrame) -> tuple[AssetPrediction, ...]:
        predictions = original_predict(bundle, frame)
        with Session(engine) as session, session.begin():
            session.execute(text("UPDATE assets SET load_factor=load_factor+0.001 WHERE id=1"))
        return predictions

    monkeypatch.setattr(predictor, "score_features", concurrent_change)
    try:
        with pytest.raises(ScoringConflict, match="changed while scoring"):
            rescore(engine, scoring_data)
        assert snapshot(engine) == previous
    finally:
        with Session(engine) as session, session.begin():
            session.execute(
                text("UPDATE assets SET load_factor=:value WHERE id=1"), {"value": original_load}
            )


def test_newer_passing_model_during_prediction_is_rejected(
    scoring_data: Path,
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ml.predict as predictor

    rescore(engine, scoring_data)
    previous = snapshot(engine)
    original_predict = predictor.score_features
    with Session(engine) as session:
        original_hash = session.scalar(
            select(ModelRun.data_hash).where(ModelRun.model_version == "test-scoring")
        )

    def concurrent_registration(
        bundle: ModelBundle, frame: pd.DataFrame
    ) -> tuple[AssetPrediction, ...]:
        predictions = original_predict(bundle, frame)
        with Session(engine) as session, session.begin():
            session.add(
                ModelRun(
                    model_version="newer-passing",
                    trained_at=datetime.now(UTC),
                    data_hash=original_hash,
                    features=list(FEATURE_COLUMNS),
                    metrics={"quality_gate_passed": 1, "pr_auc_lift": 0.001},
                    git_sha="c" * 40,
                )
            )
        return predictions

    monkeypatch.setattr(predictor, "score_features", concurrent_registration)
    try:
        with pytest.raises(ScoringConflict, match="newer passing model"):
            rescore(engine, scoring_data)
        assert snapshot(engine) == previous
    finally:
        with Session(engine) as session, session.begin():
            session.execute(delete(ModelRun).where(ModelRun.model_version == "newer-passing"))
