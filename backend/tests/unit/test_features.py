"""Boundary and leakage tests use tiny synthetic histories, never utility data."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import numpy as np
import pandas as pd
import pytest
from ml.features import (
    FEATURE_COLUMNS,
    FeatureConfig,
    build_features,
    build_training_frame,
    distances_m,
    monthly_cutoffs,
)
from ml.records import AssetInput, OutageInput, TrainingInputs, WeatherInput
from ml.split import temporal_split

CUTOFF = datetime(2025, 1, 1, tzinfo=UTC)


def inputs() -> TrainingInputs:
    asset = AssetInput(1, "feeder", None, date(2000, 1, 1), 10000, 1.2, 0.6, (3.3, 6.5))
    weather = WeatherInput(CUTOFF - timedelta(days=1), asset.location, 10, 20, 2)
    outage = OutageInput(1, CUTOFF - timedelta(days=1), asset.location)
    return TrainingInputs((asset,), (weather,), (outage,), "a" * 64)


def test_only_past_data_changes_features() -> None:
    original = inputs()
    future = replace(
        original,
        weather=(
            *original.weather,
            replace(original.weather[0], observed_at=CUTOFF, rainfall_mm=999),
        ),
        outages=(*original.outages, replace(original.outages[0], started_at=CUTOFF)),
    )
    first = build_features(original, CUTOFF, FeatureConfig())
    pd.testing.assert_frame_equal(first, build_features(future, CUTOFF, FeatureConfig()))
    assert first.iloc[0]["outage_count_365d"] == 1
    assert first.iloc[0]["rainfall_mean_30d"] == 10
    assert first.iloc[0]["load_stress"] == pytest.approx(0.45)
    assert first.iloc[0]["nearest_prior_outage_m"] == 0
    assert "target" not in FEATURE_COLUMNS and "asset_id" not in FEATURE_COLUMNS


def test_window_left_boundary_and_missing_history_are_explicit() -> None:
    original = inputs()
    event = replace(original.outages[0], started_at=CUTOFF - timedelta(days=365))
    frame = build_features(replace(original, outages=(event,)), CUTOFF, FeatureConfig())
    assert frame.iloc[0]["outage_count_365d"] == 1
    empty = build_features(replace(original, outages=(), weather=()), CUTOFF, FeatureConfig())
    assert empty.iloc[0]["nearest_prior_outage_m"] == 50000
    assert empty.iloc[0]["prior_outage_available"] == 0
    assert empty.iloc[0]["weather_days_30d"] == 0
    assert np.isfinite(empty.loc[:, list(FEATURE_COLUMNS)].to_numpy(dtype=float)).all()


def test_distance_units_and_not_yet_installed_assets() -> None:
    distance = distances_m(((0, 0),), ((0, 1),))[0, 0]
    assert distance == pytest.approx(111195, rel=0.001)
    asset = replace(inputs().assets[0], id=2, install_date=date(2025, 1, 2))
    frame = build_features(
        replace(inputs(), assets=(*inputs().assets, asset)), CUTOFF, FeatureConfig()
    )
    assert list(frame.asset_id) == [1]


def test_cutoffs_require_full_history_and_complete_labels() -> None:
    original = inputs()
    weather = tuple(
        replace(
            original.weather[0], observed_at=datetime(2024, 1, 2, tzinfo=UTC) + timedelta(days=i)
        )
        for i in range(730)
    )
    cutoffs = monthly_cutoffs(replace(original, weather=weather), FeatureConfig())
    assert cutoffs[0] == CUTOFF
    assert cutoffs[-1] == datetime(2025, 12, 1, tzinfo=UTC)
    with pytest.raises(ValueError, match="timezone"):
        build_features(original, datetime(2025, 1, 1), FeatureConfig())


def test_labels_include_cutoff_but_exclude_horizon_end() -> None:
    original = inputs()
    weather = tuple(
        replace(
            original.weather[0], observed_at=datetime(2024, 1, 2, tzinfo=UTC) + timedelta(days=i)
        )
        for i in range(730)
    )
    event = replace(original.outages[0], started_at=CUTOFF + timedelta(days=30))
    source = replace(original, weather=weather, outages=(event,))
    frame = build_training_frame(source, FeatureConfig())
    assert frame[frame.cutoff == CUTOFF].iloc[0].target == 0
    frame = build_training_frame(
        replace(source, outages=(replace(event, started_at=CUTOFF),)), FeatureConfig()
    )
    january = frame[frame.cutoff == CUTOFF].iloc[0]
    assert january.target == 1
    assert january.outage_count_365d == 0


def test_temporal_split_purges_overlapping_labels() -> None:
    rows = []
    for month in range(1, 13):
        cutoff = datetime(2025, month, 1, tzinfo=UTC)
        for target in (0, 1):
            rows.append(
                {
                    "cutoff": cutoff,
                    "target_end": cutoff + timedelta(days=45 if month == 7 else 30),
                    "target": target,
                }
            )
    groups = temporal_split(pd.DataFrame(rows))
    for left, right in zip(
        (groups.train, groups.tune, groups.calibration),
        (groups.tune, groups.calibration, groups.validation),
        strict=True,
    ):
        assert left.target_end.max() <= right.cutoff.min()
    assert groups.validation.cutoff.min() == datetime(2025, 11, 1, tzinfo=UTC)
    assert datetime(2025, 7, 1, tzinfo=UTC) not in set(groups.train.cutoff)
