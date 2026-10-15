# M6: DevOps hardening

## Changes

- JSON request logs include UTC timestamps, validated request IDs, canonical route
  templates, response status, and elapsed seconds. Unknown paths share one metrics
  bucket; logs omit request bodies, headers, query strings, and exception text.
- `X-Request-ID` propagates through successful and error responses. Missing,
  repeated, invalid, or oversized IDs are replaced with generated IDs.
- `/api/v1/metrics` returns typed process-local counters, cumulative request
  durations, in-flight requests, and uptime. Counters reset on process restart;
  multiple worker processes would each expose their own counters.
- `/health` remains process liveness. `/api/v1/ready` checks PostGIS and the required
  migrated schema, returning 503 when unavailable. Empty migrated databases are
  ready; seeding and model training remain explicit commands.
- API startup applies Alembic migrations before serving HTTP. Compose gates the
  frontend on API readiness. Connection and readiness statement timeouts bound
  database checks.
- CI uses pinned action revisions, read-only repository permissions, disabled
  persisted checkout credentials, lockfile-based npm/uv caches, temporary database
  credentials, and cancellation of superseded runs. It checks lint/types, unit and
  real PostGIS integration tests, frontend tests/build, generated API type drift,
  Docker startup, training reproducibility, and a full-stack HTTP smoke test.
- `make verify-clean` verifies committed sources in a fresh ignored clone with
  isolated ports, credentials, model artifacts, and disposable database volumes.
  It exercises an actual database outage and recovery after the happy-path smoke
  check. Existing demo containers and data remain untouched.

## Commands and observed results

Local verification of commits `58b93f6` and `28925d5`:

| Command | Result |
| --- | --- |
| `make lint` | Passed Ruff, formatting, strict mypy (61 sources), ESLint, and TypeScript |
| `make test` | Passed: 60 backend unit, 35 real PostGIS integration, 23 frontend tests |
| `make up` | Passed: db, API, and web healthy; automatic migrations completed |
| `make smoke` | Passed readiness/IDs through API and web proxy, metrics, all application endpoints, 3,000-asset rescore, 41 hotspots, and PostGIS 3.5 |
| `make build` | Passed; Vite reports dependency directive and bundle-size warnings |
| `make verify-clean` | Passed fresh clone setup/up/seed/train/test/lint/build/smoke and database outage/recovery; isolated containers and volumes removed |

Readiness integration verification downgrades the isolated test database through
Alembic: missing cutoff migration returns ready 503 while liveness stays 200;
upgrading restores readiness. Unit tests cover concurrent request-ID isolation,
500 responses, log privacy, bounded unknown-route metrics, and prefixed routes.

Hosted [Actions run 38758654220, attempt 2](https://github.com/oluwap3lumi/GridWatch/actions/runs/38758654220/attempts/2)
passed in 5m10s for source revision `28925d56db7901495fbf384c05a6e6b745239f0b`.
It verified the entire workflow, including two training runs and reproducibility.
The first attempt passed code checks but encountered Docker Hub HTTP 502 while
fetching the Node base image; rerunning the job succeeded without a code change.

The local clean clone used the same committed revision, project
`gridwatch-clean-24d43ccf`, API port 18000, and web port 15173. It started without
an existing `.env`, environment, installed frontend packages, database, or model
artifacts. Training passed the quality gate (XGBoost PR-AUC 0.0793236174 versus
baseline 0.0785310834). All 118 tests passed again. After smoke verification, an
actual database stop produced liveness 200 and readiness 503; restarting restored
readiness 200. The machine-readable receipt is ignored at
`.tooling/clean-clone-verification.json`. The original demo remains healthy.

## Review choices and limits

No application dependency was added. The user approved installing GitHub CLI.
The repository is [oluwap3lumi/GridWatch](https://github.com/oluwap3lumi/GridWatch)
and remains **private until M7 approval**.

Metrics are a basic JSON process snapshot, without a monitoring dependency or
persistent timeseries storage. Local Compose exposes loopback API/web ports;
the frontend still uses Vite's development server. Startup migrations suit this
single-instance demo; a multi-instance deployment should run a dedicated migration
job before starting replicas.

## Proposed M7 tasks (awaiting approval)

1. Review and complete architecture, data dictionary, model card, and AI-use notes.
2. Capture screenshots and a short walkthrough GIF; finish the portfolio README.
3. Agree on a licence and add it; verify no secrets or generated artifacts are tracked.
4. Rehearse the README quickstart from a fresh clone and record its elapsed time.
5. Publish the repository publicly after approval; discuss optional live hosting separately.
