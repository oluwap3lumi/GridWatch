"""SQL access for model registration, guarded against a changed training corpus."""

from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.models import ModelRun
from app.repositories.seed import data_fingerprint


def register_run(
    session: Session,
    *,
    version: str,
    trained_at: datetime,
    data_hash: str,
    features: list[str],
    metrics: dict[str, float | int],
    git_sha: str,
) -> ModelRun:
    if not session.in_transaction():
        raise ValueError("Model registration requires an explicit transaction")
    session.execute(text("SELECT pg_advisory_xact_lock(5139241308840342595)"))
    if data_fingerprint(session) != data_hash:
        raise ValueError("Training corpus changed during fitting; run make train again")
    run = ModelRun(
        model_version=version,
        trained_at=trained_at,
        data_hash=data_hash,
        features=features,
        metrics=metrics,
        git_sha=git_sha,
    )
    session.add(run)
    session.flush()
    return run


def recent_runs(session: Session, limit: int = 2) -> list[ModelRun]:
    return list(
        session.scalars(
            select(ModelRun).order_by(ModelRun.trained_at.desc(), ModelRun.id.desc()).limit(limit)
        )
    )


def latest_passing_run(session: Session) -> ModelRun | None:
    return session.scalar(
        select(ModelRun)
        .where(
            ModelRun.metrics["quality_gate_passed"].as_integer() == 1,
            ModelRun.metrics["pr_auc_lift"].as_float() > 0,
        )
        .order_by(ModelRun.trained_at.desc(), ModelRun.id.desc())
        .limit(1)
    )
