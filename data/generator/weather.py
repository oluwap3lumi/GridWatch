"""Seeded daily scenarios with seasonal rain and shared regional storms."""

import math
import random
from datetime import UTC, datetime, timedelta

from data.generator.config import GeneratorConfig
from data.generator.records import AssetRecord, WeatherRecord


def generate_weather(
    config: GeneratorConfig, assets: tuple[AssetRecord, ...]
) -> tuple[WeatherRecord, ...]:
    """Invent one station at each feeder's central vertex; never fetch real observations."""
    rng = random.Random(config.seed + 202)
    feeders = tuple(asset for asset in assets if asset.type == "feeder")
    start = config.as_of - timedelta(days=config.days - 1)
    observations: list[WeatherRecord] = []
    for day in range(config.days):
        observed = start + timedelta(days=day)
        wetness = (1 + math.sin((observed.timetuple().tm_yday - 90) / 365.25 * math.tau)) / 2
        storm = rng.random() < 0.08 + 0.1 * wetness
        rainfall = (
            rng.gammavariate(3, 25)
            if storm
            else (rng.gammavariate(2, 6) if rng.random() < 0.6 * wetness else 0)
        )
        wind = 14 + 7 * wetness + (48 if storm else 0)
        temperature = 32 - 4 * wetness - (3 if storm else 0)
        for feeder in feeders:
            observations.append(
                WeatherRecord(
                    id=len(observations) + 1,
                    feeder_id=feeder.id,
                    observed_at=datetime(observed.year, observed.month, observed.day, tzinfo=UTC),
                    location=feeder.location,
                    rainfall_mm=round(min(450, rainfall * rng.uniform(0.65, 1.35)), 3),
                    wind_kph=round(min(150, max(0, rng.gauss(wind, 6))), 3),
                    temp_c=round(min(42, max(18, rng.gauss(temperature, 1.5))), 3),
                    lightning_density=round(rng.uniform(2, 12) if storm else 0, 3),
                )
            )
    return tuple(observations)
