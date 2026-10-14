# M3 verification

Verified locally on 2026-10-14 with Python 3.12.15, Docker Desktop's Linux engine,
PostgreSQL 16 / PostGIS 3.5, and the existing locked dependencies. No dependencies
were added for M3. All demo data came from `data/generator`.

## Commands actually run

| Command | Result |
| --- | --- |
| `make lint` | Passed: Ruff/formatting, strict mypy (57 source files), ESLint, TypeScript |
| `make test` | Passed: 52 backend unit tests, 33 real PostGIS integration tests, 2 frontend tests |
| `make types` | Passed: all component/operation contracts generated; a repeat run had no Git diff |
| `make up` | Passed: database, API, and web healthy; frontend Docker production build passed |
| `make migrate` | Passed: migration `0002` applied without replacing demo data or model runs |
| `make train` (twice) | Passed at source revision `d38fc62fab05c5f05e75f6935560b2ca27b65438` |
| `make verify-train` | Passed: identical metrics and all 5,979 reloaded validation predictions; artifact integrity/provenance matched |
| `make smoke` | Passed: every application endpoint, actual HTTP rescoring, frontend health proxy/entry point, PostGIS |
| `git diff --check` | Passed |

Implementation was committed in three slices, each with passing lint, types,
and tests. This verification report is committed separately afterward.

## Observed running-stack results

The current model after retraining/rescoring is
`20261014T125635177346Z-ec299705da0d`. Its reproducibility partner is
`20261014T125559382757Z-3c07094b8eb9`. Both use persisted data hash
`7f0b3405a1a2579434e09f298dc5cc30e69f171d9fd21b798d903cd15a50c6f9`.
Validation PR-AUC remains 0.07932361743923927 versus logistic regression's
0.07853108335085585; the small gain and synthetic-data limitations remain documented
in [the model card](model-card.md).

`POST /api/v1/risk/rescore` saved all 3,000 asset predictions with a 2026-01-01
UTC cutoff and separate actual scoring timestamp:

| Band | Count |
| --- | ---: |
| low | 812 |
| medium | 1,828 |
| high | 90 |
| critical | 270 |
| unscored | 0 |

`GET /api/v1/risk/hotspots` returned 41 qualifying geography-based clusters.
The smoke test validated asset GeoJSON, pagination/risk filters, detail/history,
outage GeoJSON, summary totals, feature importance, and matching available/scored
versions after rescoring.

Without restarting the API, `GET /model` observed the new available version
while `scored_model_version` still named the preceding M2 score batch. After
rescoring, the smoke test confirmed that they matched. Earlier artifacts and
model runs were preserved.

## Integration coverage

- Every build-plan endpoint is exercised through the ASGI application against
  isolated PostGIS, including empty/unscored states, filters, geometry, pagination,
  half-open time boundaries, validation errors, unknown assets, and missing models.
- A full generated default corpus is trained with the real CPU models and scored;
  scores, bands, cutoff, factors, feeder totals, and reproducibility are checked.
- Actual geography distances prove that hotspot edges use metres; tests cover
  transitive membership, minimum group size, bbox filtering, and centroids.
- Competing rescoring is rejected and its advisory lock released. Insert failures,
  source changes before/during prediction, newer passing models registered during
  prediction, and corrupt artifacts preserve the previous score batch.
- Newer failed training runs are excluded from serving; model/artifact errors have
  typed HTTP 404/409/503 responses as appropriate.
- OpenAPI contains exactly the eight v1 paths, all schema references resolve,
  internal database/file dependencies are absent from query parameters, and
  serialized default fields are required in response schemas. Generated frontend
  types compile without `any`.

## Run and review

For the existing trained stack in PowerShell:

```powershell
make up
make migrate
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/v1/risk/rescore
Invoke-RestMethod -Uri http://localhost:8000/api/v1/risk/summary
make smoke
make lint
make test
```

Open `http://localhost:8000/docs` for the full API. For a fresh clone, follow the
README: configure `.env`, `make setup`, `make up`, `make migrate`, `make seed`,
`make train`, then `make smoke`. Do not reseed the current trained database.

Approved decisions are documented in [the API contract](api.md): fixed probability
bands at 0.05/0.08/0.10, data-relative cutoff, 500-metre connected hotspots with
three-asset minimum, stable pagination (100 default / 500 maximum), and a nullable
legacy `prediction_cutoff` column. New scoring always records that cutoff.
SHAP factors use uncalibrated log-odds, not additive probability changes.
Remote GitHub Actions execution is not claimed; its existing smoke step now
performs the full M3 checks. Frontend map interaction is the next milestone.

## Proposed M4 slices — awaiting approval

1. Add generated-contract API hooks with TanStack Query, paginated asset loading,
   and loading/error/empty states.
2. Render risk-coloured points/feeders in MapLibre, legend, filters, summary cards,
   and hotspot GeoJSON.
3. Add click-through asset detail with factors/history and a top-risk transformer
   workflow; verify key components with Vitest and the running stack.
