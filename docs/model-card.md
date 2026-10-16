# Model card

## Intended use and data

GridWatch is a portfolio demonstration of temporal prediction, GIS, model
provenance, and explanations. It is not validated for utility operations.
All examples use the deterministic synthetic corpus from `data/generator`:
3,000 invented assets, 14,600 weather observations, and 4,608 outages over 730
days ending 2025-12-31. Coordinates lie in a Lagos-area bounding box but do not
identify real infrastructure. No real utility, customer, or employer data is used.
See the [data dictionary](data-dictionary.md) for units and generation assumptions.

## Target, features, and temporal evaluation

The prediction target is at least one outage in the
30 days beginning at a monthly UTC cutoff. Features use only strictly earlier
events and weather, with at least 365 days of available history before a cutoff.
Training, tuning, probability calibration, and final validation are chronological;
label windows crossing a partition boundary are purged. The final two months are
held out from selection and fitting.

Features include asset age, load stress, vegetation, log capacity, asset type,
trailing-year outage count, previous-30-day rainfall/wind/lightning aggregates,
weather coverage, and distance to a prior outage in the previous year. Distance is
a spherical approximation in meters, capped at 50 km with a separate missing-data
flag. Static synthetic attributes are assumed unchanged throughout the simulation.
Maintenance dates are excluded because their stored values may postdate a cutoff.

The default corpus uses January–July 2025 for training, August for hyperparameter
selection, September–October for sigmoid probability calibration, and
November–December for final validation. The same assets can appear in successive
months: this measures future prediction on an existing fleet, not generalisation
to unseen assets. Logistic regression uses scaled features and selects C from
0.01, 0.1, 1, 10. CPU XGBoost selects depth 1/2/3 and 100/300/600 trees using only
tuning average precision (learning rate 0.03, minimum child weight 20, L2 10).
Both estimators remain fitted exclusively on the training months. Calibration
uses frozen estimators and its own labels; neither estimator sees validation labels.

Initial Docker evaluation of the default synthetic corpus (5,979 validation
asset-months, 323 positive labels, prevalence 0.054022):

| Metric | Logistic regression | XGBoost |
| --- | ---: | ---: |
| PR-AUC (average precision) | 0.078531 | 0.079324 |
| ROC-AUC | 0.603961 | 0.603519 |
| Brier score (lower is better) | 0.050803 | 0.050842 |
| Precision at top 5% (k=299) | 0.093645 | 0.103679 |
| Calibration error, 10 equal-width bins | 0.007285 | 0.007490 |

The PR-AUC gain is only 0.000793 absolute and does not establish statistical
significance or superiority across metrics. No real utility performance has
been measured. These scores must not guide live maintenance decisions.
The selected XGBoost has depth 1 and 100 trees; the baseline uses C=0.1.
Exact TreeSHAP contributions explain the uncalibrated XGBoost log-odds, not
additive changes to calibrated probabilities. Global importance uses 512
deterministically spaced validation rows.

`make train` stores each fitted bundle (both calibrated estimators and raw XGBoost)
with metrics, reliability bins, SHAP importance, feature schema/configuration,
locked dependency versions, source Git SHA, UTC timestamp, and the SHA-256 of all
persisted training source rows including geometry. Uploaded assets and their
associated outages are excluded from default training. `model_runs` records the same provenance
and numerical metrics. Registration takes the seed loader's advisory lock and
rechecks the data hash; a changed corpus rejects registration and removes the new
artifacts. Earlier versions are preserved. Files are checksummed before reload.
`make verify-train` compares two same-data, same-revision runs and their reloaded
validation predictions. Exact bitwise reproducibility is tested within the same
locked CPU environment; results can differ across package versions/platforms.

Limitations: correlated asset-month rows, just two holdout months, no confidence
intervals, sparse outages, synthetic and largely additive daily failure rules,
static load/vegetation values, and no future weather forecast. Historical outage
locations include the scored asset's own previous outages. Weather is assigned
from the closest available station to the asset's feeder midpoint. Missing weather
uses zeros plus coverage count; nearest-outage distances use a spherical rather
than spheroidal approximation. TreeSHAP describes associations, not causal effects.
No protected/customer attributes or real utility records are used.

M3 scoring uses the same feature contract at the next UTC day after the latest
weather observation, with a 30-day horizon. The default prediction cutoff is
2026-01-01. The actual scoring time is recorded separately. Approved synthetic
demo bands use 0.05, 0.08, and 0.10 boundaries; these are not operational thresholds.
`risk_scores` stores calibrated probabilities and up to five strongest signed
TreeSHAP factors in raw log-odds units. Those factors do not sum to the calibrated
probability and must not be interpreted as causal effects. See [the API contract](api.md).

## M8 inference on uploaded assets

The existing synthetic model can produce illustrative scores for uploaded assets.
This adds no evidence of accuracy on real infrastructure. The runtime retains
the strict model/training hash check, reads uploaded assets in the same database
snapshot, and records a separate inference hash including import revisions.
Concurrent source changes or model replacement prevent the score transaction
from replacing a consistent saved batch.

Missing installation date, capacity, load factor, and vegetation can use per-type
medians from the verified synthetic training corpus **only with explicit opt-in**.
Installation dates use the nearest integer day to the median date ordinal.
Defaults are calculated once per type, in memory, and never written into uploaded
source attributes or fitted from uploaded data. Scores identify every defaulted
field and applied value and carry `history_context=synthetic_demo`. Material and maintenance date
are not inputs to the current model and are not imputed.

Weather and prior outage context still come from the synthetic demonstration.
An uploaded asset with no matched historic outage has a zero outage count; that
means missing asset history rather than proof of reliability, and is explicitly
flagged. Features outside the training asset extent are flagged. These flags do
not establish calibration, geographic coverage or real-world suitability inside
that extent. Assets installed on or after the historical prediction cutoff remain
unscored; their dates are never silently backdated. An unavailable feeder anchor
uses the point asset's own location with a diagnostic.

LineStrings retain their historical midpoint feature location. MultiLineString
feeders use PostGIS `ST_PointOnSurface`; the hotspot repository uses the same
representative point. Uploaded asset geometry and nullable source values remain
available unchanged through the main map API.
