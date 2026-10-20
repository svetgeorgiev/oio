# Contributing to Open Influence Observatory

Thank you for helping make public-interest research reproducible and careful. OIO is released under **GPL-3.0**. Contributions should respect the existing license and the [ethics policy](docs/ETHICS.md).

## Development workflow

1. Read [README.md](README.md), [regional research methods](docs/REGIONAL-RESEARCH.md), and [ETHICS.md](docs/ETHICS.md).
2. Use **synthetic fixtures** and mocked public events for tests. **Never include real account identifiers, scraped datasets, credentials, private records, or personally identifying investigator notes in Git.**
3. Open a GitHub issue describing the bug/feature, alternatives, test plan, and source permissions if it changes collection.
4. Fork or create a feature branch and open a pull request against `main`. Keep changes focused and explain how they affect research interpretation, retention, and consent.
5. Run backend tests (`python -m unittest discover -v` from `backend/`) and JS tests/build (`node --test src/*.test.js`, `npm run build` from `frontend/`). CI runs Python and Node checks too.
6. Attach screenshots from **synthetic test data** if proposing UI changes. Ask for a second reviewer before merging changes to detection methodology or privacy controls.

## Safety and scientific accuracy

- Pattern detectors may flag legitimate journalism, campaigning, communities, fandom or emergency sharing. Evidence is a **lead**, never an account verdict.
- Topic/language presets do not verify nationality, location, identity, automation, intent, or state sponsorship.
- Propose metrics with negative controls, reproducible fixtures, calibration notes and documented false positives; prefer precision over unsupported labels.
- No unauthorized crawling, private account enumeration, automated mass reporting, deanonymization, IP tracing, or public accusation features.
- OIO is **not ready for public hosting**: the backend is unauthenticated and localhost-only. Treat data in exports as sensitive.

## Submitting changes

In the PR description include the purpose, changed files, test results, known limitations, affected migrations and rollback instructions. For schema changes, always add a migration test preserving old local records. Do not upload real capture databases or evidence bundles in issues or pull requests.

**Security issues:** Follow [SECURITY.md](SECURITY.md); avoid disclosing exploitable defects in public issues.
