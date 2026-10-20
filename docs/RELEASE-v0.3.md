# OIO v0.3 — Evidence Laboratory patch release

**Baseline:** GitHub `svetgeorgiev/oio`, `main`, commit `a2426824a15e53b47b6f192cd58169cbe10d93ec` (v0.2 Investigation Workspace).

## Changed files
- `backend/app.py` — v0.3 migration, API routes, local Host validation
- `backend/test_app.py` — existing tests updated, HTTP evidence API coverage
- `frontend/src/main.js` — Evidence Laboratory sidebar, forms, timeline, domains, register and exports
- `frontend/src/style.css` — new responsive laboratory styles
- `README.md` — installation, usage, API and safety limits
- `docs/ROADMAP.md` — milestone status

## New files
- `backend/laboratory.py` — evidence validation and local records, imports, hashes, case snapshots
- `backend/test_laboratory.py` — evidence security, atomic import, deduplication, migration, export tests
- `frontend/src/lab-utils.js` — pure timeline/chart aggregation and spreadsheet-safe CSV export
- `frontend/src/lab-utils.test.js` — Node built-in test suite for those helpers
- `fixtures/sample_evidence.csv` — two **synthetic** example.org context/counterevidence references
- `docs/RELEASE-v0.3.md` — this release guide

## Deliberately untouched
- `frontend/vite.config.js` and npm dependencies; preserve existing working runtime compiler alias/proxy
- `frontend/package-lock.json`, `frontend/package.json`; package metadata remains at legacy `0.1.0`
- `.gitignore`, `.git/`, `node_modules`, existing local `data.sqlite3` and journal files
- `fixtures/sample_posts.json`, original methodology and ethics file

## Verification in patch authoring environment
- Backend: **22 tests passed** (`python -m unittest discover -v`)
- JS: `node --check frontend/src/main.js` passed
- JS helper tests: `node --test frontend/src/lab-utils.test.js` → **2 passed**
- Source static/template validation performed
- **Vite production build not available in authoring environment:** npm dependencies not cached. Run `npm run build` and manual UI smoke tests in WebStorm before commit.

## Important scope boundary

This is a **local-only synthetic investigation prototype**. The Evidence Laboratory accepts *manually entered or locally imported* public URL metadata, with the user's acknowledgement of permission. OIO does not visit or independently authenticate those URLs. Exported SHA-256 digests apply to canonical metadata, not captured webpage bytes. Data must be reviewed before conclusions. No automatic real-world account collection, publication, attribution or bot verdicts are implemented.

## Upgrade and rollback

Stop backend + Vite, back up SQLite with any WAL/SHM companions, extract into project root, restart and validate. The schema migration adds `evidence_items` and updates `PRAGMA user_version` to 3, preserving previous tables and rows. Because database schemas are migrated forward, a code rollback should restore a backed-up v0.2 database too when strict rollback is required. No database files are shipped in this patch.
