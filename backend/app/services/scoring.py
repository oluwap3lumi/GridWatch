"""Rescore orchestration; all SQL is delegated to repositories and ML stays pure."""

from datetime import UTC, datetime, time, timedelta
from pathlib import Path

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.core.errors import (
    ModelNotFound,
    ModelUnavailable,
    ScoringConflict,
    ScoringDefaultsRequired,
)
from app.repositories.model_runs import latest_passing_run
from app.repositories.risk import replace_scores, risk_summary, scoring_lock
from app.repositories.seed import data_fingerprint
from app.repositories.training import read_imported_assets, read_training_inputs
from app.schemas.inference import InferenceDetails, ScoringProvenance
from app.schemas.risk import RescoreResponse
from app.services.artifacts import load_artifacts
from app.services.model_registry import registered_documents


def rescore(
    engine: Engine, root: Path, *, accept_scoring_defaults: bool = False
) -> RescoreResponse:
    # Defer native ML imports so startup/OpenAPI/read routes do not load SHAP/XGBoost.
    from ml.features import FEATURE_COLUMNS, FEATURE_SCHEMA_VERSION, build_features, utc
    from ml.inference import DefaultsRequired, prepare_inference
    from ml.predict import score_features

    with scoring_lock(engine):
        with Session(engine, expire_on_commit=False) as session, session.begin():
            try:
                inputs = read_training_inputs(session)
                imported = read_imported_assets(session)
                inference_hash = data_fingerprint(session, include_provenance=True)
            except ValueError as exc:
                raise ScoringConflict(
                    "No complete synthetic source corpus is available; run make seed"
                ) from exc
            run = latest_passing_run(session)
            if run is None:
                raise ModelNotFound("No passing trained model is available; run make train")
        if inputs.data_hash != run.data_hash:
            raise ScoringConflict(
                "Source data does not match the latest passing model; retrain before scoring"
            )
        metadata, _ = registered_documents(root, run)
        if (
            metadata.feature_schema != FEATURE_SCHEMA_VERSION
            or tuple(run.features) != FEATURE_COLUMNS
        ):
            raise ModelUnavailable("Model feature contract is incompatible with this application")
        try:
            bundle = load_artifacts(root, run.model_version)
        except Exception as exc:
            raise ModelUnavailable("Registered model could not be loaded") from exc
        if (
            bundle.feature_config.horizon_days != 30
            or bundle.feature_config.history_days != metadata.training_config.features.history_days
            or bundle.feature_config.weather_days != metadata.training_config.features.weather_days
            or bundle.feature_schema != metadata.feature_schema
            or bundle.feature_names != tuple(metadata.features)
        ):
            raise ModelUnavailable(
                "Saved estimator configuration does not match registered metadata"
            )
        last_day = max(utc(weather.observed_at).date() for weather in inputs.weather)
        cutoff = datetime.combine(last_day + timedelta(days=1), time.min, tzinfo=UTC)
        if cutoff - min(utc(weather.observed_at) for weather in inputs.weather) < timedelta(
            days=365
        ):
            raise ScoringConflict("Scoring requires at least 365 days of historical observations")
        try:
            prepared = prepare_inference(
                inputs, imported, cutoff, accept_defaults=accept_scoring_defaults
            )
        except DefaultsRequired as exc:
            raise ScoringDefaultsRequired(
                "Uploaded assets lack model attributes. Explicitly accept scoring defaults "
                "to use per-type training medians for this synthetic demo."
            ) from exc
        except ValueError as exc:
            raise ScoringConflict(
                "No verified reference values are available for uploaded model inputs"
            ) from exc
        provenance = ScoringProvenance(
            training_data_hash=inputs.data_hash,
            inference_data_hash=inference_hash,
            defaults_accepted=accept_scoring_defaults,
        )
        details = {
            asset_id: InferenceDetails.model_validate(
                {
                    "provenance": provenance.model_dump(),
                    "imputed_fields": list(fields),
                    "imputed_values": prepared.imputed_values[asset_id],
                    "warnings": list(prepared.warnings[asset_id]),
                }
            )
            for asset_id, fields in prepared.imputed_fields.items()
        }
        predictions = score_features(
            bundle, build_features(prepared.inputs, cutoff, bundle.feature_config)
        )
        scored_at = datetime.now(UTC)
        with Session(engine) as session, session.begin():
            replace_scores(
                session,
                predictions=predictions,
                version=run.model_version,
                data_hash=inputs.data_hash,
                inference_hash=inference_hash,
                provenance=provenance,
                inference_details=details,
                cutoff=cutoff,
                scored_at=scored_at,
            )
            summary = risk_summary(session)
        return RescoreResponse(
            model_version=run.model_version,
            scored_at=scored_at,
            prediction_cutoff=cutoff,
            scored_assets=summary.scored_assets,
            unscored_assets=summary.unscored_assets,
            counts_by_band=summary.counts_by_band,
            provenance=provenance,
            unscored_by_reason=prepared.unscored_by_reason,
        )
