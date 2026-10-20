# Open Influence Observatory (OIO)

**v0.3 — Evidence Laboratory (local-only research prototype).** OIO is an evidence-first tool for exploring candidate patterns of coordinated public posting. It is **not** a bot classifier, network attribution tool or a public allegation platform.

## What's available

- **v0.1:** idempotent synthetic fixture ingestion, exact normalized-text signals in a three-minute window, SQLite persistence.
- **v0.2:** Vue investigation workspace, detection queue, network graph, case reviews, alternative explanations and local audit events.
- **v0.3:** Evidence Laboratory for a specific investigation:
  - Manually attach a public source URL with an evidence category (observation/context/counterevidence), description, optional claimed observation time and notes.
  - Import permitted evidence **metadata** in CSV or JSON (1–100 entries per upload, 128 KiB max), validated transactionally with duplicate detection.
  - Show detector posts separately from analyst-submitted references; never treat the two as equivalent sources.
  - Analyze minute/hour/day **observation timelines**, keeping analyst-supplied timestamps separate from detector timestamps.
  - Inspect public hostnames split into **source-record hosts**, **manual source-reference hosts**, and **domains embedded in post text**. No DNS lookup or web request occurs.
  - Export JSON research snapshots with method parameters, detector-linked source posts, case review notes, audit history and SHA-256 hashes of local evidence metadata. Export spreadsheet-safe CSV evidence registers.
  - Remove incorrectly saved manual evidence with a reason; an audit event records the removal, but the evidence metadata is deleted.
  - SQLite additive v0.3 migration preserving existing v0.1/v0.2 records and cases.

This version **does not** collect live social media data, scrape pages, archive website content, authenticate analysts, check whether sources are accurate, identify server operators, or publicly publish findings. **Do not deploy it on a public interface.**

## Install on Windows / WebStorm

Requires Python 3.10+, Node.js 20+, npm. Stop the backend and frontend before replacing files.

1. Back up your existing SQLite database with both servers stopped. At project root copy `data.sqlite3` **and any current** `data.sqlite3-wal` / `data.sqlite3-shm` companions outside the repository. Do not delete them from the working copy. SQLite's journal mode is WAL.
2. Extract **OIO-v0.3-Evidence-Laboratory-PATCH.zip** directly into `D:\WebstormProjects\oio`, preserving folders and replacing existing files. It only contains changed/new files; it does not include databases, `node_modules`, or Git metadata.
3. Start the Python API:

```powershell
cd D:\WebstormProjects\oio\backend
python app.py
```

4. In another terminal, start Vue:

```powershell
cd D:\WebstormProjects\oio\frontend
npm run dev
```

Visit http://127.0.0.1:5173. The backend stays bound to http://127.0.0.1:8765. This patch adds **no third-party dependencies**. If this is a new checkout, run `npm install` in `frontend` once.

## Smoke-test the Evidence Laboratory

1. Confirm your **5 demo posts / 1 cluster** and existing investigation remain after upgrade. If this is a new install, use **Load demo data**, then open a case from Detection Queue.
2. Open **Evidence Laboratory** from the sidebar or the investigation worksheet. Select the case.
3. Confirm the timeline shows **3 detected source posts**, no manual evidence, and a source-record hostname `example.org` (demonstration placeholder).
4. Check the permission box, then add a manual `context` reference using `https://example.org/demo/context`, a descriptive title and some notes. Leave observation time empty or choose a time. Save.
5. Confirm the new evidence appears with a SHA-256 hash and that the timeline only adds an analyst-reference observation **if you supplied a time**.
6. Download both JSON and CSV exports; open them and inspect separate `source_posts` and `evidence_items` fields in the JSON, and the escaped CSV cells.
7. Try importing `fixtures/sample_evidence.csv` (included in the ZIP). Import it twice: the second attempt should insert zero duplicates (or only new records if you manually added a different reference first).
8. Test **Remove**. A reason shorter than 10 characters should be rejected. A longer reason removes the item and adds an audit event.
9. Restart the backend. References, remaining cases and timestamps should persist. The old v0.2 case-review actions should still work.

## Automated tests

```powershell
cd D:\WebstormProjects\oio\backend
python -m unittest discover -v

cd ..\frontend
node --test src\lab-utils.test.js
npm run build
```

The frontend currently uses runtime Vue template compilation through the existing `vite.config.js` alias; this patch does not replace your working Vite setup. **The package name's npm version banner is still 0.1.0 from the original prototype; the API and application footer report 0.3.0.** Package metadata cleanup can be done separately.

## Evidence metadata schema

Manual entry (or CSV header keys): `kind`, `title`, `source_url`, `observed_at`, `notes`.

```json
[
  {
    "kind": "context",
    "title": "Public context example",
    "source_url": "https://example.org/demo/context",
    "observed_at": "2026-10-20T08:01:00Z",
    "notes": "Synthetic illustration; not independently verified"
  }
]
```

`kind`: `observation`, `context`, `counterevidence`. `source_url`: valid public http(s) URL, no embedded credentials or local/private IP. `observed_at`: optional ISO 8601 timestamp **with timezone**. If you select a date/time through the UI, it is interpreted in your browser's timezone and stored as UTC. `notes` is optional. Batch import is all-or-nothing for validation. Maximum of 500 stored manual references per investigation; repeated identical normalized metadata is deduplicated using its SHA-256 digest.

**Important:** SHA-256 covers OIO's normalized **local metadata**, not the live website or the truth of its content. It provides change detection for exported fields, not authentication of remote information. The original source may change or disappear. All manual notes and times remain **analyst claims**.

## Local API routes added in v0.3

| Method | Route | Purpose |
|---|---|---|
| GET | `/api/investigations/{id}/lab` | Evidence register, source posts, timeline, domains and audit |
| GET | `/api/investigations/{id}/lab/export` | JSON research snapshot and detector parameters |
| POST | `/api/investigations/{id}/lab/evidence` | Add manually supplied evidence metadata; permission confirmation required |
| POST | `/api/investigations/{id}/lab/import` | Import CSV/JSON metadata from user's chosen local file |
| POST | `/api/investigations/{id}/lab/evidence/{item}/delete` | Delete one manual reference with an audit reason |

Existing v0.1/v0.2 endpoints are unchanged. The localhost API has no login and has bounded JSON requests, same-origin mutation checks and localhost Host checks; these are **not** a substitute for authentication and data governance.

## Principles and caveats

- Detection signals are **not** evidence of bots, criminal conduct, ownership, intent, or orchestration.
- Matching public domains do not reveal where an account is hosted or who operates it.
- Never add personal information, confidential material or unauthorized datasets.
- The demo dataset and example.org URLs are synthetic placeholders.
- Public publication, automated import of real social network data and independent authentication of posts remain out of scope.
- See `docs/ETHICS.md`, `docs/ROADMAP.md`, and `docs/RELEASE-v0.3.md`.
