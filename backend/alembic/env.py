"""Migration environment; database credentials come from process environment."""

from alembic import context
from app.core.settings import Settings
from app.db.models import Base
from app.db.session import make_engine


def include_object(
    obj: object, name: str | None, kind: str, reflected: bool, compare_to: object | None
) -> bool:
    """Compare only GridWatch tables; preserve PostGIS/tiger/topology extension tables."""
    return kind != "table" or name in Base.metadata.tables


def run_migrations() -> None:
    """Support online migrations and offline SQL without storing connection secrets."""
    settings = Settings.from_env()
    if context.is_offline_mode():
        context.configure(
            url=settings.database_url, target_metadata=Base.metadata, literal_binds=True
        )
        with context.begin_transaction():
            context.run_migrations()
    else:
        engine = make_engine(settings)
        try:
            with engine.connect() as connection:
                context.configure(
                    connection=connection,
                    target_metadata=Base.metadata,
                    compare_type=True,
                    include_object=include_object,
                )
                with context.begin_transaction():
                    context.run_migrations()
        finally:
            engine.dispose()


run_migrations()
