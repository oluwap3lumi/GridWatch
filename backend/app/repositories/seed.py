"""All database access for atomic loading and verification of synthetic demo data."""

import hashlib
from dataclasses import dataclass

from data.generator.dataset import SyntheticDataset
from geoalchemy2 import WKTElement
from sqlalchemy import delete, func, insert, select, text
from sqlalchemy.orm import Session

from app.db.models import Asset, ImportBatch, ModelRun, OutageEvent, RiskScore, WeatherObservation


@dataclass(frozen=True)
class SeedResult:
    assets: int
    weather: int
    outages: int
    data_hash: str
    database_hash: str


def data_fingerprint(session: Session) -> str:
    """Hash persisted source values in ID order; import bookkeeping is not model input."""
    session.execute(text("SET LOCAL TIME ZONE 'UTC'"))
    digest = hashlib.sha256()
    for table in ("assets", "weather_obs", "outage_events"):
        digest.update((table + "\n").encode())
        # Table names are a fixed allowlist, never input from users or the generator.
        # New import bookkeeping is not model input. Preserve existing model hashes.
        projection = (
            "(to_jsonb(d) - ARRAY['external_id','external_feeder_id','external_pole_id',"
            "'pole_id','batch_id','last_batch_id','revision'])::text"
            if table == "assets"
            else "to_jsonb(d)::text"
        )
        records = session.execute(text(f"SELECT {projection} FROM {table} d ORDER BY id"))
        for value in records.scalars():
            digest.update(value.encode("utf-8") + b"\n")
    return digest.hexdigest()


def insert_rows(
    session: Session,
    model: type[Asset] | type[WeatherObservation] | type[OutageEvent],
    rows: list[dict[str, object]],
) -> None:
    """Keep statement sizes bounded and use geometry bind parameters, not SQL strings."""
    for offset in range(0, len(rows), 1000):
        session.execute(
            insert(model).execution_options(render_nulls=True), rows[offset : offset + 1000]
        )


def replace_demo_data(session: Session, dataset: SyntheticDataset) -> SeedResult:
    """Replace only demo tables inside the caller's transaction; preserve trained-model data."""
    if not session.in_transaction():
        raise ValueError("Seeding requires an explicit transaction")
    session.execute(text("SELECT pg_advisory_xact_lock(5139241308840342595)"))
    if session.scalar(select(func.count()).select_from(ImportBatch)):
        raise ValueError("Cannot reseed a database containing private import history")
    if session.scalar(select(func.count()).select_from(ModelRun)) or session.scalar(
        select(func.count()).select_from(RiskScore)
    ):
        raise ValueError(
            "Cannot reseed a database containing model runs or risk scores; "
            "use a separate demo database"
        )
    session.execute(delete(OutageEvent))
    session.execute(delete(WeatherObservation))
    session.execute(delete(Asset))
    asset_rows: list[dict[str, object]] = [
        {
            "id": asset.id,
            "type": asset.type,
            "feeder_id": asset.feeder_id,
            "geom": WKTElement(asset.geom, srid=4326),
            "install_date": asset.install_date,
            "capacity_kva": asset.capacity_kva,
            "load_factor": asset.load_factor,
            "material": asset.material,
            "vegetation_index": asset.vegetation_index,
            "last_maintenance_date": asset.last_maintenance_date,
        }
        for asset in dataset.assets
    ]
    # Insert parent feeders first, so the parent-type trigger sees committed statement results.
    insert_rows(session, Asset, [row for row in asset_rows if row["type"] == "feeder"])
    insert_rows(session, Asset, [row for row in asset_rows if row["type"] != "feeder"])
    insert_rows(
        session,
        WeatherObservation,
        [
            {
                "id": record.id,
                "observed_at": record.observed_at,
                "geom": WKTElement(record.geom, srid=4326),
                "rainfall_mm": record.rainfall_mm,
                "wind_kph": record.wind_kph,
                "temp_c": record.temp_c,
                "lightning_density": record.lightning_density,
            }
            for record in dataset.weather
        ],
    )
    insert_rows(
        session,
        OutageEvent,
        [
            {
                "id": record.id,
                "asset_id": record.asset_id,
                "started_at": record.started_at,
                "duration_min": record.duration_min,
                "cause": record.cause,
                "geom": WKTElement(record.geom, srid=4326),
            }
            for record in dataset.outages
        ],
    )
    counts = (
        int(session.scalar(select(func.count()).select_from(Asset)) or 0),
        int(session.scalar(select(func.count()).select_from(WeatherObservation)) or 0),
        int(session.scalar(select(func.count()).select_from(OutageEvent)) or 0),
    )
    expected = (len(dataset.assets), len(dataset.weather), len(dataset.outages))
    if counts != expected:
        raise RuntimeError(f"Loaded counts {counts} do not match generated counts {expected}")
    session.execute(text("SELECT setval('asset_id_seq', (SELECT max(id) FROM assets) + 1, false)"))
    return SeedResult(
        *counts, data_hash=dataset.data_hash(), database_hash=data_fingerprint(session)
    )
