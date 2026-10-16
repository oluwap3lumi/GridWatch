# M7: Polish and publish

## Scope

Portfolio README with real screenshots, a four-frame walkthrough GIF, Mermaid
architecture, Docker-first quickstart, development commands, model limitations,
and an account of AI assistance. Architecture and data dictionary describe the
current implementation rather than planned milestone behavior. The model card
states intended use and synthetic-data provenance. The user selected MIT;
`LICENSE` uses the existing Git author name, Pelumi, and year 2026.

No application dependency was added. Screenshots were captured from the running
synthetic demo using local Edge DevTools. The GIF cycles actual screenshots
(network, top ten, asset explanation, model) at 2.5 seconds each; it is an edited
walkthrough rather than a recording of interaction timing. Windows' built-in
image encoder and a local GIF container assembler produced it without adding
packages. Capture helpers remain ignored under `.tooling/`.

## Verification

Checks run on 2026-10-16:

| Command | Observed result |
| --- | --- |
| `make up` | Passed; database, API, and web healthy |
| `make lint` | Passed Ruff/format, strict mypy (61 sources), ESLint, and TypeScript |
| `make test` | Passed 60 backend unit, 35 real PostGIS integration, and 23 frontend tests |
| `node scripts/browser_smoke.cjs` with isolated Edge on port 9335 | Passed complete-API top-ten comparison, visible SHAP/history in 3.53 seconds, map click-through, reset, mobile layout, and no runtime exceptions |
| Built-in GIF decoder | Four frames decoded; screenshots and decoded GIF inspected |

Fresh-checkout timings and the publishing review will be recorded after execution.

## Publishing

M7 approval authorizes the planned public portfolio publication after local
verification and a tracked-file/history review. No live service deployment is
included. `.env`, model artifacts, installed environments, generated frontend
build output, and browser profiles remain outside version control.
