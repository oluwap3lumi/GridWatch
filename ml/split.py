"""Pure chronological partitions with label-window purging at every boundary."""

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class TemporalPartitions:
    train: pd.DataFrame
    tune: pd.DataFrame
    calibration: pd.DataFrame
    validation: pd.DataFrame


def temporal_split(frame: pd.DataFrame) -> TemporalPartitions:
    """Reserve 2 months for validation, the previous 2 for calibration, and 1 for tuning."""
    dates = sorted(frame["cutoff"].unique())
    if len(dates) < 8:
        raise ValueError("Need at least 8 monthly cutoffs for train/tune/calibration/validation")
    tune_start, calibration_start, validation_start = dates[-5], dates[-4], dates[-2]
    groups = (
        frame[(frame["cutoff"] < tune_start) & (frame["target_end"] <= tune_start)],
        frame[
            (frame["cutoff"] >= tune_start)
            & (frame["cutoff"] < calibration_start)
            & (frame["target_end"] <= calibration_start)
        ],
        frame[
            (frame["cutoff"] >= calibration_start)
            & (frame["cutoff"] < validation_start)
            & (frame["target_end"] <= validation_start)
        ],
        frame[frame["cutoff"] >= validation_start],
    )
    for group in groups:
        if group.empty or group["target"].nunique() != 2:
            raise ValueError("Every temporal partition must contain both target classes")
    return TemporalPartitions(*(group.reset_index(drop=True) for group in groups))
