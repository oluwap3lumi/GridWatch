"""Pure synthetic asset generation, clustered along invented feeder paths."""

import math
import random
from dataclasses import replace
from datetime import timedelta

from data.generator.config import GeneratorConfig
from data.generator.records import AssetRecord, AssetType, Coordinate


def bounded_point(config: GeneratorConfig, x: float, y: float) -> Coordinate:
    west, south, east, north = config.bbox
    return round(min(east, max(west, x)), 6), round(min(north, max(south, y)), 6)


def generate_assets(config: GeneratorConfig) -> tuple[AssetRecord, ...]:
    """Keep random state local and provide deterministic IDs and feeder parentage."""
    rng = random.Random(config.seed + 101)
    west, south, east, north = config.bbox
    columns = math.ceil(math.sqrt(config.feeder_count))
    rows = math.ceil(config.feeder_count / columns)
    width, height = (east - west) / columns, (north - south) / rows
    assets: list[AssetRecord] = []
    for index in range(config.feeder_count):
        cx = west + (index % columns + 0.5) * width
        cy = south + (index // columns + 0.5) * height
        direction = rng.choice((-1, 1))
        coordinates = tuple(
            bounded_point(
                config,
                cx + (step / 5 - 0.5) * width * 0.8,
                cy
                + direction * (step / 5 - 0.5) * height * 0.65
                + rng.uniform(-height * 0.04, height * 0.04),
            )
            for step in range(6)
        )
        age = rng.uniform(8, 50)
        installed = config.as_of - timedelta(days=int(age * 365.25))
        assets.append(
            AssetRecord(
                id=index + 1,
                type="feeder",
                feeder_id=None,
                coordinates=coordinates,
                install_date=installed,
                capacity_kva=0,
                load_factor=0.8,
                material=rng.choice(("aluminium", "copper")),
                vegetation_index=round(min(1, 0.05 + age / 60 * 0.8), 4),
                last_maintenance_date=config.as_of - timedelta(days=rng.randrange(30, 700)),
            )
        )
    feeders = tuple(assets)
    for index in range(config.asset_count - config.feeder_count):
        parent = feeders[index % config.feeder_count]
        kind: AssetType = "transformer" if index < config.transformer_count else "pole"
        position = rng.uniform(0, 5)
        segment = min(4, int(position))
        fraction = position - segment
        ax, ay = parent.coordinates[segment]
        bx, by = parent.coordinates[segment + 1]
        spread = min(width, height) * (0.009 if kind == "transformer" else 0.002)
        location = bounded_point(
            config,
            ax + (bx - ax) * fraction + rng.gauss(0, spread),
            ay + (by - ay) * fraction + rng.gauss(0, spread),
        )
        parent_age = (config.as_of - parent.install_date).days / 365.25
        age = min(55, max(0.1, rng.gauss(parent_age * (0.75 if kind == "transformer" else 1), 7)))
        installed = config.as_of - timedelta(days=int(age * 365.25))
        maintenance = max(installed, config.as_of - timedelta(days=rng.randrange(15, 900)))
        vegetation = min(1, max(0, 0.05 + age / 60 * 0.75 + rng.uniform(-0.12, 0.12)))
        load = min(1.7, max(0.25, rng.gauss(0.7 + age / 100, 0.22)))
        material = "steel" if kind == "transformer" else rng.choice(("wood", "concrete", "steel"))
        assets.append(
            AssetRecord(
                id=config.feeder_count + index + 1,
                type=kind,
                feeder_id=parent.id,
                coordinates=(location,),
                install_date=installed,
                capacity_kva=float(rng.choice((100, 250, 500, 750, 1000)))
                if kind == "transformer"
                else 0,
                load_factor=round(load, 4),
                material=material,
                vegetation_index=round(vegetation, 4),
                last_maintenance_date=maintenance,
            )
        )
    for index, feeder in enumerate(feeders):
        transformers = [
            asset
            for asset in assets
            if asset.feeder_id == feeder.id and asset.type == "transformer"
        ]
        capacity = sum(asset.capacity_kva for asset in transformers)
        load = (
            sum(asset.capacity_kva * asset.load_factor for asset in transformers) / capacity
            if capacity
            else 0
        )
        assets[index] = replace(feeder, capacity_kva=capacity, load_factor=round(load, 4))
    return tuple(assets)
