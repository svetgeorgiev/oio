# OIO v0.5.2 — Collector Diagnostics

**Status:** Drop-in local-only research patch built on v0.5.1. No GitHub push was performed by this patch. Tests use fake public Jetstream events: the new UI and diagnostics-only mode still require local Windows verification.

## Why this release exists

In a three-minute Bulgaria-topic observation on 20 October 2026, OIO scanned 10,782 Jetstream event messages with no matches for `България | София | Пловдив`, even after removing the declared-language restriction. v0.5.1 could not tell whether the absence of matches reflected few relevant public posts, other event types, or a filtering problem. **Scanned events are not the same thing as posts, much less accounts.**

v0.5.2 makes the filter funnel visible without weakening the privacy and collection limits.

## Two explicitly selected modes

- **Capture + diagnostics (default):** Existing v0.5.1 behavior. Store matched public posts (up to the existing user and platform limits), report aggregate counters and language tags.
- **Diagnostics only:** Read the same bounded global public Jetstream session and evaluate the user's literal keyword and declared-language filters, but **never save any newly encountered post bodies, account DIDs, post links, record CIDs, or per-post observations**. Store only the researcher's query settings, server region, timestamps, session status, aggregate counts, and per-language totals. Prior stored posts and evidence are unchanged.

Neither mode infers a user's country. The US East/West switch selects the Jetstream host, not the authors' locations. All network access remains manually started, limited to the two allowlisted TLS WebSocket endpoints, and stopped at 15–180 seconds or 50,000 observed events. Captures also respect the 5–200 post cap and 5,000 local live-post cap. No historical backfill, account targeting, private APIs, or public report publication.

## New diagnostic counters

| Field | Meaning |
|---|---|
| `scanned` | All stream messages, including irrelevant/invalid messages |
| `post_creations` | `commit` + `app.bsky.feed.post` + operation `create`, even if record text is invalid |
| `eligible_text_posts` | Post creations containing valid text of 1–3,000 characters |
| `keyword_matches` | Eligible text containing any selected literal phrase; ignores language filter |
| `language_rejections` | Keyword matches rejected by selected `record.langs` allowlist |
| `matched` | Keyword + language matches with valid required Jetstream metadata |
| `inserted` | Newly saved post records (always **0** in diagnostics-only mode) |
| `malformed_events` | Received messages that could not be processed as bounded JSON |
| `invalid_post_records` | Post creations with invalid text/record metadata, or matching posts failing source validation |
| `unknown_language_posts` | Eligible post texts with no usable declared language tag |
| `language_counts` | Counts of syntactically valid, self-declared `record.langs` tags on eligible text posts, **including posts excluded by keywords** |

Language counts are not geographically representative. A post declaring two languages contributes to two counts; unknown-language counts are separate. The in-memory tag map is capped and final display is limited to the most frequent 20 tags (overflow aggregated). Even a diagnostic session with zero keyword matches can still show a distribution of observed declared languages.

The diagnostic panel only appears for **new v0.5.2 sessions**. Older sessions receive default zero columns in the additive migration but are intentionally marked `diagnostics_available=0` to avoid displaying misleading historical zeroes.

## Database migration

`PRAGMA user_version=7`. Only new columns are added to `live_capture_sessions`; the `posts`, `live_post_provenance`, investigation and evidence tables are untouched. Completed diagnostic reports expire with ordinary live capture-session retention (7 days). Local analyst evidence may require separate retention decisions. A process restart never resumes capture. **Back up your SQLite database with Python stopped** before extracting.

## Local verification (Windows)

1. Stop frontend and backend and copy `data.sqlite3` outside the repository while the backend is stopped. Extract the patch over your current `D:\WebstormProjects\oio` folder.
2. Start both servers and open **Live Data Research**.
3. Set profile **Bulgarian topics**, keyword `България | София | Пловдив`, declared language **empty**, mode **Diagnostics only**, duration **60 seconds**. Confirm the session completes and `inserted=0` even when `matched` is nonzero.
4. Inspect the funnel: `scanned`, `post_creations`, `eligible_text_posts`, `keyword_matches`, `language_rejections` and `matched`. Note that a nonzero `post_creations` count with zero keywords is useful evidence of a *narrow sample*, not a bot conclusion.
5. Check the declared-language totals and unknown-language counter. None of these tags prove geography or nationality.
6. Verify the existing 13 stored posts remain unchanged, then **restart the Python backend** and confirm the aggregate report persists.
7. Try a broad control phrase such as `news | today | music` (no language filter) in a separate 60-second diagnostics-only session. **Do not compare prevalence from these different biased windows**; only use as a connector sanity check.
8. Test **Capture + diagnostics** for 30 seconds with a common keyword and verify both new counters and normal post saving still work.
9. Run all automated tests and frontend build before committing.

```powershell
cd D:\WebstormProjects\oio\backend
python -m unittest discover -v
cd ..\frontend
node --test src\lab-utils.test.js src\research-utils.test.js src\region-utils.test.js
npm run build
```

## Constraints, uncertainty and integrity

- No post text or account identity is persisted by diagnostics-only collection. The tool **does observe** public post bodies transiently in memory to evaluate filters. Treat local session searches, aggregate histograms and collection metadata as research records; they are not a representative population sample.
- Unlike verified repository proofs, Jetstream JSON messages are not independently signed or revalidated by OIO. Posts can later be edited or deleted outside an observation window.
- Counters describe only the captured stream window. Server issues, partial failures, message loss, source/client language mislabelling, keyword selection and time of day can affect counts.
- No individual-account bot labels, scoring, targeting, identity tracing, political classification or automated public accusations are produced.
- This local-only prototype has no accounts or authentication; do not expose its API to the internet. Review the source-access and data-retention requirements before broader research or hosting.

See `README.md`, `docs/REGIONAL-RESEARCH.md`, `docs/ETHICS.md`, `CONTRIBUTING.md` and `SECURITY.md`.
