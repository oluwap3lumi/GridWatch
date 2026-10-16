# Data dictionary

Only synthetic or public data is permitted. Demo data originates in `data/generator`.

All geometry uses EPSG:4326 and explicit GiST indexes. Feeder assets
are LineStrings; transformers and poles are Points. `assets.feeder_id` links point
assets to a feeder and is null for feeders. A database trigger enforces parent type.
Asset IDs, observation IDs, and outage IDs are deterministic generator-assigned integers.

| Table | Fields and units |
| --- | --- |
| `assets` | id, type, feeder_id, geom, install_date, capacity_kva (kVA), load_factor (ratio, 0–2), material, vegetation_index (0–1), last_maintenance_date |
| `outage_events` | id, asset_id, started_at (UTC), duration_min (minutes), cause, geom (Point) |
| `weather_obs` | id, observed_at (UTC), geom (Point), rainfall_mm (mm), wind_kph (km/h), temp_c (°C), lightning_density (flashes/km²/day) |
| `risk_scores` | asset_id (primary key), score (0–1), band, model_version (foreign key), scored_at (UTC), prediction_cutoff (UTC; nullable legacy rows), top_factors (JSONB) |
| `model_runs` | id, unique model_version, trained_at (UTC), data_hash (SHA-256), features (JSONB string list), metrics (JSONB), git_sha |

Seeding leaves model/risk tables empty; training populates `model_runs`, and
rescoring populates `risk_scores`. Foreign keys and database constraints reject
invalid geometry, asset parentage, date ordering, and physical-value ranges.

The generator defaults to seed 42, 3,000 assets (20 feeders, 700 transformers,
2,280 poles), and 730 daily scenarios ending on 2025-12-31. This creates 14,600
weather records at invented feeder stations inside a Lagos-area bounding box
(3.25, 6.42, 3.55, 6.65). Coordinates describe an invented network, not real assets.
`WeatherRecord.feeder_id` is internal station identity and is not a database field.

Asset points cluster along generated feeder lines. Age and vegetation correlate;
outage probability increases with age, load stress, vegetation, rainfall, wind,
and lightning. Daily storms are shared regionally with local variation. These are
designed demonstration signals, not validated physical models or utility forecasts.
Poles have zero capacity; their load factor is a synthetic feeder-utilization proxy.

Each component uses an independent local seeded PRNG. Canonical JSON includes the
configuration, ordered records, rounded finite values, and ISO dates/timestamps.
SHA-256 identifies that complete corpus. Reproducibility targets the pinned Python
3.12 runtime. No wall clock, external network, or real-world records are inputs.

`make seed` prints `data_hash` for canonical generated records/configuration and
`database_hash` for every persisted row (including geometry) in stable ID order
with UTC timestamps. They identify different representations, so they need not
match each other. Each is stable across identical reloads. Reseeding replaces only
assets/weather/outages in one transaction and refuses to invalidate existing
model runs or risk scores.

`model_runs.data_hash` is the persisted `database_hash`, not the generator's
canonical JSON hash. `metrics` has numeric keys prefixed `baseline_`, `xgboost_`,
and `raw_xgboost_`, plus `pr_auc_lift` and integer `quality_gate_passed` (0/1).
PR-AUC is average precision; precision at top-k uses ceil(5% of validation
asset-month rows). Calibration error uses ten equal-width probability bins.
`features` records the exact ordered feature contract and `git_sha` identifies
the committed training source. Files under `ml/artifacts/<model_version>/`
contain dependency/configuration metadata and detailed evaluation reports.
See [the model card](model-card.md) for target windows, feature limitations, and results.

Migration `0002` adds `risk_scores.prediction_cutoff` (UTC). It is nullable for
legacy rows whose prediction date is unknown; M3 rescoring always populates it.
`scored_at` is the actual UTC time the batch was computed. `top_factors` contains
up to five nonzero factors sorted by absolute contribution: `feature`,
`feature_value`, signed `contribution`, and `contribution_unit = log_odds`.
Contributions describe raw XGBoost output, not calibrated probability changes.

Risk bands use fixed demo probability boundaries: low below 0.05, medium from
0.05 to below 0.08, high from 0.08 to below 0.10, and critical at least 0.10.
The database constrains score range and band membership; the scoring service
assigns the matching band. Current score rows form a single atomic batch with
the same model version, scoring timestamp, and prediction cutoff. Historical
model runs are preserved, while prior risk batches are replaced.
