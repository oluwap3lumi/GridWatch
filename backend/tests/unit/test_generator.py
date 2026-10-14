"""Check synthetic invariants, reproducibility, clustering, and failure signal."""

import math
import random
from datetime import date
from statistics import correlation

import pytest
from data.generator.config import GeneratorConfig
from data.generator.dataset import generate_dataset
from data.generator.outages import event_probability


def small_config(seed: int = 42) -> GeneratorConfig:
    return GeneratorConfig(
        seed=seed, asset_count=160, feeder_count=4, transformer_count=40, days=90
    )


def test_reproducible_bytes_hash_and_no_global_rng_changes() -> None:
    state = random.getstate()
    first = generate_dataset(small_config())
    second = generate_dataset(small_config())
    assert first.canonical_bytes() == second.canonical_bytes()
    assert first.data_hash() == second.data_hash()
    assert first.data_hash() != generate_dataset(small_config(43)).data_hash()
    assert random.getstate() == state


def test_counts_links_dates_and_geographic_bounds() -> None:
    config = small_config()
    dataset = generate_dataset(config)
    assert len(dataset.assets) == 160
    assert sum(asset.type == "feeder" for asset in dataset.assets) == 4
    assert sum(asset.type == "transformer" for asset in dataset.assets) == 40
    assert sum(asset.type == "pole" for asset in dataset.assets) == 116
    assert len(dataset.weather) == 4 * 90
    feeders = {asset.id for asset in dataset.assets if asset.type == "feeder"}
    assets = {asset.id: asset for asset in dataset.assets}
    west, south, east, north = config.bbox
    for asset in dataset.assets:
        assert (asset.feeder_id is None) == (asset.type == "feeder")
        if asset.type != "feeder":
            assert asset.feeder_id in feeders
        assert asset.install_date <= asset.last_maintenance_date <= config.as_of
        for lon, lat in asset.coordinates:
            assert west <= lon <= east and south <= lat <= north
    for observation in dataset.weather:
        assert observation.observed_at.utcoffset().total_seconds() == 0
        assert 0 <= observation.rainfall_mm <= 450 and 0 <= observation.wind_kph <= 150
    assert dataset.outages
    for outage in dataset.outages:
        assert assets[outage.asset_id].install_date <= outage.started_at.date() <= config.as_of
        assert outage.duration_min > 0
        assert outage.location == assets[outage.asset_id].location


def test_vegetation_correlates_with_age_and_points_cluster_by_feeder() -> None:
    config = small_config()
    assets = generate_dataset(config).assets
    points = [asset for asset in assets if asset.type != "feeder"]
    ages = [(config.as_of - asset.install_date).days for asset in points]
    assert correlation(ages, [asset.vegetation_index for asset in points]) > 0.6
    parents = {asset.id: asset for asset in assets if asset.type == "feeder"}

    def distance_to_line(point: tuple[float, float], parent_id: int) -> float:
        path = parents[parent_id].coordinates
        distances = []
        for start, end in zip(path, path[1:], strict=False):
            dx, dy = end[0] - start[0], end[1] - start[1]
            ratio = max(
                0,
                min(
                    1,
                    ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / (dx * dx + dy * dy),
                ),
            )
            distances.append(math.dist(point, (start[0] + ratio * dx, start[1] + ratio * dy)))
        return min(distances)

    for asset in points:
        assert asset.feeder_id is not None
        distances = {
            parent.id: distance_to_line(asset.location, parent.id) for parent in parents.values()
        }
        assert min(distances, key=lambda key: distances[key]) == asset.feeder_id
        assert distances[asset.feeder_id] < 0.005


def test_generated_events_have_higher_rate_in_storm_weather() -> None:
    config = GeneratorConfig(asset_count=800, feeder_count=8, transformer_count=200, days=180)
    dataset = generate_dataset(config)
    stations = {(record.feeder_id, record.observed_at.date()): record for record in dataset.weather}
    assets = {asset.id: asset for asset in dataset.assets}
    exposures = {False: 0, True: 0}
    events = {False: 0, True: 0}
    for record in dataset.weather:
        storm = record.wind_kph > 50 or record.rainfall_mm > 50
        exposures[storm] += sum(
            (asset.feeder_id or asset.id) == record.feeder_id
            and asset.install_date <= record.observed_at.date()
            for asset in dataset.assets
        )
    for event in dataset.outages:
        asset = assets[event.asset_id]
        record = stations[(asset.feeder_id or asset.id, event.started_at.date())]
        events[record.wind_kph > 50 or record.rainfall_mm > 50] += 1
    assert exposures[True] > 0 and events[False] > 0
    assert events[True] / exposures[True] > 1.5 * events[False] / exposures[False]


@pytest.mark.parametrize("index,value", [(0, 45), (1, 1.4), (2, 0.9), (3, 80), (4, 90), (5, 10)])
def test_failure_probability_increases_with_each_stressor(index: int, value: float) -> None:
    baseline = [5.0, 0.6, 0.1, 0.0, 10.0, 0.0]
    stressed = baseline.copy()
    stressed[index] = value
    assert event_probability(*stressed) > event_probability(*baseline)
    assert 0 < event_probability(*stressed) < 1


@pytest.mark.parametrize(
    "kwargs",
    [
        {"seed": -1},
        {"feeder_count": 0},
        {"transformer_count": 5000},
        {"days": 0},
        {"bbox": (4, 6, 3, 7)},
        {"bbox": (math.nan, 6, 4, 7)},
        {"as_of": date(1800, 1, 1)},
    ],
)
def test_config_rejects_invalid_inputs(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        GeneratorConfig(**kwargs)
