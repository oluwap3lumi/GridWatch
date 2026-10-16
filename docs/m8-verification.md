# M8 verification

## Slice 1: Policy, schema, and contracts

Implemented the approved repository/runtime data-policy distinction in AGENTS.md
and documented the absence of authentication and deployer access-control duties.
Upload/staging paths are gitignored; configurable size, feature, ZIP, and 24-hour
TTL settings are listed in `.env.example` and [uploads.md](uploads.md).

Migration `0003` adds import batches, expiring staged rows, durable jobs with
leases/progress, and an undo journal. Assets gain scoped external identity,
optional pole/feeder references, batch provenance, revisions, generated IDs,
nullable source attributes, and multipart feeder support. Existing seeded data
and training fingerprints are preserved. Downgrade refuses to discard M8 data.
Readiness checks require the new tables. API geometry/attribute contracts and
the generated frontend types support these storage changes; the existing map
handles multipart bounds and the detail panel displays missing values as unknown.

Staging uses UUID-derived private filenames, bounded streaming, exclusive writes,
partial-write cleanup, and symlink-safe idempotent deletion. Import/native-parser
logs suppress arbitrary messages and exception text; only fixed event/error codes,
batch UUIDs, and counts are emitted. Engine exceptions hide bound parameters.

| Command run | Result |
| --- | --- |
| `make types` | Generated frontend API contracts |
| `make lint` | Passed Ruff/format, strict mypy (65 sources), ESLint, and TypeScript |
| `make test` | 64 backend unit passed, one Windows symlink test skipped; 40 PostGIS integration and 25 frontend tests passed |
| `docker compose --profile test run --rm --build test-api pytest tests/unit/test_upload_foundations.py tests/integration/test_import_foundations.py tests/integration/test_schema.py -x --tb=short -q` | 17 focused tests passed in Linux, including the symlink test skipped on Windows; run before adding the additional downgrade-preservation test covered by the full suite |
| `make up` | Database, migrated API, and web healthy; Docker frontend build passed |
| `make smoke` | Existing model verified and rescored 3,000 assets; unchanged bands (812 low, 1,828 medium, 90 high, 270 critical) and 41 hotspots; all endpoint/PostGIS checks passed |
| `git check-ignore uploads/staging/example.upload backend/uploads/example.upload data/staging/example.json` | All three paths ignored |

The first PostGIS attempt caught a malformed compiled JSON default before any
successful migration; replacing it with `jsonb_build_object` fixed the migration.
Focused migration tests and the complete suite subsequently passed.

This slice supplies foundations, not a working upload flow. Upload endpoints,
parsers, automatic TTL cleanup, the worker, transactional import/rollback,
imported-asset scoring, and the Upload page remain in their approved later slices.
No new dependency was needed for slice 1; the four approved parser/upload
dependencies will be installed when their implementation begins. Hosted M8 CI and
clean-clone acceptance will be recorded as those checks run.

## Slice 2: Parsing, mapping, CRS, and validation

Added the four approved direct dependencies and locked their resolved versions:
python-multipart 0.0.32, PyShp 3.1.6, pyproj 3.8.0, Shapely 2.2.0. Linux wheels
work in the existing Python slim test image without additional system packages.
No Fiona, pyogrio, GeoPandas, or frontend dependency was added.

Pure helpers read CSV, GeoJSON/JSON arrays, and one-layer zipped Shapefiles;
suggest/validate mappings; reproject to EPSG:4326; and return valid/invalid rows
with fixed error reasons and reference warnings. They preserve missing optional
attributes and leading-zero IDs and reject every copy of a duplicated ID.
Optional whitespace-only cells stay missing. Dates require a convention when
ambiguous. Unknown references warn without invalidating otherwise valid rows.

ZIP inspection is in-memory only, validates all entry paths/budgets, and reads
only allowlisted components. Shapefile binary sizes/counts are checked before
native allocations. `.prj` uses `CRS.from_wkt`; missing/unparseable CRS needs user
selection. DBF encoding follows UTF-8, `.cpg`, latin-1. Null shapes and multipart
lines are handled explicitly. Native warning/exception text is suppressed;
malformed Unicode and DBF control text remain row-local and JSONB-safe.

| Command run | Result |
| --- | --- |
| `uv run --project backend pytest -c backend/pyproject.toml backend/tests/unit/test_import_parsing.py -x -q --tb=short` | 47 parser/validation tests passed |
| `docker compose --profile test run --rm --no-deps --build test-api pytest tests/unit/test_import_parsing.py tests/unit/test_upload_foundations.py -q --tb=short` | 52 passed on Linux, including the filesystem symlink test |
| `make lint` | Ruff/format, strict mypy (70 sources), ESLint, and TypeScript passed |
| `make types` | Regenerated contracts; byte hash unchanged, since this slice adds no HTTP endpoints |
| `make test` | Final run: 111 backend unit passed with one Windows symlink skip; 40 real PostGIS integration and 25 frontend tests passed; skipped coverage passed in the separate Linux run |

These are internal helpers. Upload endpoints, downloadable errors, durable jobs,
transactional upsert/rollback, and active retention cleanup remain slice 3 work.
End-to-end per-format PostGIS import tests are added when those routes exist.

## Slice 3: Durable imports, undo, reports and retention

Added versioned upload/history/validation/commit/rollback/template/report routes,
typed OpenAPI contracts (including multipart bodies and CSV downloads), bounded
HTTP multipart handling, a separate Compose worker with shared private staging,
PostgreSQL job leases/progress, transactional 1,000-row upserts, undo history,
late parent resolution, conflict checks, and automatic retention cleanup.
No additional dependency or schema migration was needed in this slice.
Seeding refuses private import history instead of erasing it.

| Command run | Result |
| --- | --- |
| `make lint` | Ruff/format, strict mypy (76 sources), ESLint and TypeScript passed |
| `make types` | Regenerated import schemas, operation bodies, binary upload and CSV response contracts |
| `make test` | 113 backend unit passed, one Windows symlink skip; 54 real PostGIS integration passed; 25 frontend passed |
| `make up` | PostGIS, API, web and the new import worker all healthy |
| `make smoke` | Existing model/provenance and API smoke passed: 3,000 scored assets, unchanged bands (812 low, 1,828 medium, 90 high, 270 critical), 41 hotspots |
| `$env:GRIDWATCH_IMPORT_SMOKE_URL='http://localhost:18001'; uv run --project backend python scripts/import_smoke.py` | Separate API/worker over HTTP: inspected 1, validated 1, inserted 1, rolled back 1; main demo unchanged |
| `docker exec gridwatch-slice3-worker python -c "from pathlib import Path; assert not list(Path('/app/uploads/staging').glob('*.upload')); print('PASS committed/rolled-back raw uploads removed')"` | Passed; no raw staging files remained |

The full suite covers every accepted format, projected and multipart Shapefiles,
validation without asset writes, idempotent re-import, partial success, retained
error CSV, upload/feature limits, TTL cleanup, abandoned leases, a lost-token
transaction that rolls back before a replacement worker succeeds, 1,001-row
upserts spanning two chunks, late relationship resolution and reverse undo,
out-of-order rollback conflicts, and a database constraint failure that preserves
the entire previous corpus. Windows' symlink test remains the platform-specific
skip already exercised successfully on Linux in slice 2; new HTTP body-limit
unit tests also passed in the focused Linux run.

Initial focused runs caught undo geometry serialization and a missing bulk-insert
import; both were fixed before the passing full run. The standalone smoke first
encountered API startup in progress; its readiness wait now handles that state.
Native exception messages and uploaded data are not written by the worker.

To reproduce the separate-worker smoke after `make test`, start disposable
containers against a fresh `test-db` (PowerShell, repo root):

```powershell
docker compose --profile test up -d --wait test-db
docker compose --profile test run -d --name gridwatch-slice3-api -p 127.0.0.1:18001:8000 -e UPLOAD_STAGING_DIR=/app/uploads/staging -v gridwatch_slice3_staging:/app/uploads/staging test-api sh start.sh
docker compose --profile test run -d --name gridwatch-slice3-worker -e UPLOAD_STAGING_DIR=/app/uploads/staging -v gridwatch_slice3_staging:/app/uploads/staging test-api python -m app.services.import_worker
$env:GRIDWATCH_IMPORT_SMOKE_URL='http://localhost:18001'
uv run --project backend python scripts/import_smoke.py
docker rm -f gridwatch-slice3-api gridwatch-slice3-worker
docker compose --profile test rm --stop --force test-db
docker volume rm gridwatch_slice3_staging
```

The smoke refuses to upload to a deployment with existing assets. It creates its
in-memory CSV from `data/generator` and leaves no sample upload in the repository.
The named API/worker containers and their test staging volume were removed after
verification. The regular four-service demo remains running.

Imported-asset inference, the Upload UI, generator sample files/screenshots,
hosted M8 CI, and final clean-clone verification remain in the approved later
slices. A requested rescore already runs as a separate job and preserves a
successful import on failure; existing strict model/corpus checks remain intact
until slice 4 implements the inference contract.

## Slice 4: Uploaded-asset inference and provenance

Uploaded assets now participate in inference while remaining outside default
synthetic training and its corpus hash. Scoring retains the exact registered
training-hash/artifact checks and separately hashes the full inference snapshot,
including asset import provenance and revisions. Both hashes and the latest
passing model are checked again before atomic score replacement.

Migration `0004` adds derived `risk_scores.inference_metadata`; legacy rows retain
unknown provenance until rescored. New scores expose training/inference hashes,
default consent, `per-type-median-v1`, the synthetic history context, applied
default fields/values, and fixed diagnostics. Defaults require explicit consent,
are computed only from eligible verified training assets of the same type, and
never replace stored uploaded attributes. Supplied dates on/after the historical
cutoff remain unscored, with reason counts in the rescore response.

Background import scoring forwards the consent option and preserves a committed
import if scoring fails. The Model page now has an unchecked opt-in checkbox;
asset details identify synthetic history, applied median values, and locations
outside the training extent. The map uses a neutral network caption when uploaded
data is present and logs only a fixed render error code. Unassigned point assets
share a nullable feeder group, rather than inflating feeder counts.
MultiLineString feeders use the same `ST_PointOnSurface` representative location
in inference and hotspots; existing LineString midpoints remain unchanged.

| Command run | Result |
| --- | --- |
| `uv run --project backend pytest -c backend/pyproject.toml backend/tests/unit/test_inference.py -q --tb=short` | 8 pure inference tests passed |
| `make lint` | Ruff/format, strict mypy (79 sources), ESLint and TypeScript passed |
| `make types` | Regenerated consent, provenance, diagnostics, nullable feeder and rescore contracts |
| `make test` | Final run: 121 backend unit passed, one Windows symlink skip; 62 real PostGIS integration passed; 28 frontend passed |
| `make up` | Migration `0004` applied; PostGIS, API, web and import worker healthy; production frontend build passed |
| `make smoke` | Existing model/artifacts verified, 3,000 assets rescored at 2026-01-01; unchanged bands (812 low, 1,828 medium, 90 high, 270 critical) and 41 hotspots; all API/PostGIS checks passed |

The final full test run includes applied median values in both API metadata and
the asset panel. Tests exercise CSV background rescoring with explicit consent;
GeoJSON and EPSG:32631 Shapefile poles and multipart feeders; missing-consent
failure with retained imports/saved scores; inference revision changes during
prediction; future installations; nullable feeder totals; and migration/readiness
checks. The CSV case scores 3,001 assets while confirming the original 3,000
predictions are unchanged, nullable uploaded attributes remain null, default
training still contains exactly 3,000 assets, and synthetic run registration
continues to use the training-only hash. Undo invalidates scores and restores the
original scoreable corpus. Frontend tests cover consent, displayed default
values/limitations, and provenance-aware snapshot comparison.

Early focused runs exposed a stale migration-version assertion and a test that
attempted registration inside the read-only training snapshot. The assertion and
test transaction boundaries were corrected before the final passing run. Native
error details and uploaded rows/coordinates are not logged. No dependency was
added and no existing model artifact needed replacement.

The Upload page remains slice 5. Generator sample files, updated screenshots,
hosted M8 CI and final clean-clone acceptance remain slice 6. No claim of model
accuracy on real infrastructure is made: uploaded estimates still use the
invented demo weather/outage context and historical cutoff.

## Slice 5: Upload interface

The Upload navigation page now accepts one CSV, zipped Shapefile, or GeoJSON/JSON
layer at a time. It offers server-suggested editable column mappings, explicit
source CRS selection when missing, and date conventions. Validation runs before
asset writes; the first 20 rows show errors/warnings alongside a MapLibre geometry
preview. Duplicate source mappings are blocked. Partial success requires an
explicit checkbox, and rescoring/default consent are separate unchecked options.

Durable jobs are polled with progress and retryable read-error states. A failed
rescore retains a saved import and links to Model for recovery. Results show
inserted/updated/skipped counts, the full error CSV, View on map (batch ID in the
URL, with extent fetched locally), and confirmed rollback. History supports
pagination, reopening, and rollback. Map/asset/model caches are invalidated when
mutating jobs finish. Closing an uncommitted batch leaves source assets unchanged
and explains staging expiry. Runtime coordinates and rows are never logged.

Small API additions support this page: optional `include_errors=false` keeps
polling responses bounded while retaining preview errors and the full CSV;
history omits row previews and full error arrays. A typed downloadable
`GET /api/v1/imports/templates/{layer_type}.geojson` generates an independently
importable synthetic feature through `data/generator`; unit tests validate each
layer example. No dependency was added.

Browser verification used an isolated disposable PostGIS/API/worker/web deployment
on port 15173, not the main demo. The ignored local driver
`node .tooling/m8-ui.cjs` generated its CSV from the synthetic example and exercised
file selection, inspection, mapping, validation, a rendered geometry preview,
commit, main-map navigation, history reopening, and confirmed rollback. Asset
count returned to zero. Desktop (1440 px) and mobile (390 px) checks found no page
overflow. The final check passed without browser exceptions using a fresh headless
Edge profile with extensions disabled. Earlier runs completed the flow but caught
permission errors in the extension-enabled browser. Those runs were not counted
as clean browser passes. The disposable deployment/staging volume and both task
browser sessions were removed/closed afterward. Review captures remain ignored;
published synthetic screenshots and generator sample files belong to slice 6.

| Command run | Result |
| --- | --- |
| `make lint` | Ruff, format check (110 files), strict mypy (79 sources), ESLint and TypeScript passed |
| `make types` | Regenerated OpenAPI client; example contracts and optional lightweight polling query included |
| `make test` | 124 backend unit passed, one existing Windows symlink skip; 62 real PostGIS integration passed; 36 frontend passed |
| `make up` | Production frontend build passed; PostGIS, API, web and import worker healthy |
| `node .tooling/m8-ui.cjs` | Synthetic-only real-browser flow and desktop/mobile overflow checks passed without exceptions in the extension-disabled profile |
| `make smoke` | Original 3,000-asset demo rescored successfully, unchanged bands (812/1,828/90/270) and 41 hotspots; provenance, API/PostGIS and metrics checks passed |
| `git diff --check` | Passed |

Frontend coverage now includes multipart layer selection, mapping suggestions and
duplicate prevention, explicit CRS/date choices, highlighted errors, partial-row
consent, scoring consent, job polling, read retries, retained imports after scoring
or rollback failures, confirmation before undo, and point-extent map zoom. Backend
tests verify generated examples and omission of large polling/history payloads
without losing preview errors or the downloadable full report. Initial checks
caught a MapLibre expression type and the generated bodyless POST contract; both
were corrected before the passing checks above. PowerShell's script policy
required calling the existing `npm.cmd` launcher; no tool/dependency was installed.

Slice 6 remains: generator sample files (including projected Shapefile and broken
input), published synthetic screenshots, documentation polish, clean-clone
acceptance, and hosted M8 CI. This slice does not claim hosted CI verification.
