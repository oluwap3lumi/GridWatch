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
