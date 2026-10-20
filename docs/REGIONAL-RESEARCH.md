# Regional research methodology (v0.5.1)

## The global feed is not a geographic feed

Official Bluesky Jetstream `us-east` and `us-west` endpoints describe **relay locations**, not account or post origin. Both distribute public network events; selecting either cannot restrict the feed to Europe. OIO does not request GPS, IP addresses or account private metadata, and does not attempt to infer nationality or place of residence.

## Topic presets, not person-location filters

OIO provides neutral research presets for European Union topics, the UK, Bulgaria, Germany and France, plus a custom option. A preset supplies editable literal keyword phrases, an optional public-record declared-language filter and a **display timezone**. Profiles are *analyst decisions*, not assertions about the posts they match.

- `EU`: topics for public EU affairs; no language restriction by default.
- `UK`: UK topics and declared `en` by default.
- `BG`: Bulgarian topics and declared `bg` by default.
- `DE`, `FR`: local topics and matching declared languages by default.
- `custom`: no automatic keywords; researcher supplies 1–3 literal phrases.

The language filter is **opt-in and editable**. An empty list accepts all language tags and posts without a `langs` field. When a filter is chosen, posts with missing/unknown `record.langs` are excluded, even if their text appears to match. A `bg` filter accepts tags such as `bg-BG` but not a different primary language; an exact `en-GB` filter matches only that language tag. Client-supplied tags can be absent, misleading or wrong. OIO does not automatically detect or translate languages.

A post about Sofia could be created outside Bulgaria; a post marked `bg` could be written anywhere; EU institution terms can be repeated globally. None of this supports geographic origin, bot identification or operator attribution.

## How sessions and evidence preserve method

- A bounded live session saves the chosen `profile_id`, its literal keyword list, selected declared-language tags, relay endpoint, session limits, timestamps and stop reason.
- Matching posts save their **declared tags** and the selected **topic profile** alongside existing source provenance. Old v0.5 captures are migrated with profile `custom`, languages `[]` (unknown) without rewriting the observed text.
- Signal Research can filter the *local post register* by selected topic profile or declared language, in addition to dates and keywords. **Candidate coordination signals are still calculated over the complete stored dataset, not over filtered search results.**
- Timezone is only a display preference. Evidence timestamps and detector windows remain UTC. A UK profile uses `Europe/London` and Bulgaria `Europe/Sofia`; daylight-saving transitions are handled by the browser's IANA timezone database.

## Selection bias, ethics and scientific limits

Short keyword-filtered Jetstream windows are **convenience samples**, not prevalence surveys of countries, languages, accounts or bots. Language missingness, platform adoption, connectivity, specific news stories and the three-phrase cap all affect what OIO saves. A dramatic coordinated burst might be completely legitimate. Do not derive EU population proportions or attribute campaigns to nations from OIO counts.

OIO never fetches private profiles or external URLs, never stores inferred location and never publishes unreviewed actor lists. Retention remains seven days for live captures; investigation notes and exports require a separate review. Consult data-protection obligations and platform terms before systematic research or public releases.
