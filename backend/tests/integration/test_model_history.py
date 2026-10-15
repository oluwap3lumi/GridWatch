"""Registered version history is paginated independently of artifact availability."""

from datetime import UTC, datetime

from sqlalchemy import Engine, delete
from sqlalchemy.orm import Session

from app.api.dependencies import get_engine
from app.db.models import ModelRun
from app.main import app
from app.schemas.risk import ModelHistory
from tests.integration.test_read_api import request


def test_history_empty_failed_runs_pagination_and_validation(engine: Engine) -> None:
    app.dependency_overrides[get_engine] = lambda: engine
    versions = ["history-pass", "history-fail", "history-inconsistent"]
    try:
        status, body = request("/api/v1/model/history")
        assert status == 200
        assert ModelHistory.model_validate(body).items == []
        with Session(engine) as session, session.begin():
            for index, version in enumerate(versions):
                session.add(
                    ModelRun(
                        model_version=version,
                        trained_at=datetime(2026, 1, 1, tzinfo=UTC),
                        data_hash="a" * 64,
                        git_sha="b" * 40,
                        features=["asset_age_years"],
                        metrics={
                            "quality_gate_passed": int(index != 1),
                            "pr_auc_lift": 0.1 if index == 0 else -0.1,
                        },
                    )
                )
                session.flush()
        status, body = request("/api/v1/model/history", {"limit": 2})
        assert status == 200
        first = ModelHistory.model_validate(body)
        assert [item.model_version for item in first.items] == versions[:0:-1]
        assert not any(item.quality_gate_passed for item in first.items)
        assert first.pagination.total == 3 and first.pagination.next_offset == 2
        status, body = request("/api/v1/model/history", {"limit": 2, "offset": 2})
        assert status == 200
        last = ModelHistory.model_validate(body)
        assert last.items[0].model_version == versions[0]
        assert last.items[0].quality_gate_passed
        assert last.items[0].data_hash == "a" * 64
        assert last.pagination.next_offset is None
        assert request("/api/v1/model/history", {"limit": 501})[0] == 422
        assert request("/api/v1/model/history", {"offset": -1})[0] == 422
        status, body = request("/api/v1/model/history", {"offset": 10})
        assert status == 200 and body["items"] == []
    finally:
        app.dependency_overrides.clear()
        with Session(engine) as session, session.begin():
            session.execute(delete(ModelRun).where(ModelRun.model_version.in_(versions)))
