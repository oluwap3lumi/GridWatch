# M0 verification

Verified locally on Windows on 2026-10-14 with Python 3.12.15, Node.js 24,
Docker Desktop, Compose, uv 0.13.0, and GNU Make 3.81.

| Command | Result |
| --- | --- |
| `make setup` | Locked backend and frontend dependency installation passed. |
| `make lint` | Ruff check and formatting, strict mypy (25 files), ESLint, and TypeScript passed. |
| `make test` | 3 backend tests and 2 frontend tests passed. |
| `make build` | TypeScript and Vite production build passed; also verified inside the web image. |
| `make types` | Generated the health contract; comparison with the committed file showed no drift. |
| `make hooks` | Installed pre-commit; the lint/type hook passed during commits. |
| `make up` | Exit 0; db, api, and web all healthy. |
| `make smoke` | Both API health paths, the Vite API proxy, web entry point, and real PostGIS 3.5 query passed. |

Browser verification used the existing Edge browser in headless mode with software
WebGL and its local debugging interface. The check observed MapLibre's loaded
status and exactly one WebGL canvas; the blank map and controls rendered in a
screenshot. This also caught and verified the explicit Vite worker-bundling fix.
Temporary browser and cache artifacts remain under gitignored `.tooling/`.

The local network reset some TLS connections to GitHub Container Registry and
npm. The API image now installs the pinned uv package from PyPI, and container
builds use dependency caches and retries. For this machine's verification, only
public package tarballs referenced by the frontend lockfile were copied into the
Docker build cache. The missing Linux native binding was fetched over verified
HTTPS and installed with npm's lockfile integrity checks. No project TLS settings
were weakened. A cold-cache build on this network has not been verified.

The CI workflow was parsed and its local setup/check/build/smoke commands were
executed. A hosted GitHub Actions run remains unverified until the repo is pushed
to GitHub. The production build reports a large MapLibre bundle; asset/map
performance work belongs to the later frontend milestone.

M0 intentionally has no asset tables, generated data, or trained model. `make seed`
and `make train` report that implementation belongs to M1 and M2. `/health` is
process liveness; database readiness is separately checked by Compose.

Proposed M1 slices, pending approval:

1. SQLAlchemy/GeoAlchemy models, Alembic migration, and spatial indexes.
2. Seeded synthetic assets, weather, and correlated outages from `data/generator`.
3. `make seed`, data dictionary, and real PostGIS integration tests for row counts,
   reproducibility, and valid EPSG:4326 geometries.
