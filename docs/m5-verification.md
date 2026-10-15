# M5 verification

Verified locally on 2026-10-15 using Python 3.12.15, Node 24, Docker Desktop Linux
containers, and a dedicated headless Edge profile with extensions disabled and
software WebGL. All data came from the existing synthetic generator corpus.
No dependency or database migration was added. Remote CI was not run.

## Implemented

- `GET /api/v1/model/history`: typed, paginated registered runs with metrics,
  features, provenance, and a quality-gate flag. Failed gates remain visible.
  Newest training timestamp and ID first; default limit 100, maximum 500.
- Model page at `/#model`: calibrated XGBoost/logistic comparisons, validation
  highlights, global mean absolute TreeSHAP bars, provenance, ten-run history
  pages, loading/error/empty states, and separate available/scored versions.
- Native hash navigation and generated OpenAPI contracts with TanStack Query.
- Shared rescore control: one POST, disabled while saving/refreshing, no automatic
  POST retry, complete fleet-cache replacement, model/history invalidation, and
  selected-asset explanations following the new scoring stamp.
- Separate outcomes for a failed scoring request and saved scores whose GET
  refresh failed. Refresh views retries reads without another scoring POST.

## Commands actually run

| Command | Result |
| --- | --- |
| `make lint` | PASS: Ruff checks/format, strict mypy (57 sources), ESLint, TypeScript |
| `make test` | PASS: 52 backend unit, 34 real PostGIS integration, 23 frontend tests |
| `make types` | PASS; generated file matched committed OpenAPI contracts |
| `git diff --exit-code -- frontend/src/api/generated.ts` | PASS: no drift |
| `make up` | PASS: frontend production build completed; db/api/web healthy |
| `node --check scripts/browser_model_smoke.cjs` | PASS |
| `node scripts/browser_model_smoke.cjs` | PASS: real UI rescore, retained asset selection, updated model status, mobile layout, no runtime exceptions |
| `node scripts/browser_smoke.cjs` | PASS: top-ten API comparison, visible SHAP/history in 4,902 ms, real canvas clicks, reset, mobile layout |
| `node scripts/browser_model_smoke.cjs --retrain` | PASS: actual `make train`, model/history refresh, actual UI rescoring, unchanged page origin and API/web container IDs |
| `make smoke` | PASS: every HTTP endpoint including history, actual rescoring, frontend proxy/entry, and PostGIS |
| `git diff --check` | PASS |

Browser commands used `GRIDWATCH_BROWSER_DEBUG_URL=http://localhost:9335`.
Frontend tests include metric comparison, missing model/history, pagination and
failed gates, refresh, rescore pending/duplicate-click prevention, HTTP conflicts,
preserved snapshots, saved-but-refresh-failed recovery, and selected explanation
updates. The PostGIS history test also covers timestamp ties, empty/out-of-range
pages, failed/inconsistent gates, and parameter validation.

Two multi-step DOM tests initially exceeded Vitest's five-second timeout under
concurrent workload. Their flows were split into focused tests, preserving the
assertions and timeout. jsdom concurrency is capped at two workers. The final
complete `make test` run passed all 109 tests.

## Retraining proof

The browser stayed open while `make train` registered
`20261015T131340755934Z-d12c665606b7` from source commit
`a175ab4a24dddaafdc6df4aa07b4ee8892048be0`. It fitted 35,756 chronological
asset-month rows using data hash
`7f0b3405a1a2579434e09f298dc5cc30e69f171d9fd21b798d903cd15a50c6f9`.
XGBoost validation PR-AUC was 0.0793236174 versus baseline 0.0785310834;
the recorded quality gate passed.

The check asserted that training preserved the old saved scores. Refresh models
then displayed the new version and its history row while distinguishing it from
the scored version. Rescore network saved all 3,000 assets, retained selected
transformer #36, and updated its explanation's model version. The returned scoring
timestamp changed. After navigation back to Model, available and scored versions
matched. `performance.timeOrigin` and both API/web container IDs stayed identical
through the entire training and rescoring sequence.

The final HTTP smoke check found seven registered versions and the new model
available and scored. Counts remained 812 low, 1,828 medium, 90 high, 270 critical,
no unscored assets, and 41 hotspots. The prediction cutoff remains 2026-01-01 UTC
with a 30-day horizon. Training and scoring used the existing corpus; no reseed ran.

## Reproduce

For the existing trained demo:

```sh
make up
make train
```

Open http://localhost:5173/#model, click **Refresh models**, then **Rescore network**.
Use Risk map to inspect the updated fleet. Refresh models and Refresh views read
data; training appends a registered version; Rescore network replaces saved scores.

For automated browser acceptance, start a separate browser from the repository
root in PowerShell (adjust the executable path for your installed browser):

```powershell
$edgePath = 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
$profilePath = Join-Path (Get-Location) '.tooling\edge-m5-isolated'
Start-Process -FilePath $edgePath -WindowStyle Hidden -ArgumentList @(
  '--headless=new', '--remote-debugging-port=9335',
  ('--user-data-dir="' + $profilePath + '"'), '--disable-extensions',
  '--disable-component-extensions-with-background-pages',
  '--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader',
  '--no-first-run', '--no-default-browser-check', 'about:blank'
)
$env:GRIDWATCH_BROWSER_DEBUG_URL = 'http://localhost:9335'
node scripts/browser_model_smoke.cjs --retrain
node scripts/browser_smoke.cjs
```

The M5 script always performs actual UI rescoring; `--retrain` also appends one
training run using `make train`, which requires committed backend/ML/data/scripts.
It expects the scored default demo corpus. `GRIDWATCH_WEB_URL` overrides the web
address when needed. Screenshots are ignored local artifacts at
`.tooling/m5-model.png` and `.tooling/m5-mobile.png`. The script closes its tab;
the dedicated browser can be closed afterward. Screenshots were visually reviewed.

## Review choices and remaining work

History shows registered evaluations, including failed gates, without loading
each historical artifact. The current model endpoint verifies its artifacts.
Scoring remains synchronous and uses the existing historical cutoff policy.
Training remains a CLI action. No new dependency was needed for routing, charts,
or browser verification. Metrics and SHAP remain synthetic demo evidence with the
existing limitations in the model card.

The frontend still uses Vite's development server in Compose. Builds report the
existing large MapLibre bundle and TanStack `use client` directive warnings;
production builds and browser checks passed. CI workflow execution and clean-clone
hardening remain for M6. M6 work has not started.

## M6 proposal — awaiting approval

1. Review and harden CI lint/types, unit/integration/frontend tests, Docker builds,
   full-stack smoke checks, and dependency caching.
2. Add structured logging, request IDs, basic metrics, and readiness/health checks.
3. Verify the clean-clone startup/seed/train/test path and document results. Run
   required checks and commit each slice; request approval before any new dependency.
