# OIO Master Roadmap — 20 October 2026

## v0.1 — synthetic foundation ✅
- [x] Vue research dashboard, localhost Python API, SQLite persistence
- [x] Idempotent fixtures, normalized exact-text/180-second candidate detection, tests

## v0.2 — Investigation Workspace ✅
- [x] Detection queue, network explorer, case notes, status reviews, audit events
- [x] Data-preserving schema migrations, origin checks; tested on Windows

## v0.3 — Evidence Laboratory ✅
- [x] Manual source URLs and metadata hashing, permission-gated CSV/JSON import
- [x] Observational timelines and publicly mentioned domains, analyst/source separation
- [x] Exports, audit on reference deletion; manual testing and commit 0229063

## v0.4 — Live Data Research ✅ committed to main
- [x] Official Bluesky Jetstream `/subscribe` JSON adapter with local keyword filter
- [x] User-confirmed Start and Stop, no auto-collection on startup/reconnect
- [x] 15–180-second bounded sessions, 5–200 saved posts, 50,000 streamed-event cap
- [x] Local telemetry and preserved event provenance (DID, CID-unverified, witnessed time, capture source/session)
- [x] Idempotent post ingestion, live-post register, existing detector/case integration
- [x] Local storage cap, 7-day pruning, explicit live-data purge
- [x] Unit and integration tests using synthetic WebSocket events (no Internet needed)
- [x] Validate actual Jetstream connectivity from Windows in a short manual session (3,169 events; 59 matched posts)
- [x] Confirm `npm run build` and 33 backend tests on Windows; live session finished at time limit
- [ ] Review and document legal basis/source policy and data minimization before broader research use

## v0.5 — Signal Research (ZIP patch for local evaluation)
- [x] Allow up to 3 literal OR phrases per explicitly started live capture (same limits)
- [x] Search local captured posts by literal phrase, actor/source link, source and UTC dates
- [x] Conservative near-duplicate long-text lead detector (token bigrams, 10 min, 3+ distinct actors)
- [x] Shared full external-URL lead detector (10 min, 3+ actors) including public facet/embed URLs
- [x] Source provenance preservation and additive migration to schema v5
- [x] Existing detection queue and human-review case integration, without automated bot verdicts
- [x] Hide old fixture loader and disable its API unless explicitly enabled for isolated tests
- [x] Backend/JS tests with benign false-positive boundaries
- [ ] Confirm Windows Vite production build and observe real captures in the research screen

## v0.6 — Methodology and source reliability
- [ ] Narrow sampling plans, coverage/denominator reporting, benign-comparison controls
- [ ] Source validation and deletion-policy checks with permitted endpoints
- [ ] Explicit uncertainty and false-positive benchmarking before public analysis
- [ ] Optional case cleanup when source material expires, plus investigator-visible deletion warnings
- [ ] Longer-running background jobs only after queue, robustness and audit design

## v0.7+ — Privacy, oversight and extensibility
- [ ] Auth/roles, permissions, quotas, source-specific terms assessments, user request handling
- [ ] Better network/temporal analysis; test against legitimate news sharing
- [ ] Public report drafts and independent reviewer sign-off with export redaction

## v1.0 — Separate public reporting portal (only after review)
- [ ] Campaign-level documented findings, not automated individual accusations
- [ ] Human publication authorization, privacy review, appeals, corrections and removals
- [ ] Reproducibility and governance transparency

## Explicit exclusions
No intrusion, bypassing platform restrictions, covert surveillance, private identity attribution, targeting accounts for harassment, server-operator identification from hosting IPs, automated political persuasion, public mass account blacklists or automatic bot verdicts.


## v0.5.1 — European Research Expansion (candidate, local QA required)
- [x] European topic presets: EU, UK, Bulgaria, Germany, France and custom
- [x] Explicit declared-language filtering and capture provenance
- [x] IANA display timezones; UTC remains authoritative for analysis
- [x] Local post register filters for selected profile and language
- [x] Backward-compatible schema v6 migration, regression tests and CI workflow
- [x] Open-source contribution, security and methodology docs
- [ ] User verification: live post capture, timezone display and Windows Vite build
- [ ] Separate evaluation using representative benign and adversarial *synthetic* fixtures
- [ ] Independent source permissions and personal-data review before public hosting


## v0.5.2 — Collector Diagnostics (local QA candidate)
- [x] Per-session aggregate funnel counts (stream events, post creations, text posts, keyword hits, language rejections, accepted matches)
- [x] Declared-language histogram and unknown-language counter without saving unmatched posts
- [x] Explicit diagnostics-only mode: no newly saved post content, account IDs, URLs or CIDs
- [x] Seven-day session-report retention, additive SQLite schema v7 migration with old sessions distinguished
- [x] Simulated network test coverage for zero matches, source errors, bounded sessions and read-after-restart
- [ ] Verify actual session funnel and zero-post diagnostic mode on Windows/Bluesky
- [ ] Validate frontend Vite production build and GitHub Actions on proposed change
- [ ] Validate that a selected research preset never implies a user's location
