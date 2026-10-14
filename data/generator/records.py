"""Immutable synthetic records; coordinates are always longitude, latitude."""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

type Coordinate = tuple[float, float]
type AssetType = Literal["feeder", "transformer", "pole"]


def point_wkt(location: Coordinate) -> str:
    """Serialize a point without needing a GIS dependency in the generator."""
    return f"POINT({location[0]:.6f} {location[1]:.6f})"


@dataclass(frozen=True, slots=True)
class AssetRecord:
    id: int
    type: AssetType
    feeder_id: int | None
    coordinates: tuple[Coordinate, ...]
    install_date: date
    capacity_kva: float
    load_factor: float
    material: str
    vegetation_index: float
    last_maintenance_date: date

    @property
    def location(self) -> Coordinate:
        """Use the central feeder vertex or the asset's sole point."""
        return self.coordinates[len(self.coordinates) // 2]

    @property
    def geom(self) -> str:
        if self.type == "feeder":
            points = ",".join(f"{x:.6f} {y:.6f}" for x, y in self.coordinates)
            return f"LINESTRING({points})"
        return point_wkt(self.location)


@dataclass(frozen=True, slots=True)
class WeatherRecord:
    id: int
    feeder_id: int  # Generator station identity, not an additional database column.
    observed_at: datetime
    location: Coordinate
    rainfall_mm: float
    wind_kph: float
    temp_c: float
    lightning_density: float

    @property
    def geom(self) -> str:
        return point_wkt(self.location)


@dataclass(frozen=True, slots=True)
class OutageRecord:
    id: int
    asset_id: int
    started_at: datetime
    duration_min: float
    cause: str
    location: Coordinate

    @property
    def geom(self) -> str:
        return point_wkt(self.location)
