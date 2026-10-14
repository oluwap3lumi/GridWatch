# GridWatch

Infrastructure failure-risk predictor for electricity-distribution assets.
Public portfolio project; synthetic or public data only.

## Status

M0 foundations are under verification. See [the build plan](docs/BUILD_PLAN.md).
Asset generation, database tables, and trained models belong to later milestones.

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
make smoke
make lint
make test
```

In PowerShell, use `Copy-Item .env.example .env` instead of `cp` if preferred.
Change the local database password placeholder in `.env`; never commit this file.
The database stays on the Compose network; API and web ports bind to loopback only.

Open http://localhost:5173 for the blank MapLibre map. No tiles, tokens, or network
map service are needed. A WebGL-capable browser is required. API docs:
http://localhost:8000/docs; liveness: http://localhost:8000/health.
`make up` waits for all three services to become healthy.

`make types` regenerates the M0 health TypeScript contract from OpenAPI.
`make build` checks the frontend production build. `make hooks` installs Git hooks.
`make down` stops the stack and preserves database data.
`make seed` and `make train` deliberately fail with milestone guidance until M1/M2.
API health currently measures process liveness; Compose checks database readiness
separately. The web container runs the Vite development server for M0.

If ports are occupied, change `API_PORT` / `WEB_PORT` in `.env`. For `make smoke`,
export the same overrides in your shell (`$env:API_PORT = '8001'` in PowerShell).
