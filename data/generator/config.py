"""Validated, fixed-date synthetic generator configuration."""

import math
import os
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class GeneratorConfig:
    """Counts include feeders; dates never depend on the wall clock."""

    seed: int = 42
    asset_count: int = 3000
    feeder_count: int = 20
    transformer_count: int = 700
    days: int = 730
    as_of: date = date(2025, 12, 31)
    bbox: tuple[float, float, float, float] = (3.25, 6.42, 3.55, 6.65)

    def __post_init__(self) -> None:
        if self.seed < 0:
            raise ValueError("seed must be nonnegative")
        if not 1 <= self.feeder_count < self.asset_count:
            raise ValueError("feeder_count must be positive and smaller than asset_count")
        if not 0 <= self.transformer_count <= self.asset_count - self.feeder_count:
            raise ValueError("transformer_count exceeds the number of point assets")
        if not 1 <= self.days <= 3650:
            raise ValueError("days must be between 1 and 3650")
        west, south, east, north = self.bbox
        if not all(math.isfinite(value) for value in self.bbox):
            raise ValueError("bbox must contain finite coordinates")
        if not (-180 <= west < east <= 180 and -90 < south < north < 90):
            raise ValueError("bbox must be ordered west,south,east,north in EPSG:4326")
        if self.as_of.year < 1900:
            raise ValueError("as_of must be in or after 1900")

    @classmethod
    def from_env(cls) -> "GeneratorConfig":
        """Read optional overrides; an absent override uses the deterministic defaults."""
        values = tuple(
            float(value) for value in os.getenv("SEED_BBOX", "3.25,6.42,3.55,6.65").split(",")
        )
        if len(values) != 4:
            raise ValueError("SEED_BBOX must contain four comma-separated coordinates")
        return cls(
            seed=int(os.getenv("SEED_RANDOM", "42")),
            asset_count=int(os.getenv("SEED_ASSET_COUNT", "3000")),
            feeder_count=int(os.getenv("SEED_FEEDER_COUNT", "20")),
            transformer_count=int(os.getenv("SEED_TRANSFORMER_COUNT", "700")),
            days=int(os.getenv("SEED_DAYS", "730")),
            as_of=date.fromisoformat(os.getenv("SEED_AS_OF", "2025-12-31")),
            bbox=(values[0], values[1], values[2], values[3]),
        )
