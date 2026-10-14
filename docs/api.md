# API contract

All application routes are under `/api/v1`; `/health` remains a liveness alias.
Interactive OpenAPI documentation is at `http://localhost:8000/docs`.
`make types` exports all component and operation contracts to
`frontend/src/api/generated.ts`. Unsupported schema shapes fail generation;
unconstrained validation context uses TypeScript `unknown`, never `any`.

## Assets and outages

- `GET /assets`: paginated GeoJSON FeatureCollection; filters `type`, `bbox`,
  `min_risk`, and `band`. Order is ascending asset ID. Unscored assets have
  `properties.risk = null` and are excluded when any risk filter is supplied.
- `GET /assets/{asset_id}`: an asset GeoJSON feature plus its paginated outage
  history. Unknown IDs return 404; IDs must be positive integers.
- `GET /outages`: paginated GeoJSON FeatureCollection; filters `asset_id`, `bbox`,
  `started_after` (inclusive), and `started_before` (exclusive). Order is descending
  event timestamp, then descending ID.

Pagination uses `limit` (default 100, range 1–500) and `offset` (default 0).
Collections include `pagination.total`, `limit`, `offset`, and `next_offset`
(null at the end). Offsets beyond the result set return an empty collection.
Asset-detail pagination applies to outage history. Counts and page contents are
read in one repeatable-read, read-only database transaction.

`bbox` is `west,south,east,north` in EPSG:4326. Bounds must be finite, ordered,
and within longitude/latitude limits; antimeridian wrapping is not supported.
PostGIS `ST_Intersects` includes geometry crossing the box boundary, including
feeder lines. Time filters require `Z` or an explicit offset and normalize to UTC.
Malformed filters return FastAPI's typed 422 validation response.

## Approved M3 scoring policy

The scoring service, aggregate repositories, and HTTP routes implement the policy below.
Predictions use a 30-day horizon beginning at the next UTC day after the latest
weather observation: 2026-01-01 for the default demo corpus. `scored_at` records
the actual scoring time; migration `0002` adds `prediction_cutoff` separately.
Legacy score rows retain a null cutoff because their original cutoff cannot be
recovered; new scoring will populate it.

| Band | 30-day probability |
| --- | --- |
| low | <0.05 |
| medium | 0.05 to <0.08 |
| high | 0.08 to <0.10 |
| critical | ≥0.10 |

These are approved synthetic demo thresholds, not validated maintenance rules.
Top factors will report signed exact TreeSHAP contributions in the raw XGBoost
log-odds space, separately from the calibrated probability score.
Hotspots will connect high/critical assets within 500 metres using
`ST_DWithin` on geography and require at least three distinct assets.

Rescoring uses the latest registered XGBoost run whose recorded quality gate and
PR-AUC lift both pass. Before use, every artifact checksum and its database
provenance are validated. Scoring and model information keep the calibrated
probability and uncalibrated SHAP output space separate.

A session advisory lock rejects simultaneous rescoring. After computation,
the persistence transaction takes the seed/training corpus lock, rechecks the
source hash and latest passing version, and replaces the complete score batch.
Failures roll back without changing the previous batch. Retraining during
scoring causes a conflict if a newer passing version becomes available.

Feeder summaries include the feeder asset itself and its child assets, so their
totals sum to the global fleet totals. Hotspot membership is transitive: three
assets connected by two 500-metre edges form one group even when the endpoints
are farther apart. Smaller groups are excluded. Feeders use their line midpoint
for distance, matching the ML feature location; cluster centres use PostGIS
geography centroids. A bbox filters original asset geometries before clustering.

## Risk and model routes

- `GET /risk/summary`: fleet and feeder totals, scored/unscored counts, band
  counts, and current scoring stamp (null until scored).
- `GET /risk/hotspots`: paginated GeoJSON cluster centres with member asset IDs,
  mean/maximum probability, and band counts. Accepts `bbox`, `limit`, and `offset`.
  No scores or no qualifying clusters returns an empty collection.
- `POST /risk/rescore`: no request body; synchronously computes and atomically
  saves a complete batch. The response reports the model, cutoff, actual scoring
  time, scored/unscored counts, and band totals.
- `GET /model`: latest passing available model, validation metrics, feature list,
  sorted mean absolute TreeSHAP importance, provenance, and `scored_model_version`.
  That last value is null before scoring and may lag the available model after
  retraining. Models are looked up per request; retraining does not require a restart.

Errors: `GET /model` returns 404 when no passing model exists. Rescoring returns
409 for missing prerequisites, concurrent work, changed source data, or a newer
passing model registered during computation. Invalid/missing registered artifacts
return 503 for both model information and rescoring. Mixed legacy scoring batches
return 409 from summary/model until rescoring restores a single batch.

For the existing trained stack in PowerShell:

```powershell
make up
make migrate
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/v1/risk/rescore
Invoke-RestMethod -Uri http://localhost:8000/api/v1/risk/summary
Invoke-RestMethod -Uri 'http://localhost:8000/api/v1/assets?type=transformer&band=critical&limit=10'
make smoke
```

`make smoke` now requires seeded data and a passing trained model. It calls every
endpoint, including actual rescoring, and verifies typed responses, summaries,
model/scored version consistency, frontend proxy/entry point, and PostGIS.
