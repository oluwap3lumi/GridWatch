"""Real PostGIS fixtures confined to the ephemeral Compose test database."""

import os
from collections.abc import Iterator

import pytest
from alembic.config import Config
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from alembic import command
from app.core.settings import Settings
from app.db.session import make_engine


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    if os.getenv("GRIDWATCH_INTEGRATION") != "1":
        pytest.fail("Run integration tests through make test's isolated PostGIS container")
    settings = Settings.from_env()
    assert settings.database_url.database == "gridwatch_test"
    assert settings.database_url.host == "test-db"
    command.upgrade(Config("alembic.ini"), "head")
    database = make_engine(settings)
    yield database
    database.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection, join_transaction_mode="create_savepoint") as database:
            yield database
        transaction.rollback()
