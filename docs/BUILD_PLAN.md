# GridWatch Build Plan

## 1. Goal
A deployable full-stack app that ingests (synthetic) asset, weather, and outage data, trains a failure-risk model, serves risk scores through an API, and visualises them on an interactive map, with CI and Docker so anyone can run it in minutes.

**Domains covered:** energy/utilities, GIS, machine learning, DevOps.

## 2. Repo structure
```
gridwatch/
├── AGENTS.md
├── README.md
├── Makefile
├── docker-compose.yml
├── .env.example
├── .pre-commit-config.yaml
├── .github/workflows/ci.yml
├── docs/
│   ├── BUILD_PLAN.md
│   ├── architecture.md          # diagram + data flow
│   ├── data-dictionary.md
│   └── model-card.md
├── data/
│   └── generator/               # synthetic data (assets, weather, outages)
│       ├── __init__.py
│       ├── config.py            # bbox, counts, random seed
│       ├── assets.py
│       ├── weather.py
│       └── outages.py
├── ml/
│   ├── features.py              # pure feature engineering
│   ├── train.py                 # train + evaluate + save
│   ├── evaluate.py              # metrics, calibration, SHAP
│   ├── predict.py
│   ├── notebooks/               # exploration (from ChatGPT sandbox)
│   └── artifacts/               # gitignored; model + metrics json
├── backend/
│   ├── pyproject.toml
│   ├── Dockerfile
│   ├── alembic/
│   ├── app/
│   │   ├── main.py
│   │   ├── core/                # settings, logging
│   │   ├── db/                  # session, models
│   │   ├── schemas/             # pydantic
│   │   ├── repositories/        # all SQL / PostGIS access
│   │   ├── services/            # scoring, risk aggregation
│   │   └── api/v1/              # assets, risk, outages, health, model
│   └── tests/
│       ├── unit/
│       └── integration/
└── frontend/
    ├── package.json
    ├── Dockerfile
    └── src/
        ├── api/                 # generated client + hooks
        ├── components/          # Map, RiskLegend, AssetPanel, Filters
        ├── pages/               # Dashboard, AssetDetail, ModelInfo
        └── tests/
```

## 3. Data model (PostGIS)
- `assets`: id, type (transformer | feeder | pole), geom (Point/LineString), install_date, capacity_kva, load_factor, material, vegetation_index, last_maintenance_date
- `outage_events`: id, asset_id, started_at, duration_min, cause, geom
- `weather_obs`: id, observed_at, geom, rainfall_mm, wind_kph, temp_c, lightning_density
- `risk_scores`: asset_id, score (0-1), band (low | medium | high | critical), model_version, scored_at, top_factors (JSONB)
- `model_runs`: id, model_version, trained_at, data_hash, features, metrics (JSONB), git_sha

## 4. API (v1)
- `GET /health`
- `GET /assets` (filters: type, bbox, min_risk, band; GeoJSON output)
- `GET /assets/{id}` (details, history, risk, top factors)
- `GET /risk/summary` (counts by band, by feeder)
- `GET /risk/hotspots` (clustered high-risk areas)
- `GET /outages` (time and bbox filters)
- `POST /risk/rescore` (re-run scoring with the latest model)
- `GET /model` (current version, metrics, feature importance)

## 5. Milestones

### M0: Foundations (day 1)
- Repo, Makefile, Docker Compose (db with PostGIS, api, web), pre-commit, ruff/mypy config, CI skeleton, `/health` endpoint, "hello map" page.
- **Done when:** `make up` shows a healthy API and a blank map; CI runs lint and a trivial test.

### M1: Database and synthetic data (days 2-3)
- SQLAlchemy models, Alembic migration, spatial indexes.
- Generator: a few thousand assets with realistic clustering along feeders, correlated vegetation and age, seeded weather, and outages whose probability depends on age, load, vegetation, and storm weather (so the model has real signal to find).
- `make seed` loads everything.
- **Done when:** data loads reproducibly (same seed, same data) and integration tests verify row counts and geometry validity.

### M2: Features and model (days 4-6)
- Feature engineering (asset age, load stress, outage count in trailing 12 months, rainfall/wind aggregates, vegetation, distance to nearest prior outage).
- Time-based train/validation split (no leakage). Baseline (logistic regression) vs XGBoost. Metrics: ROC-AUC, PR-AUC, calibration, precision at top-k. SHAP for explanations.
- `make train` writes versioned artifacts and a `model_runs` record. Write `docs/model-card.md`.
- **Done when:** XGBoost beats the baseline on PR-AUC, results are reproducible, and unit tests cover the feature functions.

### M3: Scoring service and API (days 7-9)
- Repositories, services, endpoints from section 4, GeoJSON responses, pagination, OpenAPI docs.
- Scoring writes `risk_scores` with bands and top factors.
- **Done when:** integration tests hit every endpoint against real PostGIS and the OpenAPI schema is clean.

### M4: Frontend map (days 10-13)
- MapLibre map with risk-coloured assets, legend, filters (type, band, risk threshold), click-through asset panel with SHAP factors and outage history, summary cards, hotspot layer.
- Generated API types and TanStack Query hooks. Loading, error, and empty states.
- **Done when:** a user can find the top 10 riskiest transformers and see why in under a minute. Vitest covers key components.

### M5: Model page and rescoring (day 14)
- Model info page (metrics, feature importance, version history) and a rescore button.
- **Done when:** retraining and rescoring updates the UI without a restart.

### M6: DevOps hardening (days 15-16)
- CI: lint, types, backend unit and integration tests, frontend tests, Docker build, and a stack smoke test. Cache dependencies.
- Structured logging, request IDs, basic metrics endpoint, healthchecks in Compose.
- **Done when:** a clean clone passes `make up && make seed && make train && make test` and CI is green.

### M7: Polish and publish (days 17-18)
- README with screenshots, a GIF, architecture diagram, quickstart, and a "How AI was used to build this" section. Data dictionary and model card. Licence. Optional live deployment.
- **Done when:** a stranger can run it from the README in under 10 minutes.

### Stretch
- Time-slider replay of outages, scheduled retraining, drift check, role-based auth, a what-if panel (change load or vegetation and see the risk shift).

## 6. Working agreement
- One milestone at a time, in order. Finish and verify before starting the next.
- At the start of each milestone, propose a task list; wait for approval before coding.
- At the end, summarise what changed, how to run it, and what is still open.
