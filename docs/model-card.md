# Model card

M2 is under implementation. The prediction target is at least one outage in the
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
