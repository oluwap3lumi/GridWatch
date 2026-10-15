# GridWatch

Infrastructure failure-risk predictor for electricity-distribution assets.
Public portfolio project; synthetic or public data only.

## Status

M0 foundations are implemented and verified locally. See [the build plan](docs/BUILD_PLAN.md)
and [verification results](docs/m0-verification.md).
M1 database schema, synthetic generation, and loading are implemented and verified
locally. See [M1 verification](docs/m1-verification.md).
M2 temporal features, calibrated logistic regression and CPU XGBoost, SHAP
explanations, and a versioned model registry are implemented and verified locally.
See [M2 verification](docs/m2-verification.md) and [the model card](docs/model-card.md).
M3 asset/outage GeoJSON, risk scoring/aggregation/hotspots, and model information
are implemented and verified locally. See [M3 verification](docs/m3-verification.md)
and [the API contract](docs/api.md) for filters, pagination, scoring policy, and errors.
M4 risk map, filters, summary cards, hotspots, transformer ranking, and asset
explanations/history are implemented and verified locally. See
[M4 verification](docs/m4-verification.md), including the real-browser acceptance
check and review choices. M5 model metrics, global feature importance, registered
version history, and UI rescoring are implemented and verified locally. See
[M5 verification](docs/m5-verification.md) for the retraining-without-restart check.
M6 is awaiting approval.
`make migrate` applies Alembic migrations to the running API's database.
`make test` includes a separate
ephemeral PostGIS container; it uses a generated password, exposes no host database
port, and removes the test container after the run. Docker must be running.

## Architecture

Python 3.12 / FastAPI, PostgreSQL 16 / PostGIS 3, React / Vite / TypeScript,
and MapLibre. See [architecture](docs/architecture.md).

## Quickstart

Install Docker with Compose v2+, uv, Node.js 24 LTS, GNU Make, and a Python
interpreter for the portable task runner. uv provisions Python 3.12 for the backend.
On Windows, start Docker Desktop and add Make's `bin` folder to PATH
(GnuWin32 defaults to `C:\Program Files (x86)\GnuWin32\bin`). Open a new terminal
after installing tools.

```sh
cp .env.example .env
make setup
make up
make migrate
make seed
make train
make smoke
make lint
make test
```

In PowerShell, use `Copy-Item .env.example .env` instead of `cp` if preferred.
Change the local database password placeholder in `.env`; never commit this file.
The database stays on the Compose network; API and web ports bind to loopback only.

Open http://localhost:5173 for the risk explorer. No tiles, tokens, or network
map service are needed. A WebGL-capable browser is required. API docs:
http://localhost:8000/docs; liveness: http://localhost:8000/health.
`make up` waits for all three services to become healthy.

`make types` regenerates all component and operation TypeScript contracts from OpenAPI.
`make build` checks the frontend production build. `make hooks` installs Git hooks.
`make down` stops the stack and preserves database data.
`make seed` migrates and atomically replaces synthetic assets, weather, and outages.
It refuses to reseed a database that contains model runs or risk scores. The default
corpus contains 3,000 assets and two years of daily synthetic weather ending on
2025-12-31: 20 feeders, 700 transformers, 2,280 poles, 14,600 weather observations,
and 4,608 outages. Counts and source/database SHA-256 hashes are printed after a successful
load; repeating the same configuration produces the same data and hashes.
Generator overrides are listed in `.env.example`; run `make up` after changing them.
`make train` builds a fresh backend training container, reads a consistent database
snapshot, and records a versioned model under `ml/artifacts/` plus a `model_runs`
row. Training code must be committed so the recorded Git SHA identifies the code
that ran. Artifacts stay on the host through a Compose bind mount and are ignored
by Git. Each version contains `model.joblib`, `metadata.json`, `metrics.json`,
`evaluation.json` (reliability bins and SHAP importance), and `manifest.json`
(SHA-256 checksums). Load joblib artifacts only from your trusted local registry.
The required quality gate is XGBoost PR-AUC above the logistic baseline; a failed
gate records the run for inspection and makes the command fail.
Run `make train` a second time, then `make verify-train` to compare the last two
runs: database provenance, artifact checksums, metrics, and reloaded predictions.
Use the same seed, source revision, locked dependencies, and CPU environment.
Retraining appends versions; it does not replace earlier artifacts or rescore assets.
After a process crash between file publication and database registration, an
unregistered artifact directory may remain; database records identify registered runs.
API health currently measures process liveness; Compose checks database readiness
separately. The web container currently runs the Vite development server.

Click **Top 10 transformers**, then select a ranked asset or a map point to see
its signed SHAP factors and paginated outage history. Type, band, and minimum-risk
filters operate together; **Reset filters** restores the full fleet. Summary
cards and hotspot centres always describe the whole fleet. Hotspot links are
500 metres; connected groups can span more than 500 metres, and marker halos are
not distance boundaries. The map uses a local background without street tiles.
The accessible asset list remains usable if WebGL is unavailable.

Scores are historical 30-day predictions at the displayed cutoff, not today's
forecast. The default corpus uses 2026-01-01 UTC. Band thresholds are synthetic
demo choices. SHAP factors describe uncalibrated model log-odds, not additive
changes to calibrated probability or causal effects. **Refresh network** reads
the API; it does not rescore. The dashboard checks batch consistency across all
pages and preserves the previous snapshot if a refresh fails.

Open **Model** (http://localhost:5173/#model) for calibrated validation metrics,
baseline comparisons, global SHAP importance, provenance, and paginated version
history. Available and scored versions are displayed separately. To update the
running demo, run `make train`, click **Refresh models**, then **Rescore network**.
The page and API/web containers can remain running throughout. Rescoring saves
the whole fleet and refreshes the map, summaries, model status, and selected asset.
The button stays disabled until saving and refreshing finish. A failed read after
saving is reported separately; **Refresh views** retries reads without rescoring.
Failed quality gates remain in history. Historical records do not certify current
artifact-file availability; the current model endpoint verifies its artifacts.

GitHub Actions installs locked dependencies, runs lint/types, backend and frontend
tests (including real isolated PostGIS integration tests), builds the frontend,
checks generated-type drift, and boots/seeds the full stack for HTTP and PostGIS
smoke checks. It trains twice and checks reproducibility. Local hooks run the same
lint/type target. The smoke check calls every endpoint and performs actual rescoring.
CI workflow execution itself has not been verified remotely.

If ports are occupied, change `API_PORT` / `WEB_PORT` in `.env`. For `make smoke`,
export the same overrides in your shell (`$env:API_PORT = '8001'` in PowerShell).
