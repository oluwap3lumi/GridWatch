# Architecture

M0 runs a PostGIS 3 / PostgreSQL 16 database, a FastAPI service, and a React/Vite web app.
Compose waits for database and API health checks before starting dependent services.
The web development server proxies `/api` to FastAPI. `/health` is an API liveness alias;
the canonical OpenAPI route is `/api/v1/health`. Database readiness is separate in M0.

The initial MapLibre map uses a local background style and requires no external tiles.
Vite bundles MapLibre's worker explicitly as an ES module, so its URL works in both
development and production builds. This uses MapLibre's
[worker URL configuration](https://maplibre.org/maplibre-gl-js/docs/API/functions/setWorkerUrl/).
M1 generates an invented network, weather, and correlated outages entirely in
`data/generator`. The seed service passes that immutable corpus to a repository;
the repository serializes concurrent seeds with a transaction-level advisory lock,
replaces demo rows atomically, and verifies loaded counts and a database fingerprint.
Database DDL is applied only by Alembic. Integration tests use a separate ephemeral
PostGIS database. Feature engineering, trained models, and scoring remain M2/M3 work.
