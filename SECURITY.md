# Security policy

**Development prototype only.** OIO's local API is not authenticated, and captured public posts can be personal data. **Never forward ports, host this API publicly, or share the SQLite file.**

## Reporting vulnerabilities

Please do not publish exploitation instructions, credentials or captured personal data in a public issue. Use GitHub's **Report a vulnerability** private channel if enabled for this repository. If that option is unavailable, open a minimal issue asking the maintainers to provide a private contact channel **without including sensitive details**.

## Scope

- User-triggered, time-limited observation; no hidden background capture.
- Local-only API; Origin and Host header checks, but no remote authentication.
- Retained public posts have a seven-day default expiry; manually supplied notes and exported files require separate user review.
- A compromised local machine or browser can access the local database; protections here do not replace OS security.

Changes introducing public hosting or multi-user access require a security/design review, authentication, authorization, CSRF mitigation, safe data deletion and operational controls **before** release.
