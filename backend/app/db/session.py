"""Explicit engine and session construction; imports do not contact the database."""

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.settings import Settings


def make_engine(settings: Settings) -> Engine:
    """Create a lazy engine using the approved Psycopg 3 driver."""
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_timeout=2,
        connect_args={"connect_timeout": 2},
    )


def session_factory(engine: Engine) -> sessionmaker[Session]:
    """Provide transactional sessions for repositories and application services."""
    return sessionmaker(engine, expire_on_commit=False)
