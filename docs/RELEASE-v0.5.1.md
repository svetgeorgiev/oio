# OIO v0.5.1 — European Research Expansion

**Status:** ZIP patch prepared for user testing. Do not tag or merge until real Bluesky sessions, fresh install and database migration have been verified on Windows.

## Baseline and patch layering

The **GitHub `main` branch was at v0.4** when this package was prepared. This ZIP contains **all changes from v0.5 plus v0.5.1** so it may be extracted over either local v0.4 or previously extracted v0.5. It never overwrites the local SQLite database, node_modules, Git files or environments. Backup your database with the backend fully stopped before extraction.

## Functionality

- Analyst-chosen regional **topic** presets (`custom`, `eu`, `uk`, `bg`, `de`, `fr`), with editable OR search phrases (1–3).
- Optional declared post-language allowlist, validated server-side (0–6 BCP47-like tags). A selected language excludes missing/unknown `record.langs`.
- IANA Europe timezones in collection and observation views; detector evidence and search date ranges remain in UTC.
- Session metadata includes profile ID, filter languages and global Jetstream endpoint. Each new captured post records profile ID and **unverified** public `record.langs` with other existing provenance.
- Signal Research adds **local** filters for recorded research profile and language; it does not imply author location.
- SQLite schema version **6**, additive migration from v0.4/v0.5 and repeatable without deleting capture data, investigation notes or evidence.
- First-pass public contribution guidelines, security policy, issue/PR templates and GitHub Actions tests.

## What this DOES NOT provide

- No European-only relay, geolocation, account nationality or IP detection.
- No unlimited streaming, private API, automated report publishing, identity correlation or bot verdicts.
- No change to the 7-day live post retention, 50,000 event scan bound, per-session caps or localhost-only deployment.
- No detection changes beyond v0.5's explainable exact-text / near-text / shared-link candidate rules.

## Windows QA checklist

1. Stop both servers and back up `data.sqlite3` **outside** the repository while closed. Extract to `D:\WebstormProjects\oio` and replace existing source files.
2. Run `cd backend; python -m unittest discover -v`. Then `cd ..\frontend; node --test src\lab-utils.test.js src\research-utils.test.js src\region-utils.test.js; npm run build`.
3. Confirm the original v0.4/v0.5 saved posts and investigations still display and schema was migrated to 6.
4. In Live Data Research choose **Bulgarian topics**: see a Bulgarian keyword preset, `bg` as default declared language, `Europe/Sofia` display zone, and US relay endpoints still shown separately.
5. Run one **short authorized** Bulgarian-tagged public observation. It may return zero matching posts and this is not necessarily a bug. Changing a preset's editable keywords should change collection results.
6. Repeat with UK or EU topics, blank the language filter for multilingual observation. Compare saved posts by research profile and declared languages; do **not** infer where authors live.
7. Restart backend; check session report profile and language tags persist. Open Signal Research and filter local post register by profile and language.
8. Confirm the old v0.5 pattern detectors still work; no candidate signal from a small sample is normal. Confirm manual data deletion/retention still works without touching investigation notes.
9. Review diff and ensure local databases and captures are never staged before committing to main.

## Contributor launch checks

GitHub workflow checks Python tests, JS utility tests and Vite build for PRs. Read `CONTRIBUTING.md`, `SECURITY.md`, `docs/ETHICS.md`, and `docs/REGIONAL-RESEARCH.md`. All fixtures must be synthetic or privacy-preserving and licensed for redistribution. The public repository is **source-code only**, not a hosted public reporting service.
