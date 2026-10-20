# OIO v0.4 — Live Data Research: Release and safety notes

**Status:** Local-only ZIP patch built for Windows evaluation. Existing v0.3 database is migrated additively. Production GitHub `main` was not changed by patch creation.

## Files updated/added
- `backend/app.py` — local API version bump, live schemas, three new control routes, two read routes.
- `backend/live_stream.py` (new) — controlled Jetstream WebSocket v1-JSON adapter, strict bounds, opt-in, provenance and TTL.
- `backend/requirements.txt` (new) — optional Python `websocket-client` dependency.
- `backend/laboratory.py` — expose source provenance in case JSON exports, new limitation note.
- `backend/test_app.py`, `backend/test_laboratory.py`, `backend/test_live_stream.py` (new) — migrated schema version tests and live unit/HTTP tests.
- `frontend/src/main.js`, `frontend/src/style.css` — new Live Data Research navigation, control form, sampled-record register and status UI.
- `README.md`, `docs/ROADMAP.md`, `docs/ETHICS.md`, `docs/RELEASE-v0.4.md` — setup, responsible research limitations, testing.

## Explicit design decisions
- **Opt-in** button and local acknowledgment, no background feed ingestion.
- **Server-side** collection filtering to post record events; **local-only literal keyword matching** on text.
- Fixed allowlist of two official service hosts; TLS WebSockets only.
- One capture at a time, 3-second cooldown; bounded time (15–180 sec), per-session saved posts (5–200), scan (50,000 messages), total local storage (5,000 live posts).
- No infinite reconnection/retry; after connection loss user may manually begin another bounded session.
- Observed Jetstream `time_us` used for detector windows; user-authored `createdAt` stored as a *claim* in provenance. DIDs, CIDs and external record links are unverified.
- Captured-post ID keyed by DID and record key, so re-seen content is not duplicated.
- In-stream update/delete removes an earlier captured version; updates outside the session are not monitored.
- All live posts, capture metadata and session logs removed by retention maintenance after seven days (up to one hour scheduling resolution while the server is running) or manual purge. Existing demo data, notes and manual references are not changed by manual purge.

## Developer verification

```powershell
cd D:\WebstormProjects\oio\backend
python -m pip install -r requirements.txt
python -m unittest discover -v
python app.py
```

In another terminal:

```powershell
cd D:\WebstormProjects\oio\frontend
node --test src\lab-utils.test.js
npm run build
npm run dev
```

Then use the Live Data Research screen for a **short live observation**, inspect counts and sample source links, stop it, ensure restart doesn't reconnect, and test purge after a database backup.

**Testing in build environment:** all backend tests and existing JS utility tests can run offline with fake event streams. Outbound Bluesky network connectivity and production Vite compilation **cannot be validated in this environment**; please verify locally. Zero keyword matches in a live short run is normal.

## Responsible interpretation

A suspicious synchronization cluster is a *lead for human investigation*; never an automated judgment that accounts are fake, illegal, linked to a data centre, or controlled by a particular actor. Raw captured posts are not reliable prevalence measurements. Public publication remains disabled. Data minimization and source/terms evaluation are mandatory before sustained real-world deployment.
