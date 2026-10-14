# Architecture

M0 runs a PostGIS 3 / PostgreSQL 16 database, a FastAPI service, and a React/Vite web app.
Compose waits for database and API health checks before starting dependent services.
The web development server proxies `/api` to FastAPI. `/health` is an API liveness alias;
the canonical OpenAPI route is `/api/v1/health`. Database readiness is separate in M0.

The initial MapLibre map uses a local background style and requires no external tiles.
Synthetic generation, persistence, features, and scoring follow in later milestones.
