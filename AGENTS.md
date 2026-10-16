# AGENTS.md: GridWatch

GridWatch is a full-stack infrastructure risk predictor. It scores electricity-distribution assets (transformers, feeders, poles) for failure risk and shows them on a map.

Read this file and `docs/BUILD_PLAN.md` before every task.

## Hard rules
1. **Repository data must be synthetic or public.** Everything committed (samples, fixtures, tests, screenshots, and docs) must use synthetic or public data. Demo data comes from `data/generator`. At runtime, users may upload their own data; it stays on their deployment. Upload/staging directories must be gitignored. Logs must never contain uploaded row contents or coordinates: import logs contain only counts, batch IDs, and fixed error/event codes. Delete staged files after commit, rollback, or configurable TTL expiry. Deployers are responsible for access control because GridWatch has no real authentication; state this in the README.
2. **No secrets in git.** Config comes from environment variables. Keep `.env.example` up to date.
3. **Work in small slices.** One milestone task at a time. After each slice: run lint, type-check, and tests, then fix failures before moving on.
4. **Ask before adding a dependency.** State what it is for and why the standard library or an existing dependency is not enough.
5. **Never mark a task done unless it runs.** Show the command you ran and its result.
6. **Conventional commits** (`feat:`, `fix:`, `test:`, `docs:`, `chore:`), one logical change per commit.
7. Do not rewrite files outside the current task's scope.

## Stack
- **Backend:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 + GeoAlchemy2, Alembic, PostgreSQL 16 + PostGIS 3
- **ML:** pandas, scikit-learn, XGBoost, SHAP, joblib (file-based model registry in `ml/artifacts/`)
- **M8 imports (approved):** python-multipart, pyshp, pyproj, Shapely 2.x. No Fiona, pyogrio, GeoPandas, or new frontend dependencies.
- **Frontend:** React + Vite + TypeScript, MapLibre GL JS, TanStack Query, Vitest
- **Tooling:** uv (or pip-tools), ruff, mypy, pytest, pre-commit, Docker Compose, GitHub Actions, Makefile

## Commands (keep these working)
- `make up` start db + api + web via Docker Compose
- `make seed` generate synthetic data and load it
- `make train` train model, evaluate, and write artifacts
- `make test` run backend + frontend tests
- `make lint` ruff + mypy + eslint + tsc

## Conventions
- API routes are versioned under `/api/v1`. All responses are typed Pydantic models.
- Geometry is stored as EPSG:4326. Use `ST_DWithin` on geography for distance queries.
- DB changes only through Alembic migrations.
- ML code is pure and testable: no DB calls inside feature or model functions. Data access lives in `app/repositories`.
- Every model run records: data hash, feature list, metrics, git SHA, timestamp.
- Frontend: no `any`. API types are generated from the OpenAPI schema (`make types`).
- Tests: unit tests for logic, integration tests against a real PostGIS container, one smoke test of the full stack in CI.

## Definition of done (any task)
Code runs, tests added or updated and passing, lint and types clean, docs updated if behaviour changed.
