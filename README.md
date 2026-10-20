# Open Influence Observatory (OIO)

**v0.4 — Live Data Research: LOCAL-ONLY research prototype.** OIO helps researchers inspect possible coordinated posting while preserving uncertainty and alternative explanations. **Matching posts are not proof of bots, common ownership, criminal activity or manipulation.** No public case publishing, login, identity attribution, or covert collection.

## Milestones

- **v0.1:** Synthetic fixture loader and SQLite exact-text / 180-second coordination signals.
- **v0.2:** Investigation cases, review statuses, notes, graph and audit trail.
- **v0.3:** Evidence Laboratory: manual references, permitted CSV/JSON import, timestamps, domain summaries and reproducible JSON/CSV exports.
- **v0.4:** **Explicitly started, short public Bluesky Jetstream observations**. A read-only collector receives `app.bsky.feed.post` event updates through Bluesky's official Jetstream legacy-JSON-compatible `/subscribe` endpoint, matches a **literal keyword locally**, and saves only matched public posts with stream provenance. Separate session report and captured-post list. No private access, full historical replay, account targeting, outside enrichment, or publishing.

## Install v0.4 on Windows / WebStorm

Requires **Python 3.10+**, **Node.js 20+**, npm, and a live Internet connection **only for optional Bluesky observation**.

1. **Stop both servers.** Back up `data.sqlite3` plus any `data.sqlite3-wal` and `data.sqlite3-shm` files with the backend fully stopped. Keep the backup **outside** Git and the OIO directory.
2. Extract `OIO-v0.4-Live-Data-Research-PATCH.zip` directly into `D:\WebstormProjects\oio`, selecting **Replace existing files**. No databases, Git metadata, `.env`, virtual environments, or `node_modules` are in this ZIP.
3. Open PowerShell in `D:\WebstormProjects\oio\backend`. Install the **optional** WebSocket connector dependency:

```powershell
python -m pip install -r requirements.txt
```

4. Start the backend:

```powershell
cd D:\WebstormProjects\oio\backend
python app.py
```

5. In another terminal, start the frontend:

```powershell
cd D:\WebstormProjects\oio\frontend
npm install  # Only required for a new checkout or if node_modules is absent
npm run dev
```

6. Open `http://127.0.0.1:5173`. The API stays bound to **127.0.0.1:8765**. **Never bind or expose the prototype publicly.** The repository's Vue runtime-compiler Vite configuration is preserved. No new frontend package dependencies.

## Live capture: how it works

1. Select **Live Data Research** in the sidebar. Choose a literal keyword/phrase of 4–64 characters. The phrase is **not** a regular expression and is matched case-insensitively **on your computer**, not on Bluesky's servers. Bluesky only filters the stream to post-record commits.
2. Choose **US East** or **US West** (official `jetstream.*.bsky.network` hosts), a **15–180 second duration** and a maximum of **5–200 newly saved posts**. The UI provides common presets. An independent **50,000-event scan limit** also stops a session; local total capacity is **5,000 live posts**.
3. Check the explicit permission/retention acknowledgment and select **Start observation**. The collector runs only after that click, connects to the official **WebSocket (WSS)** service, and **does not resume after backend restart**.
4. Watch statuses and the *last 60 saved posts*. `scanned` counts incoming event messages (including non-post events); `matched` counts matching creation events; `inserted` counts only new saved post IDs. Zero matches/clusters is normal, especially on short runs or narrow keywords.
5. The collector stops automatically at the time, per-session new-post or scanned-event limit, or manually with **Stop**. Connection failures appear as session errors. There is **no automatic reconnect** or unbounded retry loop.
6. `GET /api/clusters` continues to use the same intentionally basic **exact-text/180-second/three-actors** rule. Any clusters are shown alongside synthetic examples. Open an investigation and inspect provenance in Evidence Laboratory, treating every signal as **unverified**.

**Privacy and retention:** matched public posts contain text and a public decentralized identifier (DID); this may constitute personal data. Data remains on your local PC. OIO stores original-source URLs, event timestamps, source provider, supplied CID (not cryptographically verified), and session ID. Posts and old completed session metadata are pruned on backend startup, live-status checks, before new capture, and in hourly local-only housekeeping after **7 days**; idle deadlines may vary by up to an hour. **Delete all captured live posts** clears live post bodies, provenance and session logs immediately after confirmation; synthetic records and manually written investigation notes or evidence **are not deleted**, and cases with purged posts may no longer have a linked source cluster. Researchers are responsible for separately reviewing and deleting personally identifying material in analyst notes and exports.

**About deletion/update events:** if a post deletion/update passes through Jetstream **while a session is active**, OIO removes the previously saved version. Changes outside the observation interval may not be noticed. Jetstream's plain JSON stream is **not a cryptographically verified archive** and post existence/authenticity is not independently rechecked by OIO.

## Local validation checklist

1. On existing v0.3 database, confirm **5 synthetic posts**, the existing cluster/investigation, and manual Evidence Laboratory entries remain intact after upgrade. `GET /api/health` now reports v0.4.
2. Open **Live Data Research**: no connection should start automatically; counters should be zero for a new workspace. Check disabled Start until permission is acknowledged.
3. Start with a relatively common phrase for **30–60 seconds**, 25–100 posts. Verify state changes (`connecting` → `running` → `finished`) and statuses show the reason. Capturing zero matching posts is **not a test failure**; it depends on network traffic.
4. Verify saved posts have source links, public DIDs and local capture counts. Refresh; the records should persist. Retry with an exact phrase and ensure duplicates aren't stored twice.
5. Click **Stop** during an active session. It should finish without crashing Python.
6. Run **Delete all captured live posts** with its exact confirmation phrase; ensure live count becomes zero **but the five synthetic demo posts remain**. Do not clear live posts if you need their linked cluster evidence for an existing case.
7. Verify network/data errors show in the UI without breaking Overview, Investigations or Evidence Laboratory. Try restarting the backend; it should **not** reconnect automatically.
8. Run tests and build commands below, then commit to GitHub only after inspecting the diff.

If connection fails, check `python -m pip show websocket-client` and Windows outbound TLS/WebSocket permissions. The upstream service may be temporarily unavailable; this repository cannot guarantee external service availability. Do not bypass network restrictions.

## Automated tests

```powershell
cd D:\WebstormProjects\oio\backend
python -m unittest discover -v

cd ..\frontend
node --test src\lab-utils.test.js
npm run build
```

Backend tests stub the WebSocket stream; they **do not** contact Bluesky. The Vite production build must be confirmed locally. The `frontend/package.json` version remains `0.1.0` as inherited from the original prototype; the API/footer reflect `0.4.0`.

## New local APIs (v0.4)

| Method | Route | Purpose |
|---|---|---|
| GET | `/api/live/status` | Current/last session state, metrics and retention limits |
| GET | `/api/live/posts` | 60 most recently stored, matched, public posts |
| POST | `/api/live/start` | Explicitly start **one** bounded observation; full configuration + permission flag required |
| POST | `/api/live/stop` | Request stop; no automatic auto-restart |
| POST | `/api/live/purge` | Clear live posts and capture sessions with exact confirmation |

`POST /api/live/start` JSON example:

```json
{"keyword":"public announcement","region":"us-east","duration_seconds":60,"max_posts":100,"permission_confirmed":true}
```

Stop conditions and errors are returned as session metadata from `/api/live/status`. The API is local-only with DNS-rebinding Host and Origin checks, **not** remotely authenticated. Existing v0.1–v0.3 APIs still work.

## Known limitations, governance & next work

- Jetstream data is publicly broadcast but the legacy JSON event is **not independently signature-verified**. Record CID/actor DID are provenance leads, not proof of control or true identity. Official specs: https://bsky.network/docs/protocol-services/ , https://github.com/bluesky-social/jetstream/blob/main/docs/README.md , https://atproto.com/guides/streaming-data .
- **Biased convenience sample:** broad public stream truncated by keyword, 50,000 event cap, time range and save limits. No network-wide prevalence estimate or political classification is supported. A synchronized repost from legitimate users can look identical to coordination.
- Public data access still requires reviewing applicable terms, privacy law and retention; local permission checkbox does not itself establish legal entitlement to retain or publish content. No public deployment until authentication, source governance, DPIA where appropriate, abuse prevention, correction/removal processes and independent review.
- There is no full historical backfill, verified deletion mirroring, NLP similarity, automatic bot scoring, real identity attribution, DNS investigation, scraping, screenshot archive, or public report publishing.
- Next: improve research methodology, validate capture quality on Windows, analyze benign false positives, develop a verified-retrieval path with independent controls and a documented source policy.

See `docs/ROADMAP.md`, `docs/ETHICS.md`, `docs/RELEASE-v0.4.md`.
