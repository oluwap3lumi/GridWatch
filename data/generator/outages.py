"""Synthetic outages whose likelihood depends on asset and storm stress."""

import random
from datetime import timedelta

from data.generator.config import GeneratorConfig
from data.generator.records import AssetRecord, OutageRecord, WeatherRecord


def event_probability(
    age_years: float,
    load_factor: float,
    vegetation_index: float,
    rainfall_mm: float,
    wind_kph: float,
    lightning_density: float,
) -> float:
    """Synthetic per-day probability, not a calibrated real utility risk estimate."""
    probability = (
        0.00012
        + 0.0012 * min(1, max(0, age_years / 50))
        + 0.0022 * max(0, load_factor - 0.75)
        + 0.001 * vegetation_index
        + 0.004 * min(1, rainfall_mm / 100)
        + 0.003 * max(0, min(1, wind_kph / 100) - 0.25)
        + 0.0003 * min(1, lightning_density / 10)
    )
    return min(0.04, max(0, probability))


def generate_outages(
    config: GeneratorConfig,
    assets: tuple[AssetRecord, ...],
    weather: tuple[WeatherRecord, ...],
) -> tuple[OutageRecord, ...]:
    """Simulate daily exposure after installation, sharing each feeder's weather scenario."""
    rng = random.Random(config.seed + 303)
    groups: dict[int, list[AssetRecord]] = {}
    for asset in assets:
        groups.setdefault(asset.feeder_id or asset.id, []).append(asset)
    outages: list[OutageRecord] = []
    for observation in weather:
        for asset in groups[observation.feeder_id]:
            age = (observation.observed_at.date() - asset.install_date).days / 365.25
            if age < 0:
                continue
            probability = event_probability(
                age,
                asset.load_factor,
                asset.vegetation_index,
                observation.rainfall_mm,
                observation.wind_kph,
                observation.lightning_density,
            )
            multiplier = {"feeder": 0.35, "transformer": 1.3, "pole": 0.7}[asset.type]
            if rng.random() >= probability * multiplier:
                continue
            if observation.wind_kph > 50 or observation.rainfall_mm > 50:
                cause = (
                    "lightning"
                    if observation.lightning_density > 7 and rng.random() < 0.3
                    else "storm"
                )
            elif asset.vegetation_index > 0.6 and rng.random() < 0.5:
                cause = "vegetation"
            elif asset.load_factor > 1.05 and rng.random() < 0.6:
                cause = "overload"
            else:
                cause = "equipment"
            duration = min(1200, rng.lognormvariate(3.6, 0.6) + age * 0.8 + observation.wind_kph)
            outages.append(
                OutageRecord(
                    id=len(outages) + 1,
                    asset_id=asset.id,
                    started_at=observation.observed_at + timedelta(minutes=rng.randrange(1440)),
                    duration_min=round(duration, 2),
                    cause=cause,
                    location=asset.location,
                )
            )
    return tuple(outages)
