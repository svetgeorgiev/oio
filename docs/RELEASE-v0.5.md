# OIO v0.5 — Signal Research (local-only patch)

**Baseline:** `svetgeorgiev/oio`, GitHub `main` commit `87bced3` (v0.4). This patch does **not** commit or push anything to GitHub.

## Changed/new files

- `backend/research.py` (new): literal local post search; near-duplicate and shared-full-link candidate extraction.
- `backend/app.py`: read-only research endpoints, extra lead types in existing queue, version marker, synthetic fixture endpoint disabled unless explicitly enabled with `OIO_ENABLE_DEMO=1`.
- `backend/live_stream.py`: 1–3 optional OR-separated literal capture phrases (same strict duration/post limits), and additive provenance column for external link targets supplied in public Bluesky rich-text facets or embed cards. No link fetching.
- `backend/laboratory.py`: link provenance in reproducible exports and domain summaries.
- `backend/test_research.py` (new), `backend/test_live_stream.py`, `backend/test_app.py`, `backend/test_laboratory.py`: additional tests and schema 5 expectations.
- `frontend/src/main.js`, `frontend/src/style.css`: new Signal Research navigation, local search, observation histogram, leads and evidence inspection.
- `frontend/src/research-utils.js`, `frontend/src/research-utils.test.js` (new): pure, tested UTC bucket and query parameter helpers.
- `README.md`, `docs/ROADMAP.md`, `docs/ETHICS.md`, this document: validation, limitations and release notes.

## Safe installation

1. Stop OIO Python and Vite. Back up `D:\WebstormProjects\oio\data.sqlite3` (including WAL/SHM sidecars if any) **outside the repository** while backend is stopped.
2. Extract `OIO-v0.5-Signal-Research-PATCH.zip` directly into `D:\WebstormProjects\oio`; overwrite changed files. No `.git`, SQLite data, credentials, dependencies or unrelated files are included.
3. Start backend (`cd backend; python app.py`) and frontend (`cd frontend; npm run dev`); open `http://127.0.0.1:5173`.
4. Open **Signal Research**, run a local search for `news`, inspect observed records, then inspect the updated Detection Queue. A short sample might have **zero** leads. No extra remote requests are made by analysis.
5. Run `python -m unittest discover -v` under `backend` and `node --test src\lab-utils.test.js src\research-utils.test.js` + `npm run build` under `frontend`.
6. Check staged Git files; push only after validating locally.

## Detection methods and limits

- Live capture now allows 1–3 literal phrases separated by `|` (up to 90 chars total); matching is local and case-insensitive. No regex, arbitrary account lookups or increased observation quotas.

- Exact same normalized wording: existing 180-second window, 3 distinct source/actor pairs. Old 12-character cluster IDs remain stable.
- Near-duplicate longer wording: >=8 words, >=40 text characters, token-bigram Jaccard >=0.78, >=2 *different* normalized texts, >=3 actor pairs, 600-second anchored window. Fast candidate blocking by shared lexical shingles deliberately misses some variants. High-frequency blocking keys are skipped.
- Same external full URL: normalized hostname and full path, known tracking parameters ignored, shared by >=3 actor pairs inside 600 seconds. Domain-only matches are intentionally excluded. Facet/embed URLs are captured **only for new sessions**; historical records are not retroactively enriched.
- Research search: local storage only; arbitrary terms are literal, no account enumeration; source/UTC time filters; 1–100 response rows. Hourly chart is computed from the **visible** rows, not the full platform or even all results.
- Network payloads show at most 120 source references per lead (with explicit truncation notice), while retaining the full post and distinct-actor counts. The local searchable records are not deleted by this display limit.
- Findings are **investigative leads**, not bot scores, prevalence estimates, common control/intent claims, or attribution. Common breaking-news links, shared statements, petitions, and community campaigns produce similar patterns.

## Operational notes

- Schema migration: `PRAGMA user_version=5`; adds only `live_post_provenance.external_links` as a JSON array field, default `[]`. Captured data, analyst notes, cases and evidence persist.
- As in v0.4, deleted/updated posts outside an active Jetstream session may not be noticed, and JSON events are not cryptographically verified. Seven-day retention applies to live post bodies and provenance.
- Demo data is intentionally blocked on normal installs. Enable only in an **isolated test database** using `OIO_ENABLE_DEMO=1`. Existing synthetic records are not automatically deleted by this upgrade.
- The API remains localhost-only and unauthenticated: never publish it on the public internet.
- No new dependencies; the prior v0.4 `websocket-client` requirement is unchanged.
