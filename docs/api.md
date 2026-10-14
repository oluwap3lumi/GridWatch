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

Scoring and risk/model routes are the next implementation slice.
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
