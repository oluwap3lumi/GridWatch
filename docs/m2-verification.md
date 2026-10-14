# M2 verification

Verified locally on 2026-10-14 using Windows, Docker Desktop's Linux engine,
Python 3.12.15, PostgreSQL 16 / PostGIS 3.5, and locked dependencies.
The trained source revision is `b7ad9331436a63024eb5bae31cb6a727fe1efc14`;
this report is committed separately after verification.

## Commands actually run

| Command | Result |
| --- | --- |
| `make lint` | Passed: Ruff, formatting, strict mypy (39 source files), ESLint, TypeScript |
| `make test` | Passed: 32 backend unit tests, 14 real PostGIS integration tests, 2 frontend tests |
| `make up` | Passed: database, API, and web all healthy |
| `make train` (twice at the revision above) | Passed: two versioned artifact directories and registered `model_runs`; PR-AUC gate passed |
| `make verify-train` | Passed: identical metrics and all 5,979 reloaded validation predictions, valid artifact checksums and database provenance |
| `make smoke` | Passed: API health aliases, frontend proxy/entry point, PostGIS 3.5 |
| `git diff --check` | Passed |

Each implementation slice ran lint, types, and tests before its conventional
commit. The final UTC coverage regression test checks that different timestamp
offsets representing the same instant do not count as different weather days.

## Reproducible model runs

The final verified pair is:

- `20261014T112259863716Z-867014e42400`
- `20261014T112401376511Z-5f0148ce27c8`

Both use the persisted source-row SHA-256:
`7f0b3405a1a2579434e09f298dc5cc30e69f171d9fd21b798d903cd15a50c6f9`.
Their validation probability hash is:
`e480ad844fc4776c365750f60a59d9f7cedd669b3abc8e0392964471e26be0a1`.
Each run records the data hash, ordered 16-feature list, numeric metrics, Git SHA,
and UTC training timestamp in PostGIS. Host artifacts include the fitted bundle,
metadata, metrics, evaluation (reliability bins and exact TreeSHAP), and manifest.
Only `ml/artifacts/.gitkeep` is tracked by Git.

The default synthetic corpus produces 35,756 eligible asset-month rows:
20,840 train (January–July), 2,979 tune (August), 5,958 calibration
(September–October), and 5,979 validation (November–December 2025).
Validation has 323 positive labels and prevalence 0.054022.

| Validation metric | Logistic regression | Calibrated XGBoost |
| --- | ---: | ---: |
| PR-AUC / average precision | 0.07853108335085585 | 0.07932361743923927 |
| ROC-AUC | 0.6039609434185347 | 0.6035192086214372 |
| Brier score | 0.050803228554730136 | 0.050842033660386865 |
| Precision at top 299 rows | 0.09364548494983277 | 0.10367892976588629 |

The absolute PR-AUC lift is 0.0007925340883834231. The gain is small and does
not demonstrate statistical significance or real utility performance. The final
validation labels were excluded from fitting, tuning, and calibration. The
evaluated hyperparameter grid was kept fixed after inspecting holdout results.

Tests cover cutoff/window boundaries, future observation exclusion, complete
target windows, label purging, distance units/missing history, metric calculations,
deterministic fitting, SHAP additivity in log-odds, prediction contracts,
artifact round-trips/corruption, read-only database snapshots, and rejection of
registration when the data hash no longer matches.

## Run it

For the existing seeded stack:

```sh
make up
make train
make train
make verify-train
make lint
make test
make smoke
```

For a fresh clone, first copy `.env.example` to `.env`, configure the local
password, run `make setup`, `make up`, and `make seed`. Do not reseed the current
trained database: the M1 loader deliberately refuses to invalidate existing runs.
Training code must be committed before `make train` to identify its source reliably.

## Limits and next milestone

See [the model card](model-card.md) for the 30-day monthly target, temporal
protocol, static synthetic attribute assumptions, calibration, and SHAP units.
The CI workflow now trains twice and verifies reproducibility, but no remote
GitHub Actions run is claimed. Asset scoring and new API endpoints await M3.

Proposed M3 slices, subject to user approval:

1. Agree risk-band thresholds and API details; implement typed schemas and
   repositories for asset/outage filtering, pagination, and GeoJSON.
2. Load a registered passing model; score assets with historical features and
   SHAP factors, atomically write risk scores, and add summaries/hotspots.
3. Implement the remaining v1 endpoints, generate frontend API types, and verify
   every endpoint against isolated PostGIS plus a stack smoke test.
