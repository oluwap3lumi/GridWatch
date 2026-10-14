"""Pure historical features and future labels, with explicit UTC prediction cutoffs."""

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from ml.records import Coordinate, TrainingInputs, WeatherInput

type FloatArray = NDArray[np.float64]

FEATURE_COLUMNS = (
    "asset_age_years",
    "load_stress",
    "vegetation_index",
    "capacity_log_kva",
    "is_feeder",
    "is_transformer",
    "is_pole",
    "outage_count_365d",
    "rainfall_mean_30d",
    "rainfall_max_30d",
    "wind_mean_30d",
    "wind_max_30d",
    "lightning_mean_30d",
    "weather_days_30d",
    "nearest_prior_outage_m",
    "prior_outage_available",
)
FEATURE_SCHEMA_VERSION = "monthly-history-v1"


@dataclass(frozen=True)
class FeatureConfig:
    horizon_days: int = 30
    history_days: int = 365
    weather_days: int = 30

    def __post_init__(self) -> None:
        if not 1 <= self.horizon_days <= 90:
            raise ValueError("horizon_days must be between 1 and 90")
        if self.history_days != 365 or self.weather_days != 30:
            raise ValueError(
                "This feature schema requires 365-day history and a 30-day weather window"
            )


def utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Prediction and observation timestamps must be timezone-aware")
    return value.astimezone(UTC)


def distances_m(points: tuple[Coordinate, ...], references: tuple[Coordinate, ...]) -> FloatArray:
    """Vectorized spherical distances in meters; inputs are EPSG:4326 lon/lat."""
    left = np.radians(np.asarray(points, dtype=np.float64))
    right = np.radians(np.asarray(references, dtype=np.float64))
    dlon = right[None, :, 0] - left[:, None, 0]
    dlat = right[None, :, 1] - left[:, None, 1]
    term = (
        np.sin(dlat / 2) ** 2
        + np.cos(left[:, None, 1]) * np.cos(right[None, :, 1]) * np.sin(dlon / 2) ** 2
    )
    return np.asarray(2 * 6371008.8 * np.arcsin(np.sqrt(np.clip(term, 0, 1))), dtype=np.float64)


def nearest_distances(
    points: tuple[Coordinate, ...], references: tuple[Coordinate, ...]
) -> FloatArray:
    """Bound intermediate memory and distinguish no historical outage using a separate flag."""
    if not references:
        return np.full(len(points), 50000.0, dtype=np.float64)
    unique = tuple(sorted(set(references)))
    result = np.empty(len(points), dtype=np.float64)
    for start in range(0, len(points), 256):
        result[start : start + 256] = np.minimum(
            50000, distances_m(points[start : start + 256], unique).min(axis=1)
        )
    return result


def build_features(inputs: TrainingInputs, cutoff: datetime, config: FeatureConfig) -> pd.DataFrame:
    """Use only [cutoff-history, cutoff) events and [cutoff-weather, cutoff) observations."""
    cutoff = utc(cutoff)
    eligible = tuple(
        sorted((a for a in inputs.assets if a.install_date < cutoff.date()), key=lambda a: a.id)
    )
    if not eligible:
        raise ValueError("No assets installed before the prediction cutoff")
    past = tuple(
        event
        for event in inputs.outages
        if cutoff - timedelta(days=config.history_days) <= utc(event.started_at) < cutoff
    )
    counts = Counter(event.asset_id for event in past)
    historical_weather = tuple(
        w
        for w in inputs.weather
        if cutoff - timedelta(days=config.weather_days) <= utc(w.observed_at) < cutoff
    )
    stations: dict[Coordinate, list[WeatherInput]] = defaultdict(list)
    for record in historical_weather:
        stations[record.location].append(record)
    station_locations = tuple(sorted(stations))
    assets_by_id = {asset.id: asset for asset in inputs.assets}
    anchors = tuple(assets_by_id[asset.feeder_id or asset.id].location for asset in eligible)
    station_ids = (
        distances_m(anchors, station_locations).argmin(axis=1) if station_locations else None
    )
    nearest = nearest_distances(
        tuple(asset.location for asset in eligible), tuple(event.location for event in past)
    )
    rows: list[dict[str, object]] = []
    for index, asset in enumerate(eligible):
        weather = (
            stations[station_locations[int(station_ids[index])]] if station_ids is not None else []
        )
        rain = [w.rainfall_mm for w in weather]
        wind = [w.wind_kph for w in weather]
        lightning = [w.lightning_density for w in weather]
        rows.append(
            {
                "asset_id": asset.id,
                "cutoff": cutoff,
                "asset_age_years": (cutoff.date() - asset.install_date).days / 365.25,
                "load_stress": max(0, asset.load_factor - 0.75),
                "vegetation_index": asset.vegetation_index,
                "capacity_log_kva": float(np.log1p(asset.capacity_kva)),
                "is_feeder": int(asset.kind == "feeder"),
                "is_transformer": int(asset.kind == "transformer"),
                "is_pole": int(asset.kind == "pole"),
                "outage_count_365d": counts[asset.id],
                "rainfall_mean_30d": sum(rain) / len(rain) if rain else 0,
                "rainfall_max_30d": max(rain, default=0),
                "wind_mean_30d": sum(wind) / len(wind) if wind else 0,
                "wind_max_30d": max(wind, default=0),
                "lightning_mean_30d": sum(lightning) / len(lightning) if lightning else 0,
                "weather_days_30d": len({utc(w.observed_at).date() for w in weather}),
                "nearest_prior_outage_m": float(nearest[index]),
                "prior_outage_available": int(bool(past)),
            }
        )
    return pd.DataFrame(rows)


def monthly_cutoffs(inputs: TrainingInputs, config: FeatureConfig) -> tuple[datetime, ...]:
    """Keep only monthly cutoffs with a full warmup and fully observed future label window."""
    if not inputs.weather:
        raise ValueError("Training requires weather history")
    first = min(utc(w.observed_at) for w in inputs.weather) + timedelta(days=config.history_days)
    end = max(utc(w.observed_at) for w in inputs.weather) + timedelta(days=1)
    cursor = datetime(first.year, first.month, 1, tzinfo=UTC)
    dates = []
    while cursor + timedelta(days=config.horizon_days) <= end:
        if cursor >= first:
            dates.append(cursor)
        cursor = datetime(cursor.year + (cursor.month == 12), cursor.month % 12 + 1, 1, tzinfo=UTC)
    if not dates:
        raise ValueError("Not enough data for history plus a complete future target window")
    return tuple(dates)


def build_training_frame(inputs: TrainingInputs, config: FeatureConfig) -> pd.DataFrame:
    """Keep labels separate from the explicitly listed numeric feature columns."""
    frames = []
    for cutoff in monthly_cutoffs(inputs, config):
        frame = build_features(inputs, cutoff, config)
        end = cutoff + timedelta(days=config.horizon_days)
        positives = {
            event.asset_id for event in inputs.outages if cutoff <= utc(event.started_at) < end
        }
        frame["target"] = frame["asset_id"].isin(positives).astype(int)
        frame["target_end"] = end
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)
