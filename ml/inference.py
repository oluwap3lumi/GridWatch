"""Pure, opt-in inference defaults derived only from the verified training corpus."""

from collections import Counter
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from statistics import median

from ml.features import utc
from ml.records import AssetInput, AssetKind, Coordinate, TrainingInputs

POLICY = "per-type-median-v1"
FIELDS = ("install_date", "capacity_kva", "load_factor", "vegetation_index")


class DefaultsRequired(ValueError):
    """An uploaded eligible asset lacks at least one model input."""


@dataclass(frozen=True)
class ImportedAssetInput:
    id: int
    kind: AssetKind
    feeder_id: int | None
    install_date: date | None
    capacity_kva: float | None
    load_factor: float | None
    vegetation_index: float | None
    location: Coordinate


@dataclass(frozen=True)
class PreparedInference:
    inputs: TrainingInputs
    imputed_fields: dict[int, tuple[str, ...]]
    imputed_values: dict[int, dict[str, float | str]]
    warnings: dict[int, tuple[str, ...]]
    unscored_by_reason: dict[str, int]


def prepare_inference(
    training: TrainingInputs,
    imported: tuple[ImportedAssetInput, ...],
    cutoff: datetime,
    *,
    accept_defaults: bool,
) -> PreparedInference:
    """Never modify source attributes or use uploaded records to calculate defaults."""
    cutoff = utc(cutoff)
    reference = tuple(asset for asset in training.assets if asset.install_date < cutoff.date())
    if not reference:
        raise ValueError("No eligible reference corpus for inference")
    west = min(asset.location[0] for asset in reference)
    east = max(asset.location[0] for asset in reference)
    south = min(asset.location[1] for asset in reference)
    north = max(asset.location[1] for asset in reference)
    historical_ids = {
        event.asset_id
        for event in training.outages
        if cutoff - timedelta(days=365) <= utc(event.started_at) < cutoff
    }
    by_kind = {
        kind: tuple(asset for asset in reference if asset.kind == kind)
        for kind in {asset.kind for asset in reference}
    }
    defaults = {
        kind: (
            date.fromordinal(round(median(asset.install_date.toordinal() for asset in group))),
            float(median(asset.capacity_kva for asset in group)),
            float(median(asset.load_factor for asset in group)),
            float(median(asset.vegetation_index for asset in group)),
        )
        for kind, group in by_kind.items()
    }
    assets = list(training.assets)
    imputed: dict[int, tuple[str, ...]] = {}
    applied_values: dict[int, dict[str, float | str]] = {}
    warnings: dict[int, tuple[str, ...]] = {}
    skipped: Counter[str] = Counter()
    skipped["NOT_INSTALLED_AT_CUTOFF"] = sum(
        asset.install_date >= cutoff.date() for asset in assets
    )
    for asset in imported:
        if asset.install_date is not None and asset.install_date >= cutoff.date():
            skipped["NOT_INSTALLED_AT_CUTOFF"] += 1
            continue
        missing = tuple(field for field in FIELDS if getattr(asset, field) is None)
        if missing and not accept_defaults:
            raise DefaultsRequired("SCORING_DEFAULTS_REQUIRED")
        if missing and asset.kind not in defaults:
            raise ValueError("No assets of this type in the verified reference corpus")
        installed = asset.install_date or defaults[asset.kind][0]
        capacity = asset.capacity_kva if asset.capacity_kva is not None else defaults[asset.kind][1]
        load = asset.load_factor if asset.load_factor is not None else defaults[asset.kind][2]
        vegetation = (
            asset.vegetation_index
            if asset.vegetation_index is not None
            else defaults[asset.kind][3]
        )
        assets.append(
            AssetInput(
                asset.id,
                asset.kind,
                asset.feeder_id,
                installed,
                capacity,
                load,
                vegetation,
                asset.location,
            )
        )
        imputed[asset.id] = missing
        applied_values[asset.id] = {}
        for field in missing:
            value = getattr(assets[-1], field)
            applied_values[asset.id][field] = (
                value.isoformat() if isinstance(value, date) else float(value)
            )
        notes = ["SYNTHETIC_HISTORY"]
        if asset.id not in historical_ids:
            notes.append("NO_ASSET_OUTAGE_HISTORY")
        if not (west <= asset.location[0] <= east and south <= asset.location[1] <= north):
            notes.append("OUTSIDE_TRAINING_EXTENT")
        if missing:
            notes.append("IMPUTED_ATTRIBUTES")
        warnings[asset.id] = tuple(notes)
    eligible_ids = {asset.id for asset in assets if asset.install_date < cutoff.date()}
    for prepared_asset in assets:
        if (
            prepared_asset.id in warnings
            and prepared_asset.feeder_id is not None
            and prepared_asset.feeder_id not in eligible_ids
        ):
            warnings[prepared_asset.id] += ("UNAVAILABLE_FEEDER_ANCHOR",)
    return PreparedInference(
        replace(training, assets=tuple(assets)),
        imputed,
        applied_values,
        warnings,
        {key: count for key, count in skipped.items() if count},
    )
