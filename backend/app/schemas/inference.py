"""Explicit provenance and limitations of synthetic-demo inference on uploaded assets."""

from typing import Literal

from pydantic import Field

from app.schemas.base import ApiModel

type InferenceWarning = Literal[
    "SYNTHETIC_HISTORY",
    "NO_ASSET_OUTAGE_HISTORY",
    "OUTSIDE_TRAINING_EXTENT",
    "IMPUTED_ATTRIBUTES",
    "UNAVAILABLE_FEEDER_ANCHOR",
]


class ScoringProvenance(ApiModel):
    training_data_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    inference_data_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    imputation_policy: Literal["per-type-median-v1"] = "per-type-median-v1"
    defaults_accepted: bool
    history_context: Literal["synthetic_demo"] = "synthetic_demo"


class InferenceDetails(ApiModel):
    provenance: ScoringProvenance | None = None
    imputed_fields: list[str] = Field(default_factory=list)
    imputed_values: dict[str, float | str] = Field(default_factory=dict)
    warnings: list[InferenceWarning] = Field(default_factory=list)
