# Open Influence Observatory (OIO)

**v0.5.2 — Collector Diagnostics: LOCAL-ONLY research prototype.** OIO helps researchers inspect possible coordinated posting while preserving uncertainty and alternative explanations. **Matching posts are not proof of bots, common ownership, criminal activity or manipulation.** No public case publishing, login, identity attribution, or covert collection.

## Collector Diagnostics (v0.5.2)

**Live Data Research** now exposes aggregate filter-funnel counts for **new** sessions: received messages → public post creations → eligible text posts → literal keyword matches → language-filter rejections → accepted source-valid matches → newly saved posts. It also reports limited, self-declared `record.langs` tag counts and the number of text-bearing posts with unknown/missing language metadata. The counts are diagnostics for one biased, bounded stream sample; they are **not evidence of where users live or whether they are bots**.

Choose **Capture + diagnostics** (default) to preserve v0.5.1 post-saving behavior. Choose **Diagnostics only** to observe events transiently, compute counters and test your keywords/language criteria, while **not saving new post content, account identifiers or source links**. Your previously stored live posts stay untouched. The session still stores the researcher's query settings, timestamps and aggregate counts for up to seven days. Old sessions are explicitly marked as not having diagnostic data.

See [v0.5.2 release notes](docs/RELEASE-v0.5.2.md) for field definitions, privacy limits and a Bulgarian zero-match test plan.

## European topic research (v0.5.1)

The global Bluesky Jetstream relay does **not** offer an EU-only stream. The US East/West options choose public stream servers, not author locations. In **Live Data Research**, select an editable **EU, UK, Bulgaria, Germany or France topic preset**, then optionally apply a strict filter using publicly declared `record.langs` tags. Selecting a language excludes records with no declared tag. A profile records investigator intent, **not nationality, residence, server hosting or bot identity**. The **Signal Research** post register supports optional saved-profile and language filters; candidate signals remain based on all locally stored posts. Regional clocks are presentation only; stored timestamps remain UTC.

Details and limitations: [Regional Research Methods](docs/REGIONAL-RESEARCH.md). Contributors: [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md).

## Milestones

- **v0.5.2:** Local filter-funnel diagnostics and a bounded aggregate-only discovery mode. No source text or account identifiers stored in the latter.
- **v0.5.1:** Editable European topic presets and client-declared language-tag filters (not geography).

- **v0.1:** Synthetic fixture loader and SQLite exact-text / 180-second coordination signals.
- **v0.2:** Investigation cases, review statuses, notes, graph and audit trail.
- **v0.3:** Evidence Laboratory: manual references, permitted CSV/JSON import, timestamps, domain summaries and reproducible JSON/CSV exports.
- **v0.4:** **Explicitly started, short public Bluesky Jetstream observations**. A read-only collector receives `app.bsky.feed.post` event updates through Bluesky's official Jetstream legacy-JSON-compatible `/subscribe` endpoint, matches one or up to three OR-separated **literal phrases locally**, and saves only matched public posts with stream provenance. Separate session report and captured-post list. No private access, full historical replay, account targeting, outside enrichment, or publishing.

- **v0.5:** **Local Signal Research** with post search (literal phrase, actor, URL, source and UTC dates), chronological bins, and *additional* conservative coordination leads from longer near-matching wording and sharing of the same full external URL. Public facet/embed links on **newly captured** Bluesky records are preserved as unverified source metadata. Cases and graphs work for all three signal types. No automatic bot scoring, accusations, or public posting.

## Install v0.5.2 on Windows / WebStorm

Requires **Python 3.10+**, **Node.js 20+**, npm, and a live Internet connection **only for optional Bluesky observation**.

1. **Stop both servers.** Back up `data.sqlite3` plus any `data.sqlite3-wal` and `data.sqlite3-shm` files with the backend fully stopped. Keep the backup **outside** Git and the OIO directory.
2. Extract `OIO-v0.5.2-Collector-Diagnostics-PATCH.zip` directly into `D:\WebstormProjects\oio`, selecting **Replace existing files**. No databases, Git metadata, `.env`, virtual environments, or `node_modules` are in this ZIP.
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

## v0.5.1 — Language and topic scope

**Global public stream, not geographic targeting:** EU/UK/BG/DE/FR presets select editable text search phrases and an optional declared-language allowlist. You can remove the language selection to include multilingual and untagged posts. Stored posts retain their selected *research profile*, unverified `record.langs` and the usual Jetstream provenance. The observation session remembers both settings. See [Regional Research Methods](docs/REGIONAL-RESEARCH.md) for known selection biases and locality limitations.

## Live capture: how it works

1. Select **Live Data Research** in the sidebar. Choose a literal keyword/phrase of 4–40 characters each (up to 3 separated by `|`, 90 characters total). These phrases are **not** regular expressions and are matched case-insensitively **on your computer**, not on Bluesky's servers. Bluesky only filters the stream to post-record commits.
2. Choose **US East** or **US West** (official `jetstream.*.bsky.network` hosts), a **15–180 second duration** and a maximum of **5–200 newly saved posts**. The UI provides common presets. An independent **50,000-event scan limit** also stops a session; local total capacity is **5,000 live posts**.
3. Check the explicit permission/retention acknowledgment and select **Start observation**. The collector runs only after that click, connects to the official **WebSocket (WSS)** service, and **does not resume after backend restart**.
4. Watch statuses and the *last 60 saved posts*. `scanned` counts incoming event messages (including non-post events); `matched` counts matching creation events; `inserted` counts only new saved post IDs. Zero matches/clusters is normal, especially on short runs or narrow keywords.
5. The collector stops automatically at the time, per-session new-post or scanned-event limit, or manually with **Stop**. Connection failures appear as session errors. There is **no automatic reconnect** or unbounded retry loop.
6. `GET /api/clusters` now checks **exact text / 180 seconds**, **near-duplicate long text / 600 seconds**, and **same full external URL / 600 seconds**, always requiring at least 3 distinct source/actor pairs. Any clusters are shown alongside synthetic examples. Open an investigation and inspect provenance in Evidence Laboratory, treating every signal as **unverified**.

**Privacy and retention:** matched public posts contain text and a public decentralized identifier (DID); this may constitute personal data. Data remains on your local PC. OIO stores original-source URLs, event timestamps, source provider, supplied CID (not cryptographically verified), and session ID. Posts and old completed session metadata are pruned on backend startup, live-status checks, before new capture, and in hourly local-only housekeeping after **7 days**; idle deadlines may vary by up to an hour. **Delete all captured live posts** clears live post bodies, provenance and session logs immediately after confirmation; synthetic records and manually written investigation notes or evidence **are not deleted**, and cases with purged posts may no longer have a linked source cluster. Researchers are responsible for separately reviewing and deleting personally identifying material in analyst notes and exports.

**About deletion/update events:** if a post deletion/update passes through Jetstream **while a session is active**, OIO removes the previously saved version. Changes outside the observation interval may not be noticed. Jetstream's plain JSON stream is **not a cryptographically verified archive** and post existence/authenticity is not independently rechecked by OIO.

## v0.5 local signal research workflow

- Live Data Research now also accepts **up to 3 literal OR phrases separated by `|`** (e.g., `public announcement | local notice`) instead of only one keyword. All previous collection limits remain unchanged.
- Open **Signal Research** in the sidebar and search the **already saved** public captures. This screen does not request more records from any platform.
- Search by text, public actor identifier, or URL; choose live-only (default) or all local records; optionally filter UTC dates. The result count is explicit, with at most **100 visible rows** per search.
- Review three separate lead types: **Exact text** (3 actors / 180 seconds), **Similar wording** (3 actors / 600 seconds, long text, token-bigram Jaccard at least 0.78) and **Shared link** (3 actors / 600 seconds, same normalized external URL with a path). The near-text detector deliberately misses many paraphrases; no semantic language-model analysis is performed.
- Full external URLs in public post text are considered, plus public **facet/embed external links** captured in v0.5+ sessions. The latter are stored separately in provenance and **do not alter the post text**. Older sessions cannot retroactively recover embedded link metadata.
- Research leads appear in the existing **Detection Queue** and can be opened as normal human-review investigations, with unchanged v0.1–v0.4 exact-text cluster identifiers. The Network Explorer labels each type of shared signal.
- Both the search and detectors operate **locally on retained records**. Existing 7-day live retention, bounded session limits and other privacy controls remain unchanged. These signals are not proof of bots, common control, intent, illegality, or scale of automation; normal news-sharing and campaigns can generate them.
- **Demonstration data is disabled by default** in v0.5 to protect real research from accidental contamination. The button was removed. To deliberately re-enable the fixture endpoint for an isolated test database only, start Python with `OIO_ENABLE_DEMO=1` in its environment. Do not enable it on your normal research database.

### API additions

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/research/search?q=news&scope=live&limit=60` | Literal local search with optional timezone-aware `from`/`to` ISO strings; bounded 100 rows |
| GET | `/api/research/signals` | Three candidate types, review links and explanation metadata; no bot score |
| GET | `/api/clusters` | Existing endpoint enhanced with conservative text/link research leads |

### v0.5 test commands (Windows)

```powershell
cd D:\WebstormProjects\oio\backend
python -m unittest discover -v
cd ..\frontend
node --test src\lab-utils.test.js src\research-utils.test.js
npm run build
```

> Migration note: the schema upgrades to SQLite `user_version=5`, adding one optional `external_links` provenance column. It preserves all existing v0.4 posts, cases, evidence references and capture sessions. Back up SQLite before updating. No new npm or Python requirements.

## Local validation checklist

1. On existing v0.3 database, confirm **5 synthetic posts**, the existing cluster/investigation, and manual Evidence Laboratory entries remain intact after upgrade. `GET /api/health` now reports v0.5.2.
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

Backend tests stub the WebSocket stream; they **do not** contact Bluesky. The Vite production build must be confirmed locally. The `frontend/package.json` version remains `0.1.0` as inherited from the original prototype; the API/footer reflect `0.5.0`.

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


## v0.5.1 local validation / contributor CI

This combined patch can be extracted over v0.4 or v0.5; the GitHub baseline at packaging time was v0.4. With the backend stopped, back up `data.sqlite3` outside the repository first. Do not commit your database or captured posts. Full checklist: [release notes](docs/RELEASE-v0.5.1.md).

```powershell
cd D:\WebstormProjects\oio\backend
python -m unittest discover -v
cd ..\frontend
node --test src\lab-utils.test.js src\research-utils.test.js src\region-utils.test.js
npm run build
```

These tests use synthetic public-event shapes. Actual Jetstream reachability and production frontend compilation must be verified on your own workstation. Do not expose the unauthenticated API to the Internet.
