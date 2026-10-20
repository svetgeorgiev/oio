# Open Influence Observatory (OIO)

**v0.1 — local-only, synthetic-data research prototype.** A public-interest, evidence-first project for studying coordinated online activity. This is **not** a bot detector or an attribution engine.

## Requirements
- Python 3.10+
- Node.js 20+
- npm

## Run on Windows (PowerShell)
Open terminal 1:
```powershell
cd backend
python app.py
```
Open terminal 2:
```powershell
cd frontend
npm install
npm run dev
```
Visit http://127.0.0.1:5173 and select **Load demonstration data**. SQLite is created in the project root. The backend binds only to 127.0.0.1. The sample is entirely synthetic.

## Tests
```powershell
cd backend
python -m unittest discover -v
```

## API
- `GET /api/health` — health check
- `GET /api/stats` — aggregate metrics
- `GET /api/clusters` — candidate clusters and source references
- `POST /api/load-fixture` — local-only, idempotent synthetic data import

## Detection methodology v0.1
Normalize text to lowercase, remove URLs, collapse whitespace; SHA-256 fingerprint. Group matching fingerprints into non-overlapping 180-second windows; flag windows with at least 3 distinct `(source, actor)` pairs. This is deliberately simple and prone to false positives (quotes, breaking news, organic campaigns). A flagged pattern is **not** evidence of bots, shared ownership, illegal conduct, or intent. The public case publication workflow is not implemented.

## Boundaries
No scraping, external ingestion, deanonymization, automatic accusations, credential access, or public publishing. API has no authentication and must **not** be exposed to the internet. Use platform-authorized access and review platform rules before building adapters. Do not collect private information or retain unnecessary personal data.

See `docs/ROADMAP.md` and `docs/ETHICS.md`.
