# OIO Master Roadmap

## v0.1 — validated synthetic-data foundation
- [x] Vue dashboard, Python localhost API, SQLite persistence
- [x] Idempotent sample ingestion; exact normalized-text/180-second candidates
- [x] Supporting source references and backend tests

## v0.2 — Investigation Workspace
- [x] Overview, Detection Queue, Network Explorer, Investigations and Methodology
- [x] Status/search filtering, graph of candidate text and synthetic actors
- [x] Create/reopen local cases, statuses, notes, alternate explanations, audit events
- [x] SQLite migration preserving earlier data, origin checks and API tests
- [x] Manually verified on Windows; backend tests and Vite production build passed

## v0.3 — Evidence Laboratory (current patch; local validation pending)
- [x] Add evidence register with observation, context and counterevidence categories
- [x] Optional claimed observation time, public source URL, metadata SHA-256
- [x] Bounded/atomic CSV+JSON metadata import, permission acknowledgement, deduplication
- [x] Timeline with distinct detector vs analyst observations (minute/hour/day)
- [x] Domain analysis with separate source-record, manual, and embedded-link categories
- [x] JSON research snapshot export + safe CSV register
- [x] Local evidence deletion with audit reason, additive SQLite schema migration
- [x] Backend/API/unit and JS helper tests; local API Host protection
- [ ] Validate full Vue UI and production build on developer's WebStorm environment
- [ ] Add evidence provenance quality controls and negative/false-positive benchmarks
- [ ] Accessible graph navigation and paginated datasets for higher scale

## v0.4 — permitted public-data pilot (planning; **not implemented**)
- [ ] Document licensing/terms, retention policy and lawful access for one candidate source
- [ ] Source adapter behind permission gates with bounded ingestion and backoff
- [ ] Assess data protection obligations and platform restrictions
- [ ] Independent accuracy, bias, and privacy evaluation using known benign coordination
- [ ] Explicit backup/restore and retention controls for cases

## v0.5+
- [ ] Robust content similarity, time-series comparison and network analysis with counterfactual tests
- [ ] Stronger reviewer workflows, independent sign-off, and publication risk assessment
- [ ] Authentication/roles, quotas, auditing and privacy enforcement **before** any multi-user hosting
- [ ] Accessible researcher documentation and independent methodology replication

## v1.0 — separate public transparency portal (after safeguards)
- [ ] Reviewed campaign-level reporting with limitations and counterevidence
- [ ] Publication approval and redaction, corrections and appeals
- [ ] External methodology and governance review

## Explicitly out of scope
- Private identity attribution, unauthorized access, account doxxing, covert surveillance
- Server intrusion, bypassing platform controls, automated accusations or blacklists
- Claims that a matching domain reveals a data centre or server operator
