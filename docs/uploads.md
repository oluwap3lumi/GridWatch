# Uploads (M8 in progress)

## Data policy

Only synthetic/public material may be committed: examples, test fixtures, docs,
screenshots, and sample files. At runtime, users may upload their own data, which
stays on their deployment. Deployers must supply access control: GridWatch has
no real authentication. Do not expose it to untrusted networks without that control.

Default upload/staging directories are gitignored. Import and parser/database
logs suppress arbitrary messages, exception text, row contents, coordinates, and
filenames; import events contain batch UUIDs, nonnegative counts, and fixed codes.
SQLAlchemy engine exceptions hide bind parameters. Do not print uploaded rows or
raw parser exceptions from workers, request handlers, or command-line helpers.

## Slice 1 foundations

Migration `0003` adds import history, durable job state and leases, expiring staged
rows, and an undo journal. Asset relationships/identity and nullable source
attributes are represented in storage and typed contracts. MultiLineString feeder
geometry is accepted by the schema, asset API, and map bounds calculation.
Existing seed values remain intact, and import bookkeeping does not change the
legacy model-input fingerprint. Asset IDs now have a sequence, advanced after
seeding so future generated IDs do not collide with deterministic seed IDs.

`UploadSettings.from_env()` provides configurable limits:

| Variable | Default |
| --- | ---: |
| `UPLOAD_STAGING_DIR` | `uploads/staging` |
| `UPLOAD_MAX_BYTES` | 26,214,400 (25 MiB) |
| `UPLOAD_MAX_FEATURES` | 100,000 |
| `UPLOAD_MAX_EXPANDED_BYTES` | 262,144,000 (250 MiB) |
| `UPLOAD_MAX_ZIP_FILES` | 32 |
| `UPLOAD_MAX_ZIP_RATIO` | 100 |
| `UPLOAD_TTL_SECONDS` | 86,400 (24 hours) |

The bounded staging helper uses UUID filenames, exclusive creation, and partial
file cleanup. Its deletion operation is idempotent and rejects symlink targets.
History records have explicit `expires_at`; the lifecycle worker will delete raw
files and staged rows after commit, rollback, or TTL expiry. Automatic expiry,
upload endpoints, parsing, worker execution, and Upload UI are **not available in
slice 1**. The undo journal is persistent imported-data history, separate from
temporary staging, and is required to restore overwritten records.

Upcoming parsers will read `.prj` with `pyproj.CRS.from_wkt`, require a selected CRS
if missing/unparseable, handle null shapes and multipart lines, and try DBF
encoding in the approved order: UTF-8, `.cpg`, then latin-1. CSV/JSON/ZIP handling
and synthetic sample preparation will be documented as those slices run.
