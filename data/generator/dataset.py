"""Coordinate the pure generators and hash their canonical, synthetic records."""

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime

from data.generator.assets import generate_assets
from data.generator.config import GeneratorConfig
from data.generator.outages import generate_outages
from data.generator.records import AssetRecord, OutageRecord, WeatherRecord
from data.generator.weather import generate_weather


def json_default(value: object) -> str:
    if isinstance(value, date | datetime):
        return value.isoformat()
    raise TypeError(f"Unsupported canonical data type: {type(value).__name__}")


@dataclass(frozen=True, slots=True)
class SyntheticDataset:
    config: GeneratorConfig
    assets: tuple[AssetRecord, ...]
    weather: tuple[WeatherRecord, ...]
    outages: tuple[OutageRecord, ...]

    def canonical_bytes(self) -> bytes:
        """Stable ordering, explicit dates, and finite rounded values for reproducibility."""
        return json.dumps(
            asdict(self),
            default=json_default,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")

    def data_hash(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


def generate_dataset(config: GeneratorConfig) -> SyntheticDataset:
    """No database, network, file, wall-clock, or global-random side effects."""
    assets = generate_assets(config)
    weather = generate_weather(config, assets)
    outages = generate_outages(config, assets, weather)
    return SyntheticDataset(config, assets, weather, outages)
