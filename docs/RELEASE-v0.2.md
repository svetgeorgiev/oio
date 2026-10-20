# OIO v0.2 — patch release notes

**Baseline:** existing `svetgeorgiev/oio` main branch v0.1, as inspected on 20 October 2026.

## Files replaced

- `backend/app.py` — case records, audit log, migration, HTTP endpoints
- `backend/test_app.py` — regression and integration tests
- `frontend/src/main.js` — redesigned interactive Vue application
- `frontend/src/style.css` — new responsive workspace styling
- `README.md` — v0.2 setup, method limitations, test checklist
- `docs/ROADMAP.md` — progress and next milestones

## Files added

- `docs/RELEASE-v0.2.md` — this file

## Files intentionally not included

- No SQLite databases (your local `data.sqlite3` stays untouched)
- No node_modules, no npm package/lockfile changes
- No Git history or GitHub commits (developer reviews and commits locally)
- No `fixtures/sample_posts.json` changes
- No `frontend/vite.config.js` changes: keep your existing tested Vue compiler alias and `/api` proxy

## Upgrade process

Stop both servers, back up SQLite, extract patch into project root and restart. The backend creates missing v0.2 tables automatically; it does not delete the v0.1 posts or `reviews` table. Test the case workflow before committing. This is a **local development prototype**, not deployment-ready.

## Verification in package authoring environment

- Backend: `python -m unittest discover -v` → 10 tests passed
- JS source: `node --check frontend/src/main.js` → passed
- CSS and JS files created and packaged; static template was reviewed
- Vite production build: **not run here** because dependencies could not be installed offline; run `npm run build` in WebStorm, then check the UI
