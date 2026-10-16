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

## Timed README rehearsal

`python .tooling/m7-quickstart.py` passed on source revision
`4771e4b3c1ac97c2ea5c3f2483c6bb2182dc884c`. It cloned committed sources into
`.tooling/gridwatch-m7-07300c59`, copied the example configuration with a generated
local password, and used ports 18200/15200 and a separate Compose project.

| README step | Elapsed |
| --- | ---: |
| `make up` | 30.38 seconds |
| `make seed` | 26.46 seconds |
| `make train` | 38.08 seconds |
| Complete clone-to-working-browser rehearsal | **119.38 seconds (1m59s)** |

The browser opened the fresh app, clicked **Rescore network**, waited for **Views
refreshed**, confirmed 3,000 scored assets and a ready map, then opened the top-ten
transformer explanation and outage history. There were no runtime exceptions.
No host environment, installed npm packages, `.env`, database, or model artifacts
were copied into the clone. Node/Edge were used only to automate the browser
verification; the README runtime path requires no host npm/uv setup.

Docker base images, build layers, and dependency caches were already present.
This is a fresh-checkout and empty-state measurement, not a cold-download timing
guarantee. Prerequisite installation, manual password editing, and cleanup are
outside the measured interval. Slow image downloads can exceed ten minutes.
The isolated containers and database volumes were removed after verification;
the original demo and model registry were preserved. The machine-readable receipt
is ignored at `.tooling/m7-quickstart.json`.

## Publishing

M7 approval authorizes the planned public portfolio publication after local
verification and a tracked-file/history review. No live service deployment is
included. `.env`, model artifacts, installed environments, generated frontend
build output, and browser profiles remain outside version control.

The prepublication review passed for 305 historical blobs and 24 local Markdown
file/image links. It checks historical blobs for common GitHub/OpenAI/AWS
credential patterns and private keys and rejects tracked `.env`, model binaries,
bytecode, installed dependencies, or frontend build output. This supplements
manual review of configuration, synthetic-data sources, docs, and screenshots;
it is not a guarantee that every possible secret format can be detected.
