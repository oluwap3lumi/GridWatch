"""Bounded readiness checks against the application database and migrated schema."""

from sqlalchemy import Engine, text


def database_ready(engine: Engine) -> bool:
    """Empty migrated databases are ready; seed data and trained models are optional."""
    with engine.connect() as connection, connection.begin():
        connection.execute(text("SET LOCAL statement_timeout = '2000ms'"))
        return bool(
            connection.scalar(
                text("""
            SELECT PostGIS_Version() IS NOT NULL
              AND to_regclass('public.assets') IS NOT NULL
              AND to_regclass('public.risk_scores') IS NOT NULL
              AND to_regclass('public.outage_events') IS NOT NULL
              AND to_regclass('public.weather_obs') IS NOT NULL
              AND to_regclass('public.model_runs') IS NOT NULL
              AND to_regclass('public.import_batches') IS NOT NULL
              AND to_regclass('public.import_jobs') IS NOT NULL
              AND to_regclass('public.import_rows') IS NOT NULL
              AND to_regclass('public.import_changes') IS NOT NULL
              AND EXISTS (SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'risk_scores'
                  AND column_name = 'prediction_cutoff')
              AND EXISTS (SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'risk_scores'
                  AND column_name = 'inference_metadata')
        """)
            )
        )
