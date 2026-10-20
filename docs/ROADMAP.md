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

## v0.4 — Live Data Research (patch built; developer Windows test pending)
- [x] Official Bluesky Jetstream `/subscribe` JSON adapter with local keyword filter
- [x] User-confirmed Start and Stop, no auto-collection on startup/reconnect
- [x] 15–180-second bounded sessions, 5–200 saved posts, 50,000 streamed-event cap
- [x] Local telemetry and preserved event provenance (DID, CID-unverified, witnessed time, capture source/session)
- [x] Idempotent post ingestion, live-post register, existing detector/case integration
- [x] Local storage cap, 7-day pruning, explicit live-data purge
- [x] Unit and integration tests using synthetic WebSocket events (no Internet needed)
- [ ] Validate actual Jetstream connectivity from Windows in a short manual session
- [ ] Confirm `npm run build` and manual UI Start/Stop/purge; collect observed errors
- [ ] Review and document legal basis/source policy and data minimization before broader research use

## v0.5 — Methodology and source reliability
- [ ] Narrow sampling plans, coverage/denominator reporting, benign-comparison controls
- [ ] Source validation and deletion-policy checks with permitted endpoints
- [ ] Explicit uncertainty and false-positive benchmarking before public analysis
- [ ] Optional case cleanup when source material expires, plus investigator-visible deletion warnings
- [ ] Longer-running background jobs only after queue, robustness and audit design

## v0.6+ — Privacy, oversight and extensibility
- [ ] Auth/roles, permissions, quotas, source-specific terms assessments, user request handling
- [ ] Better network/temporal analysis; test against legitimate news sharing
- [ ] Public report drafts and independent reviewer sign-off with export redaction

## v1.0 — Separate public reporting portal (only after review)
- [ ] Campaign-level documented findings, not automated individual accusations
- [ ] Human publication authorization, privacy review, appeals, corrections and removals
- [ ] Reproducibility and governance transparency

## Explicit exclusions
No intrusion, bypassing platform restrictions, covert surveillance, private identity attribution, targeting accounts for harassment, server-operator identification from hosting IPs, automated political persuasion, public mass account blacklists or automatic bot verdicts.
