# Open Influence Observatory (OIO)

**v0.2 — Investigation Workspace (local-only research prototype).** OIO is an evidence-first research tool for investigating patterns of *potentially* coordinated public posting. It is **not** a bot classifier, attribution engine or public accusation platform.

## What changed in v0.2

- Sidebar workspace: Overview, Detection queue, Network explorer, Investigations, Methodology
- Candidate search and review-status filters
- Interactive relationship diagram for accounts sharing exact normalized text (synthetic fixture)
- Create one local investigation per candidate cluster; reopen existing ones without duplicates
- Editable title, status, reviewer notes and alternative explanations
- Append-only local activity log of case creation/field changes (no user identity recording)
- SQLite schema migration preserving v0.1 posts and legacy reviews
- Better API errors, bounded JSON bodies, origin check on writes, graceful Ctrl+C shutdown
- More backend unit and HTTP integration tests

**Important:** OIO still accepts *only* the bundled synthetic fixture. There is no live social media ingestion, AI bot verdict, public publishing, login, authorization or deployed server. Keep the backend bound to loopback.

## Requirements

- Windows with Python 3.10+ and Node.js 20+ (also works on other OSes)
- npm
- Existing v0.1 checkout, updated with files from the v0.2 ZIP

## Install the v0.2 patch into the existing project

1. **Stop** the backend and Vite frontend.
2. **Back up your database.** With both servers stopped, copy `data.sqlite3` (and any present `data.sqlite3-wal` / `data.sqlite3-shm` files) somewhere outside the repository. Do not delete local SQLite files.
3. Extract the ZIP **into the OIO project root**, e.g. `D:\WebstormProjects\oio`, preserving folders and choosing **replace existing files**.
4. The ZIP contains only files changed/added for v0.2; it does **not** contain `node_modules`, local databases, source fixtures, or Git metadata.
5. Run the two development servers below. Migration runs on first database access automatically.

**Terminal 1 (backend)**

```powershell
cd D:\WebstormProjects\oio\backend
python app.py
```

**Terminal 2 (frontend)**

```powershell
cd D:\WebstormProjects\oio\frontend
npm run dev
```

If dependencies are not already installed locally, run `npm install` in `frontend` first. No new npm dependencies are needed for this patch.

Visit **http://127.0.0.1:5173**. The API remains on `http://127.0.0.1:8765`.

## Testing

```powershell
cd D:\WebstormProjects\oio\backend
python -m unittest discover -v

cd ..\frontend
npm run build
```

Smoke-test the UI:

1. Overview loads with previous 5 demo posts / 1 cluster (if v0.1 data exists).
2. Clicking **Load demo data** again does not increase the ingested post count.
3. Detection queue shows the unreviewed cluster; search and filters work.
4. Network explorer shows the central shared-text node and three separate synthetic actors. Clicking an actor filters supporting records.
5. **Start investigation** creates a case; repeat action reopens it without a duplicate.
6. Enter notes and an alternative explanation; set status to **Needs context**, then save.
7. Try **Dismissed** with fewer than 10 characters of reviewer notes: the API should reject it.
8. Add adequate notes and save **Dismissed** or **Closed**; an audit event appears.
9. Stop and restart Python: the posts, case, status and notes should persist.

## API (all local only)

| Method | Endpoint | Meaning |
| --- | --- | --- |
| GET | `/api/health` | Version and local mode |
| GET | `/api/stats` | Aggregate counts |
| GET | `/api/clusters` | Detected candidates and synthetic evidence |
| GET | `/api/clusters/{id}` | One candidate |
| GET | `/api/investigations` | Private local cases |
| GET | `/api/investigations/{id}` | Case details and audit log |
| POST | `/api/load-fixture` | Idempotent synthetic import |
| POST | `/api/investigations` | Create/reopen case; body `{ "cluster_id": "..." }` |
| POST | `/api/investigations/{id}/review` | Update approved review fields |

## Detection methodology

OIO lowercases posts, removes URLs, collapses whitespace, hashes normalized text and groups identical content into 180-second non-overlapping windows; groups require three distinct `(source, actor)` pairs. A candidate means **only that this pattern matched the rule**. Synchronized legitimate campaigns, memes and news coverage can look the same. The prototype graph is a visual explanation of the grouping, **not proof of shared control**.

## Limitations and safety

- No authentication, no access controls for local cases; **do not expose this API publicly**.
- Do not use real private/personal datasets until permissions, data protection requirements, retention rules, user authentication and review governance are implemented.
- Audit log records edits and timestamps, **not identity or tamper-proof provenance**.
- Review status is for a *case*, not a verdict about people.
- Publishing remains intentionally disabled.
- For the original v0.1 ethics policy, see `docs/ETHICS.md`; planned milestones are in `docs/ROADMAP.md`.
