# Evidence and publication principles

1. Coordination is not inherently malicious. Grassroots advocacy, news sharing, and fandom can produce the same signals.
2. Treat every automated flag as an investigative lead, not a verdict.
3. Human review must consider alternative explanations, source authenticity, and counterevidence.
4. Public reports should focus on campaign-level behaviour; minimize identifiable information and avoid exposing private individuals.
5. Record provenance and methodology; support correction, appeal and removal requests.
6. Comply with source terms, applicable data protection law, and retention limits.
7. Never attempt unauthorized server access, deanonymization, or intrusive infrastructure tracing.
8. The prototype's fixture URLs are illustrative placeholders, not evidence.

## Addendum: v0.4 Bluesky public data

9. The Jetstream connection is an opt-in, short **observation**, not a verified firehose archive or a census of any population. All posts are treated as potentially misleading or edited; official record provenance is not cryptographically verified by the JSON adapter.
10. Data collection is limited to public post-record events and stored keyword matches, in bounded batches, locally. The keyword filter is applied client-side; the transport still receives many non-matching public post records transiently, which OIO does not store.
11. Post text and public DIDs can be personal data. Apply a strict data minimization/retention policy and allow deletion; case notes or exports may retain copies independently, and must be reviewed separately.
12. A short interval with zero matching content, or an exact-text match across multiple accounts, says **nothing reliable** about the size of bot populations or who controls the accounts. Avoid publishing individual-account allegations.
13. Do not run this prototype on a publicly accessible interface. A permission checkbox is not a substitute for a lawful basis, source terms review, privacy impact assessment or independently verified research methodology.
