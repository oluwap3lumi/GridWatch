"""Reproducible, invented upload examples derived only from the existing generator."""

import argparse
import csv
import io
import json
import zipfile
from pathlib import Path

import shapefile
from pyproj import CRS, Transformer

from data.generator.assets import generate_assets
from data.generator.config import GeneratorConfig
from data.generator.records import AssetRecord


def external(asset: AssetRecord) -> str:
    return f"sample-{asset.type}-{asset.id}"


def properties(asset: AssetRecord) -> dict[str, str | float]:
    return {
        "external_id": external(asset),
        "capacity_kva": asset.capacity_kva,
        "install_date": asset.install_date.isoformat(),
        "load_factor": min(asset.load_factor, 1.5),
        "last_maintenance_date": asset.last_maintenance_date.isoformat(),
        "material": asset.material,
        "vegetation_index": asset.vegetation_index,
        **({"feeder_id": f"sample-feeder-{asset.feeder_id}"} if asset.feeder_id else {}),
    }


def csv_bytes(rows: list[dict[str, str | float]]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def geojson(assets: tuple[AssetRecord, ...]) -> bytes:
    features = [
        {
            "type": "Feature",
            "properties": properties(asset),
            "geometry": {
                "type": "LineString" if asset.type == "feeder" else "Point",
                "coordinates": asset.coordinates if asset.type == "feeder" else asset.location,
            },
        }
        for asset in assets
    ]
    return (
        json.dumps({"type": "FeatureCollection", "features": features}, indent=2) + "\n"
    ).encode()


def projected_shapefile(poles: tuple[AssetRecord, ...]) -> bytes:
    shp, shx, dbf = io.BytesIO(), io.BytesIO(), io.BytesIO()
    projection = Transformer.from_crs(4326, 32631, always_xy=True)
    with shapefile.Writer(shp=shp, shx=shx, dbf=dbf, shapeType=shapefile.POINT) as writer:
        for field in ("externalid", "feeder_id", "install_da", "last_maint", "material"):
            writer.field(field, "C", size=40)
        for field in ("capacity_k", "load_facto", "vegetation"):
            writer.field(field, "N", size=18, decimal=6)
        for pole in poles:
            values = properties(pole)
            writer.point(*projection.transform(*pole.location))
            writer.record(
                values["external_id"],
                values["feeder_id"],
                values["install_date"],
                values["last_maintenance_date"],
                values["material"],
                values["capacity_kva"],
                values["load_factor"],
                values["vegetation_index"],
            )
    # DBF's last-update header must not depend on the day regeneration runs.
    dbf_data = bytearray(dbf.getvalue())
    dbf_data[1:4] = bytes((125, 12, 31))
    members = {
        "poles.shp": shp.getvalue(),
        "poles.shx": shx.getvalue(),
        "poles.dbf": bytes(dbf_data),
        "poles.prj": CRS.from_epsg(32631).to_wkt(version="WKT1_ESRI").encode(),
        "poles.cpg": b"UTF-8",
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, data in sorted(members.items()):
            entry = zipfile.ZipInfo(name, date_time=(2025, 12, 31, 0, 0, 0))
            entry.create_system = 3  # Stable Unix metadata even when generated on Windows.
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, data)
    return output.getvalue()


def sample_files() -> dict[str, bytes]:
    """Stable IDs intentionally match across formats to demonstrate upserts."""
    assets = generate_assets(GeneratorConfig(asset_count=40, feeder_count=2, transformer_count=10))
    poles = tuple(asset for asset in assets if asset.type == "pole")[:8]
    feeders = tuple(asset for asset in assets if asset.type == "feeder")
    rows = []
    for asset in tuple(asset for asset in assets if asset.type == "transformer")[:8]:
        pole = next(pole for pole in poles if pole.feeder_id == asset.feeder_id)
        rows.append(
            {
                **properties(asset),
                "latitude": asset.location[1],
                "longitude": asset.location[0],
                "pole_id": external(pole),
            }
        )
    broken = [dict(row) for row in rows[:5]]
    broken[1].update(latitude=0, longitude=0)
    broken[2].update(install_date="invalid-date", capacity_kva=-1)
    broken[4]["external_id"] = broken[3]["external_id"]
    return {
        "transformers.csv": csv_bytes(rows),
        "poles.geojson": geojson(poles),
        "feeder_lines.geojson": geojson(feeders),
        "poles_shapefile.zip": projected_shapefile(poles),
        "broken_transformers.csv": csv_bytes(broken),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="Check committed bytes without writing"
    )
    options = parser.parse_args()
    destination = Path(__file__).resolve().parents[1] / "samples"
    if not options.check:
        destination.mkdir(exist_ok=True)
    for name, data in sample_files().items():
        path = destination / name
        if options.check:
            if not path.exists() or path.read_bytes() != data:
                raise SystemExit(f"Synthetic sample needs regeneration: {name}")
        else:
            path.write_bytes(data)
    print("PASS synthetic samples: 5 reproducible files")


if __name__ == "__main__":
    main()
