# M1 verification

Verified locally on Windows and inside Linux containers on 2026-10-14, using
Python 3.12.15 and PostgreSQL 16 / PostGIS 3.5.

## Implemented

- Typed SQLAlchemy/GeoAlchemy models and reversible Alembic revision `0001` for
  assets, outage events, weather observations, risk scores, and model runs.
- Explicit GiST geometry indexes, temporal indexes, foreign keys, geometry/value
  constraints, and the approved self-referencing `assets.feeder_id` relationship.
  A trigger rejects links to non-feeders and changes to referenced feeder types.
- Pure seeded asset/weather/outage generation with invented feeder paths, age/
  vegetation correlation, and outage probability driven by asset and storm stress.
- Atomic `make seed` with parent-first insertion, bounded batches, concurrent-seed
  locking, actual loaded counts, and hashes of generated and persisted records.
- Isolated PostGIS integration tests, generated test passwords, automatic test
  container cleanup, and CI migration/seeding steps.

## Commands actually run

| Command | Result |
| --- | --- |
| `make lint` | Ruff check/format, strict mypy (32 source files), ESLint, and TypeScript passed. |
| `make test` | 23 backend unit tests, 12 real PostGIS integration tests, and 2 frontend tests passed. |
| `make up` | Exit 0; db, API, and web all healthy. |
| `make seed` twice | Each load returned 3,000 assets, 14,600 weather rows, and 4,608 outages; both hashes were identical. |
| `make smoke` | Both health routes, web proxy/entry point, and PostGIS query passed. |

The integration tests exercised migration downgrade/upgrade and metadata/schema
agreement; geometry/SRID/parent/foreign-key rejection; row counts and geometry
validity; proximity to feeder lines using `ST_DWithin` on geography; complete-row
fingerprint equality after reload; stale-row removal with a smaller configuration;
transaction rollback after invalid data; and refusal to overwrite trained-model
data. Unit tests also verified unchanged global random state, correlated age/
vegetation, and a higher observed outage rate during generated storms.

## Default corpus fingerprints

```text
Generated data/configuration SHA-256:
d8dd2f293d42fbc729f17f9a987c78c7e461e5294ee03e778a20560ab808f69c

Persisted database-row SHA-256:
7f0b3405a1a2579434e09f298dc5cc30e69f171d9fd21b798d903cd15a50c6f9
```

The generated hash matched between host Python and container Python. The database
fingerprint includes all fields and geometries in the three populated demo tables.
These hashes describe different representations; see the [data dictionary](data-dictionary.md).

The only additional unlisted dependency was the explicitly approved Psycopg 3
binary driver. The approved feeder relationship is the sole new data-model field.
No real utility/customer data, frontend feature work, or trained models were added.
The model-run and risk-score tables remain empty in the demo database.

The workflow's local lint/test/build/seed/smoke steps were verified; a hosted GitHub
Actions run remains unverified until the repo is pushed. The M0 cold-network/cache
limitation remains documented in [M0 verification](m0-verification.md).

M2 remains pending approval. Proposed slices: repository-backed training data and
pure time-aware features; leakage-safe temporal evaluation of logistic regression
and XGBoost; reproducible artifact/model-run registration, SHAP, and the model card.
