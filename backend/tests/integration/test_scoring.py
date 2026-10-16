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

from app.api.dependencies import get_artifact_root, get_engine
from app.core.errors import ModelUnavailable, ScoringConflict, ScoringDefaultsRequired
from app.db.models import (
    Asset,
    ImportBatch,
    ImportChange,
    ImportJob,
    ImportRow,
    ModelRun,
    OutageEvent,
    RiskScore,
    WeatherObservation,
)
from app.main import app
from app.repositories.model_runs import register_run
from app.repositories.risk import risk_summary, scoring_lock
from app.repositories.seed import replace_demo_data
from app.repositories.training import read_training_inputs
from app.schemas.assets import AssetCollection, AssetDetail
from app.schemas.risk import HotspotCollection, ModelInfo, RescoreResponse, RiskSummary
from app.services.artifacts import save_artifacts
from app.services.risk_policy import risk_band
from app.services.scoring import rescore
from app.services.train import dependency_versions
from tests.integration.test_read_api import request


@pytest.fixture
def imported_scoring(scoring_data: Path, engine: Engine, tmp_path: Path, monkeypatch):
    from app.core.uploads import UploadSettings
    from app.services.upload_storage import UploadStorage

    monkeypatch.setenv("MODEL_ARTIFACT_DIR", str(scoring_data))
    monkeypatch.setenv("UPLOAD_STAGING_DIR", str(tmp_path))
    yield scoring_data, UploadStorage(UploadSettings.from_env())
    with Session(engine) as session, session.begin():
        session.execute(delete(RiskScore))
        session.execute(delete(Asset).where(Asset.batch_id.is_not(None)))
        for model in (ImportChange, ImportRow, ImportJob, ImportBatch):
            session.execute(delete(model))


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
    app.dependency_overrides[get_engine] = lambda: engine
    app.dependency_overrides[get_artifact_root] = lambda: trained_registry
    try:
        yield trained_registry
    finally:
        app.dependency_overrides.clear()
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


def test_risk_and_model_http_contracts(scoring_data: Path, engine: Engine) -> None:
    status, payload = request("/api/v1/model")
    assert status == 200
    model = ModelInfo.model_validate(payload)
    assert model.model_version == "test-scoring" and model.scored_model_version is None
    assert len(model.feature_importance) == 16
    assert [item.mean_absolute_contribution for item in model.feature_importance] == sorted(
        (item.mean_absolute_contribution for item in model.feature_importance), reverse=True
    )
    status, payload = request("/api/v1/risk/rescore", method="POST")
    assert status == 200
    result = RescoreResponse.model_validate(payload)
    status, payload = request("/api/v1/risk/summary")
    summary = RiskSummary.model_validate(payload)
    assert status == 200 and summary.scored_assets == 3000
    assert summary.counts_by_band == result.counts_by_band
    assert summary.scoring is not None and summary.scoring.model_version == model.model_version
    _, payload = request("/api/v1/assets", {"band": "critical", "min_risk": 0.10, "limit": 500})
    assets = AssetCollection.model_validate(payload)
    assert assets.pagination.total == result.counts_by_band.critical
    assert all(
        feature.properties.risk is not None and feature.properties.risk.score >= 0.10
        for feature in assets.features
    )
    _, payload = request("/api/v1/assets/21")
    detail = AssetDetail.model_validate(payload)
    assert detail.asset.properties.risk is not None
    assert detail.asset.properties.risk.prediction_cutoff == result.prediction_cutoff
    status, payload = request("/api/v1/risk/hotspots", {"limit": 500})
    clusters = HotspotCollection.model_validate(payload)
    assert status == 200 and clusters.radius_m == 500
    assert clusters.features
    assert all(feature.properties.asset_count >= 3 for feature in clusters.features)
    assert request("/api/v1/risk/hotspots", {"bbox": "0,0,1,1"})[1]["features"] == []
    assert request("/api/v1/risk/hotspots", {"limit": 501})[0] == 422
    assert request("/api/v1/model")[1]["scored_model_version"] == "test-scoring"
    with scoring_lock(engine):
        assert request("/api/v1/risk/rescore", method="POST")[0] == 409


def test_http_corrupt_registry_and_failed_newest_model(scoring_data: Path, engine: Engine) -> None:
    with Session(engine) as session, session.begin():
        run = session.scalar(select(ModelRun).where(ModelRun.model_version == "test-scoring"))
        assert run is not None
        session.add(
            ModelRun(
                model_version="newer-failed",
                trained_at=datetime.now(UTC),
                data_hash=run.data_hash,
                features=run.features,
                git_sha="c" * 40,
                metrics={"quality_gate_passed": 0, "pr_auc_lift": -0.001},
            )
        )
    try:
        assert request("/api/v1/model")[1]["model_version"] == "test-scoring"
        metadata = scoring_data / "test-scoring" / "metadata.json"
        original = metadata.read_bytes()
        try:
            metadata.write_text("{}")
            assert request("/api/v1/model")[0] == 503
            assert request("/api/v1/risk/rescore", method="POST")[0] == 503
        finally:
            metadata.write_bytes(original)
    finally:
        with Session(engine) as session, session.begin():
            session.execute(delete(ModelRun).where(ModelRun.model_version == "newer-failed"))


def test_uploaded_csv_background_scoring_keeps_training_separate(
    imported_scoring, engine: Engine
) -> None:
    from app.api.v1.imports import commit, undo
    from app.repositories.import_jobs import process_one
    from app.repositories.imports import detail
    from app.schemas.imports import CommitImport
    from tests.integration.test_import_lifecycle import start

    root, storage = imported_scoring
    rescore(engine, root)
    seeded_scores = snapshot(engine)
    with Session(engine) as session, session.begin():
        original = read_training_inputs(session)
    identifier = start(engine, storage, b"external_id,lat,lon\nT-demo,6.5,3.3\n")
    commit(identifier, engine, CommitImport(rescore=True, accept_scoring_defaults=True))
    assert process_one(engine, storage) and process_one(engine, storage)
    with Session(engine) as session:
        result = detail(session, identifier)
        assert result.status == "imported" and result.job.status == "completed", (
            result.job.error_code
        )
        asset = session.scalar(select(Asset).where(Asset.external_id == "T-demo"))
        assert (
            asset.install_date is None and asset.capacity_kva is None and asset.load_factor is None
        )
        asset_id = asset.id
        score = session.get(RiskScore, asset_id)
        assert 0 <= score.score <= 1 and score.top_factors
        assert set(score.inference_metadata["imputed_fields"]) == {
            "install_date",
            "capacity_kva",
            "load_factor",
            "vegetation_index",
        }
        provenance = score.inference_metadata["provenance"]
        assert set(score.inference_metadata["imputed_values"]) == set(
            score.inference_metadata["imputed_fields"]
        )
        assert provenance["training_data_hash"] == original.data_hash
        assert provenance["inference_data_hash"] != original.data_hash
        assert provenance["defaults_accepted"] is True
        summary = risk_summary(session)
        assert summary.scored_assets == 3001
        assert summary.by_feeder[-1].feeder_id is None and summary.by_feeder[-1].total_assets == 1
    assert snapshot(engine)[:3000] == seeded_scores
    with Session(engine) as session, session.begin():
        training = read_training_inputs(session)
        assert training.data_hash == original.data_hash and len(training.assets) == 3000
        assert asset_id not in {a.id for a in training.assets}
    with Session(engine) as session, session.begin():
        # Registering a synthetic run still compares the training-only snapshot.
        register_run(
            session,
            version="ignored-upload-run",
            trained_at=datetime.now(UTC),
            data_hash=original.data_hash,
            features=list(FEATURE_COLUMNS),
            metrics={},
            git_sha="c" * 40,
        )
        session.execute(delete(ModelRun).where(ModelRun.model_version == "ignored-upload-run"))
    status, payload = request(f"/api/v1/assets/{asset_id}")
    view = AssetDetail.model_validate(payload)
    assert status == 200 and view.asset.properties.capacity_kva is None
    assert "SYNTHETIC_HISTORY" in view.asset.properties.risk.warnings
    assert view.asset.properties.risk.provenance == summary.scoring.provenance
    undo(identifier, engine)
    process_one(engine, storage)
    with Session(engine) as session:
        assert not session.scalars(select(RiskScore)).first()
    assert rescore(engine, root).scored_assets == 3000


def test_default_consent_failure_is_explicit_and_preserves_saved_scores(
    imported_scoring, engine: Engine
) -> None:
    from app.api.v1.imports import commit
    from app.repositories.import_jobs import process_one
    from app.repositories.imports import detail
    from app.schemas.imports import CommitImport
    from tests.integration.test_import_lifecycle import start

    root, storage = imported_scoring
    identifier = start(engine, storage, b"external_id,lat,lon\nT-demo,6.5,3.3\n")
    commit(identifier, engine, CommitImport(rescore=True))
    process_one(engine, storage)
    process_one(engine, storage)
    with Session(engine) as session:
        result = detail(session, identifier)
        assert result.status == "imported" and result.job.error_code == "SCORING_DEFAULTS_REQUIRED"
    rescore(engine, root, accept_scoring_defaults=True)
    saved = snapshot(engine)
    with pytest.raises(ScoringDefaultsRequired):
        rescore(engine, root)
    assert snapshot(engine) == saved
    status, payload = request("/api/v1/risk/rescore", method="POST")
    assert status == 409 and "Explicitly accept" in payload["detail"]


@pytest.mark.parametrize("layer", ["pole", "feeder_line"])
@pytest.mark.parametrize("format", ["geojson", "shapefile"])
def test_uploaded_spatial_formats_score_and_multipart_hotspots_work(
    imported_scoring, engine: Engine, layer: str, format: str
) -> None:
    import json

    from pyproj import CRS

    from app.api.v1.imports import commit
    from app.repositories.import_jobs import process_one
    from app.repositories.risk import hotspots
    from app.schemas.imports import CommitImport
    from tests.integration.test_import_lifecycle import start
    from tests.unit.test_import_parsing import packed, shape_members

    root, storage = imported_scoring
    if format == "shapefile":
        data = packed(
            shape_members(prj=CRS.from_epsg(32631).to_wkt().encode(), lines=layer == "feeder_line")
        )
        filename = "network.zip"
    else:
        geometry = (
            {"type": "Point", "coordinates": [3.3, 6.5]}
            if layer == "pole"
            else {
                "type": "MultiLineString",
                "coordinates": [[[3.3, 6.5], [3.31, 6.51]], [[3.32, 6.5], [3.33, 6.51]]],
            }
        )
        data = json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {"type": "Feature", "properties": {"external_id": "001"}, "geometry": geometry}
                ],
            }
        ).encode()
        filename = "network.geojson"
    identifier = start(engine, storage, data, filename, layer)
    commit(identifier, engine, CommitImport())
    process_one(engine, storage)
    result = rescore(engine, root, accept_scoring_defaults=True)
    assert result.scored_assets == 3001 and result.unscored_assets == 0
    with Session(engine) as session, session.begin():
        asset = session.scalar(select(Asset).where(Asset.batch_id == identifier))
        score = session.get(RiskScore, asset.id)
        assert score.top_factors and score.inference_metadata["imputed_fields"]
        assert "SYNTHETIC_HISTORY" in score.inference_metadata["warnings"]
        if format == "shapefile":
            assert "OUTSIDE_TRAINING_EXTENT" in score.inference_metadata["warnings"]
        score.score, score.band = 0.12, "critical"
        session.flush()
        # Ensure an elevated MultiLineString reaches the geography clustering path.
        assert hotspots(session, limit=500, offset=0).type == "FeatureCollection"
        summary = risk_summary(session)
        assert summary.by_feeder[-1].feeder_id == (None if layer == "pole" else asset.id)


def test_import_revision_change_during_scoring_is_rejected(
    imported_scoring, engine: Engine, monkeypatch
) -> None:
    import ml.predict as predictor

    from app.api.v1.imports import commit
    from app.repositories.import_jobs import process_one
    from app.schemas.imports import CommitImport
    from tests.integration.test_import_lifecycle import start

    root, storage = imported_scoring
    identifier = start(engine, storage, b"external_id,lat,lon\nT-demo,6.5,3.3\n")
    commit(identifier, engine, CommitImport())
    process_one(engine, storage)
    rescore(engine, root, accept_scoring_defaults=True)
    saved = snapshot(engine)
    original_predict = predictor.score_features

    def concurrent_change(bundle, frame):
        values = original_predict(bundle, frame)
        with Session(engine) as session, session.begin():
            # Identical values, but a new asset revision must still fence the old snapshot.
            session.execute(
                text("UPDATE assets SET load_factor=load_factor WHERE batch_id=:id"),
                {"id": identifier},
            )
        return values

    monkeypatch.setattr(predictor, "score_features", concurrent_change)
    with pytest.raises(ScoringConflict, match="changed while scoring"):
        rescore(engine, root, accept_scoring_defaults=True)
    assert snapshot(engine) == saved


def test_future_import_is_unscored_and_http_consent_is_honoured(
    imported_scoring, engine: Engine
) -> None:
    from app.api.v1.imports import commit
    from app.repositories.import_jobs import process_one
    from app.schemas.imports import CommitImport
    from tests.integration.test_import_lifecycle import start

    _, storage = imported_scoring
    identifier = start(
        engine,
        storage,
        b"external_id,lat,lon,install_date\nnew,6.5,3.3,2027-01-01\nunknown,6.5,3.3,\n",
    )
    commit(identifier, engine, CommitImport())
    process_one(engine, storage)
    assert request("/api/v1/risk/rescore", method="POST", body={})[0] == 409
    status, payload = request(
        "/api/v1/risk/rescore", method="POST", body={"accept_scoring_defaults": True}
    )
    result = RescoreResponse.model_validate(payload)
    assert status == 200 and result.scored_assets == 3001 and result.unscored_assets == 1
    assert result.unscored_by_reason == {"NOT_INSTALLED_AT_CUTOFF": 1}
    assert result.provenance.defaults_accepted is True
    with Session(engine) as session:
        future = session.scalar(select(Asset).where(Asset.external_id == "new"))
        assert session.get(RiskScore, future.id) is None
        summary = risk_summary(session)
        assert (
            summary.by_feeder[-1].total_assets == 2 and summary.by_feeder[-1].unscored_assets == 1
        )
