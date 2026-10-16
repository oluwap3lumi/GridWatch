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
