"""Read consistent training inputs from PostGIS; ML functions never access a database."""

from typing import TYPE_CHECKING, cast

from ml.records import AssetInput, AssetKind, OutageInput, TrainingInputs, WeatherInput
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.repositories.seed import data_fingerprint
from app.repositories.spatial import ASSET_POINT

if TYPE_CHECKING:
    from ml.inference import ImportedAssetInput


def read_training_inputs(session: Session) -> TrainingInputs:
    """Begin with a repeatable read-only snapshot, then hash and read that same corpus."""
    session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
    data_hash = data_fingerprint(session, training_only=True)
    assets = tuple(
        AssetInput(
            id=int(row.id),
            kind=cast(AssetKind, row.type),
            feeder_id=row.feeder_id,
            install_date=row.install_date,
            capacity_kva=float(row.capacity_kva),
            load_factor=float(row.load_factor),
            vegetation_index=float(row.vegetation_index),
            location=(float(row.lon), float(row.lat)),
        )
        for row in session.execute(
            text(
                "SELECT a.id,a.type,a.feeder_id,a.install_date,a.capacity_kva,"
                "a.load_factor,a.vegetation_index, "
                f"ST_X({ASSET_POINT}) AS lon, ST_Y({ASSET_POINT}) AS lat "
                "FROM assets a WHERE a.batch_id IS NULL ORDER BY a.id"
            )
        )
    )
    weather = tuple(
        WeatherInput(
            observed_at=row.observed_at,
            location=(float(row.lon), float(row.lat)),
            rainfall_mm=float(row.rainfall_mm),
            wind_kph=float(row.wind_kph),
            lightning_density=float(row.lightning_density),
        )
        for row in session.execute(
            text(
                "SELECT observed_at,ST_X(geom) AS lon,ST_Y(geom) AS lat,"
                "rainfall_mm,wind_kph,lightning_density "
                "FROM weather_obs ORDER BY id"
            )
        )
    )
    outages = tuple(
        OutageInput(
            asset_id=int(row.asset_id),
            started_at=row.started_at,
            location=(float(row.lon), float(row.lat)),
        )
        for row in session.execute(
            text(
                "SELECT asset_id,started_at,ST_X(geom) AS lon,ST_Y(geom) AS lat "
                "FROM outage_events o WHERE EXISTS (SELECT 1 FROM assets a "
                "WHERE a.id=o.asset_id AND a.batch_id IS NULL) ORDER BY id"
            )
        )
    )
    if not assets or not weather or not outages:
        raise ValueError("Training data is empty; run make seed before make train")
    return TrainingInputs(assets, weather, outages, data_hash)


def read_imported_assets(session: Session) -> tuple["ImportedAssetInput", ...]:
    """Use the caller's repeatable-read snapshot; nullable source values remain nullable."""
    from ml.inference import ImportedAssetInput

    return tuple(
        ImportedAssetInput(
            id=row.id,
            kind=cast(AssetKind, row.type),
            feeder_id=row.feeder_id,
            install_date=row.install_date,
            capacity_kva=row.capacity_kva,
            load_factor=row.load_factor,
            vegetation_index=row.vegetation_index,
            location=(float(row.lon), float(row.lat)),
        )
        for row in session.execute(
            text(
                "SELECT a.id,a.type,a.feeder_id,a.install_date,a.capacity_kva,"
                f"a.load_factor,a.vegetation_index,ST_X({ASSET_POINT}) AS lon,"
                f"ST_Y({ASSET_POINT}) AS lat "
                "FROM assets a WHERE a.batch_id IS NOT NULL ORDER BY a.id"
            )
        )
    )
