"""Run provenance is recorded transactionally and stale training snapshots are rejected."""

from datetime import UTC, datetime

import pytest
from data.generator.config import GeneratorConfig
from data.generator.dataset import generate_dataset
from ml.features import FEATURE_COLUMNS
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import ModelRun
from app.repositories.model_runs import recent_runs, register_run
from app.repositories.seed import replace_demo_data


def test_registration_rejects_changed_data_and_records_provenance(session: Session) -> None:
    dataset = generate_dataset(
        GeneratorConfig(asset_count=60, feeder_count=4, transformer_count=12, days=30)
    )
    session.begin()
    seeded = replace_demo_data(session, dataset)
    timestamp = datetime.now(UTC)
    with pytest.raises(ValueError, match="changed"):
        register_run(
            session,
            version="stale",
            trained_at=timestamp,
            data_hash="a" * 64,
            features=list(FEATURE_COLUMNS),
            metrics={"pr_auc": 0.1},
            git_sha="b" * 40,
        )
    assert session.scalar(select(func.count()).select_from(ModelRun)) == 0
    register_run(
        session,
        version="test-model",
        trained_at=timestamp,
        data_hash=seeded.database_hash,
        features=list(FEATURE_COLUMNS),
        metrics={"pr_auc": 0.1},
        git_sha="b" * 40,
    )
    run = recent_runs(session)[0]
    assert run.model_version == "test-model"
    assert run.trained_at == timestamp
    assert run.data_hash == seeded.database_hash
    assert run.features == list(FEATURE_COLUMNS)
    assert run.metrics == {"pr_auc": 0.1}
    assert run.git_sha == "b" * 40
