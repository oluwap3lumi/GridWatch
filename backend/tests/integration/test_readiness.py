"""Readiness requires the migrated serving schema, while liveness stays independent."""

from alembic.config import Config
from sqlalchemy import Engine

from alembic import command
from app.api.dependencies import get_engine
from app.main import app
from app.repositories.readiness import database_ready
from app.schemas.operations import MetricsResponse
from tests.integration.test_read_api import request


def test_readiness_checks_postgis_migrations_and_metrics(engine: Engine) -> None:
    app.dependency_overrides[get_engine] = lambda: engine
    try:
        assert database_ready(engine)
        assert request("/api/v1/ready") == (200, {"status": "ready"})
        command.downgrade(Config("alembic.ini"), "0001")
        assert not database_ready(engine)
        assert request("/api/v1/ready") == (503, {"status": "not_ready"})
        assert request("/api/v1/health") == (200, {"status": "ok"})
        status, body = request("/api/v1/metrics")
        assert status == 200
        observed = MetricsResponse.model_validate(body)
        assert observed.scope == "process" and observed.requests > 0
        assert any(
            row.route == "/api/v1/ready" and row.status_code == 503 for row in observed.routes
        )
    finally:
        command.upgrade(Config("alembic.ini"), "head")
        app.dependency_overrides.clear()
    assert database_ready(engine)
