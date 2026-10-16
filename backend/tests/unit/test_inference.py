"""Synthetic, pure inference defaults, consent, cutoff and domain diagnostics."""

from dataclasses import replace
from datetime import UTC, date, datetime
from statistics import median

import pandas as pd
import pytest
from data.generator.assets import generate_assets
from data.generator.config import GeneratorConfig
from ml.features import FeatureConfig, build_features
from ml.inference import DefaultsRequired, ImportedAssetInput, prepare_inference
from ml.records import AssetInput, TrainingInputs

CUTOFF = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture
def reference() -> TrainingInputs:
    assets = generate_assets(GeneratorConfig(asset_count=20, feeder_count=2, transformer_count=6))
    return TrainingInputs(
        tuple(
            AssetInput(
                a.id,
                a.type,
                a.feeder_id,
                a.install_date,
                a.capacity_kva,
                a.load_factor,
                a.vegetation_index,
                a.location,
            )
            for a in assets
        ),
        (),
        (),
        "a" * 64,
    )


def uploaded(**kwargs) -> ImportedAssetInput:
    return replace(
        ImportedAssetInput(100, "transformer", None, None, None, None, None, (3.4, 6.5)), **kwargs
    )


def test_no_imports_leave_features_identical(reference: TrainingInputs) -> None:
    prepared = prepare_inference(reference, (), CUTOFF, accept_defaults=False)
    pd.testing.assert_frame_equal(
        build_features(reference, CUTOFF, FeatureConfig()),
        build_features(prepared.inputs, CUTOFF, FeatureConfig()),
    )
    assert not prepared.imputed_fields and not prepared.warnings


def test_defaults_require_consent(reference: TrainingInputs) -> None:
    with pytest.raises(DefaultsRequired):
        prepare_inference(reference, (uploaded(),), CUTOFF, accept_defaults=False)


def test_per_type_medians_preserve_source_and_ignore_other_uploads(
    reference: TrainingInputs,
) -> None:
    original = uploaded()
    outlier = uploaded(
        id=101,
        capacity_kva=999999,
        load_factor=1.5,
        vegetation_index=1.0,
        install_date=date(2025, 1, 1),
    )
    prepared = prepare_inference(reference, (outlier, original), CUTOFF, accept_defaults=True)
    result = next(a for a in prepared.inputs.assets if a.id == 100)
    transformers = [a for a in reference.assets if a.kind == "transformer"]
    assert result.capacity_kva == median(a.capacity_kva for a in transformers)
    assert result.load_factor == median(a.load_factor for a in transformers)
    assert result.vegetation_index == median(a.vegetation_index for a in transformers)
    assert result.install_date.toordinal() == round(
        median(a.install_date.toordinal() for a in transformers)
    )
    assert original.capacity_kva is None and original.install_date is None
    assert set(prepared.imputed_fields[100]) == {
        "install_date",
        "capacity_kva",
        "load_factor",
        "vegetation_index",
    }
    assert "IMPUTED_ATTRIBUTES" in prepared.warnings[100]
    assert prepared.imputed_values[100]["capacity_kva"] == result.capacity_kva
    assert prepared.imputed_values[100]["install_date"] == result.install_date.isoformat()
    assert not prepared.imputed_fields[101]


def test_complete_uploaded_attributes_need_no_median_consent(reference: TrainingInputs) -> None:
    source = uploaded(
        install_date=date(2001, 1, 1), capacity_kva=123, load_factor=0.9, vegetation_index=0.7
    )
    prepared = prepare_inference(reference, (source,), CUTOFF, accept_defaults=False)
    assert prepared.inputs.assets[-1].capacity_kva == 123
    assert prepared.imputed_fields[100] == ()
    assert set(prepared.warnings[100]) == {"SYNTHETIC_HISTORY", "NO_ASSET_OUTAGE_HISTORY"}


def test_future_installation_is_not_backdated_or_imputed(reference: TrainingInputs) -> None:
    prepared = prepare_inference(
        reference, (uploaded(install_date=CUTOFF.date()),), CUTOFF, accept_defaults=False
    )
    assert prepared.inputs.assets == reference.assets
    assert prepared.unscored_by_reason == {"NOT_INSTALLED_AT_CUTOFF": 1}


def test_outside_training_extent_is_explicit(reference: TrainingInputs) -> None:
    prepared = prepare_inference(
        reference, (uploaded(location=(-77.0, 38.0)),), CUTOFF, accept_defaults=True
    )
    assert "OUTSIDE_TRAINING_EXTENT" in prepared.warnings[100]


def test_missing_parent_anchor_uses_asset_location_without_crashing(
    reference: TrainingInputs,
) -> None:
    future = uploaded(id=102, kind="feeder", install_date=date(2027, 1, 1))
    prepared = prepare_inference(
        reference, (future, uploaded(feeder_id=102)), CUTOFF, accept_defaults=True
    )
    assert "UNAVAILABLE_FEEDER_ANCHOR" in prepared.warnings[100]
    assert 100 in build_features(prepared.inputs, CUTOFF, FeatureConfig()).asset_id.values


def test_missing_type_reference_and_naive_cutoff_are_rejected(reference: TrainingInputs) -> None:
    without_poles = replace(
        reference, assets=tuple(a for a in reference.assets if a.kind != "pole")
    )
    with pytest.raises(ValueError, match="type"):
        prepare_inference(without_poles, (uploaded(kind="pole"),), CUTOFF, accept_defaults=True)
    with pytest.raises(ValueError, match="timezone"):
        prepare_inference(reference, (), CUTOFF.replace(tzinfo=None), accept_defaults=True)
