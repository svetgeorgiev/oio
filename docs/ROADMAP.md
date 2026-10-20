# OIO Master Roadmap

## v0.1 — validated synthetic-data foundation

- [x] Vue dashboard, Python standard-library localhost API, SQLite persistence
- [x] Idempotent sample ingestion and exact-text / 180-second coordination candidates
- [x] Candidate evidence records and tests

## v0.2 — Investigation Workspace (this patch)

- [x] Redesigned workspace: Overview, Detection Queue, Network Explorer, Investigations and Methodology
- [x] Search and status filters for local candidates and cases
- [x] Graph linking a candidate text fingerprint to synthetic actor identifiers
- [x] Local case creation, reopen existing investigation, status transitions
- [x] Notes and alternative explanations; reason required for dismissal/closure
- [x] Case creation/edit audit trail (local events only)
- [x] SQLite additive migration preserving v0.1 data
- [x] Local API request validation, clean shutdown, HTTP integration tests
- [ ] UI tested and signed off on developer Windows/WebStorm environment
- [ ] Frontend converted to Vue single-file components via build-time compilation (not needed for v0.2 prototype)

## v0.3 — reliability and controlled research preparation

- [ ] Threat modelling: localhost cross-origin protection, operational boundaries, abuse cases
- [ ] Authentication and role-based authorization before any multi-user deployment
- [ ] Data retention/deletion workflows, backup/restore, exportable case evidence bundles
- [ ] Provenance integrity checks, evidence snapshots, reproducibility metadata
- [ ] Methodology evaluation with false-positive and negative controls
- [ ] Paginated candidate views for larger datasets; performance testing
- [ ] Accessible keyboard-friendly graph and investigative navigation improvements
- [ ] Source permission review and impact assessment before handling non-synthetic data

## v0.4 — permissioned source pilot (only after governance review)

- [ ] One approved data-source adapter with bounded ingestion and documented permission basis
- [ ] Background jobs, backoff, monitoring and data-quality alerting
- [ ] Independent accuracy / privacy review

## v1.0 — public transparency portal (separate from researcher workspace)

- [ ] Reviewed campaign-level reporting, documented uncertainties and alternatives
- [ ] Publication approval, redaction, correction and appeals workflow
- [ ] Public methodology, audit process and evaluation summaries

## Out of scope

- Private identity attribution, unauthorized access, doxxing, covert surveillance
- Unreviewed public account accusations and automated public blacklists
- Server intrusion, scraping around access controls and unconsented data aggregation
