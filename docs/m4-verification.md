# M4 verification

Verified locally on 2026-10-14 with Python 3.12.15, Node 24, Docker Desktop's Linux
engine, and headless Microsoft Edge using software WebGL. No remote CI run is
claimed. All data is the existing synthetic generator corpus.

## Implemented

- Generated OpenAPI contracts, a typed GET client, and TanStack Query hooks with
  cancellation, bounded retries, complete pagination, and scoring-batch checks.
- Risk-coloured transformer/pole points and feeder lines, selection, fit/zoom,
  band legend, combined type/band/minimum-risk filters, and hotspot centres.
- Whole-fleet summary cards and an accessible priority queue. One button ranks
  the complete scored transformer fleet, descending by score with ID tie breaks.
- Asset panel with signed TreeSHAP factors first, feature values, attributes,
  prediction cutoff, scoring provenance, and ten-event outage-history pages.
- Loading, server-error/retry, empty-filter, empty-network, unscored, missing
  explanation/history, and changed-score-batch states. Failed fleet refreshes keep
  the previous consistent snapshot visible.
- Responsive layout and keyboard selection/focus; the list works without WebGL.

TanStack Query was already in the approved stack. The user explicitly approved
Testing Library React/user-event/jest-dom and jsdom as test-only dependencies.
No backend schema or endpoint changed in M4.

## Commands and results

| Command | Actual local result |
| --- | --- |
| `make lint` | PASS: Ruff checks/format, strict mypy (57 sources), ESLint, TypeScript |
| `make test` | PASS: 52 backend unit, 33 real PostGIS integration, 15 frontend tests |
| `npm.cmd --prefix frontend test` | PASS after final UI/label corrections: 15 tests in 6 files |
| `make types` | PASS: generated contracts; `git diff --exit-code -- frontend/src/api/generated.ts` found no drift |
| `make up` | PASS: Docker production frontend build, then db/api/web all healthy |
| `make smoke` | PASS: health aliases/proxy, web entry, model, actual rescore, assets/detail, outages, summary, hotspots, PostGIS |
| `node scripts/browser_smoke.cjs` | PASS: complete API ranking comparison, visible SHAP, real history, canvas click-through, reset, mobile layout; no runtime exceptions |
| `git diff --check` | PASS |

The final browser acceptance path took **5,245 ms** from opening the page to the
top-ten ranking, a visible first explanation, and loaded/scrolled real outage
history for transformer #36. This is an automated browser measurement, not a
human usability study. It satisfies the under-one-minute interaction target
locally. The first transformer had a 12.5% displayed probability and two outages.
The test compares all 700 transformers across API pages, not only the first page.
It verifies desktop 1440px and mobile 390px layouts, including actual canvas clicks.

The checked snapshot contained 3,000 assets, 20 feeders, 812 low, 1,828 medium,
90 high, 270 critical, no unscored assets, and 41 hotspots. Scores use the historical
2026-01-01 UTC cutoff and a 30-day horizon. `make smoke` actually rescored this
persisted corpus; it did not reseed or retrain it.

Frontend tests cover ranking/ties, combined filters, emptiness, hotspot toggling,
list selection and explanations, map layers/source updates/clicks/cleanup,
loading/error/retry states, outage pagination, unscored assets, duplicate pages,
batch changes, and cancellation propagation. Backend checks use a separate
ephemeral PostGIS database and remove it after running.

## Reproduce browser verification

Start the existing trained stack with `make up`, then open http://localhost:5173.
Click **Top 10 transformers** and select any row or map point. Scroll inside the
desktop panel for all factors, history, and attributes. Mobile brings the panel
into view above the map. API docs remain at http://localhost:8000/docs.

The browser smoke script uses Node 24 built-ins and an already running Chromium
DevTools endpoint. For a separate hidden Edge profile on Windows PowerShell:

```powershell
$edgePath = 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
$profilePath = Join-Path (Get-Location) '.tooling\edge-m4'
Start-Process -FilePath $edgePath -WindowStyle Hidden -ArgumentList @(
  '--headless=new', '--remote-debugging-port=9223',
  ('--user-data-dir="' + $profilePath + '"'),
  '--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader',
  '--no-first-run', '--no-default-browser-check', 'about:blank'
)
node scripts/browser_smoke.cjs
```

Use the equivalent installed Chrome/Edge executable on other systems. Optional
environment overrides are `GRIDWATCH_BROWSER_DEBUG_URL` (default
`http://localhost:9223`) and `GRIDWATCH_WEB_URL` (default
`http://localhost:5173`). The script closes its own tab and writes ignored local
screenshots to `.tooling/m4-dashboard.png`, `.tooling/m4-detail.png`, and
`.tooling/m4-mobile.png`. It expects the default scored demo corpus; empty/error
states are tested separately by Vitest. The browser check is local, not yet a
hosted CI browser job.

## Review choices and limits

The map has no street tiles or external token. Summary cards and hotspot centres
always show the whole fleet, even when assets are filtered; the UI says so.
Hotspots link high/critical assets within 500 metres, but transitive groups can
span farther. Marker halos are visual centres, not 500-metre boundaries.

The dashboard loads the complete small demo fleet before ranking; an incomplete
page cannot become a misleading top ten. A much larger fleet would need server
ranking and viewport queries. SHAP explains raw model log-odds, not calibrated
probability changes or causes. Historical cutoffs and synthetic band thresholds
are displayed explicitly. Refresh reads data without invoking rescoring.

Vite reported a large MapLibre-containing bundle (about 1.31 MB minified, 365 KB
gzip, plus a 508 KB worker) and TanStack's `use client` directive warnings. Builds
and real browser checks passed. Production serving and bundle optimisation remain
later-milestone work. M5's model page, version history, and rescore button were not
implemented.

## M5 proposal — awaiting approval

1. Add the typed model page with metrics, global feature importance, and registered
   version history; distinguish the available model from the currently scored one.
2. Add the rescore action with pending/error/success states and query invalidation
   so map, summaries, and selected-asset explanations update together.
3. Test model/history and rescore flows, then verify retraining and rescoring update
   the running UI without restarting it. Run lint/types/tests and commit each slice.
