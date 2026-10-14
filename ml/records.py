"""Database-independent immutable training inputs."""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

type AssetKind = Literal["feeder", "transformer", "pole"]
type Coordinate = tuple[float, float]


@dataclass(frozen=True, slots=True)
class AssetInput:
    id: int
    kind: AssetKind
    feeder_id: int | None
    install_date: date
    capacity_kva: float
    load_factor: float
    vegetation_index: float
    location: Coordinate


@dataclass(frozen=True, slots=True)
class WeatherInput:
    observed_at: datetime
    location: Coordinate
    rainfall_mm: float
    wind_kph: float
    lightning_density: float


@dataclass(frozen=True, slots=True)
class OutageInput:
    asset_id: int
    started_at: datetime
    location: Coordinate


@dataclass(frozen=True, slots=True)
class TrainingInputs:
    assets: tuple[AssetInput, ...]
    weather: tuple[WeatherInput, ...]
    outages: tuple[OutageInput, ...]
    data_hash: str
