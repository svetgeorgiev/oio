"""OIO v0.5: transparent, bounded, LOCAL analysis of previously captured public posts.

No network requests, bot scoring, identity attribution, or automated case publication.
Potential coordination is only a lead; breaking news and activism can cause matches.
"""
import hashlib
import json
import ipaddress
import re
from collections import defaultdict
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urlsplit
from regions import PROFILE_BY_ID, LANG_RE

URL_RE = re.compile(r'https?://[^\s<>"\'`]+', re.IGNORECASE)
WORD_RE = re.compile(r'\w+', re.UNICODE)
TRACKING_PARAMETERS = {'fbclid', 'gclid', 'igshid', 'mc_cid', 'mc_eid'}
EXCLUDED_HOSTS = {'bsky.app', 'example.org', 'localhost'}
NEAR_WINDOW = 600
LINK_WINDOW = 600
MIN_ACTORS = 3
MIN_TOKENS = 8
NEAR_THRESHOLD = 0.78
MAX_POSTS = 5000  # Storage cap from v0.4. Do not run unbounded historical scans.
MAX_EVIDENCE = 120  # Keep network views and HTTP payloads bounded.


def utc_seconds(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()


def normalized_text(text):
    return re.sub(r'\s+', ' ', URL_RE.sub('', text).casefold()).strip()


def shingles(text):
    tokens = WORD_RE.findall(normalized_text(text))[:160]
    if len(tokens) < MIN_TOKENS or len(text) < 40:
        return frozenset()
    return frozenset(zip(tokens, tokens[1:]))


def jaccard(a, b):
    return len(a & b) / len(a | b) if a and b else 0


def canonical_links(text):
    """Normalize literal URLs without network access. No DNS or redirects.

    Full paths must exist: common homepage hostnames are not useful evidence.
    Drop only known tracking parameters, retaining meaning-changing query params.
    """
    result = set()
    for match in URL_RE.findall(text):
        value = match.rstrip('.,;:!?)]}')
        try:
            parsed = urlsplit(value)
            hostname = (parsed.hostname or '').lower().rstrip('.')
            if not hostname or hostname in EXCLUDED_HOSTS or hostname.endswith(('.local', '.internal', '.localhost')):
                continue
            try:
                address = ipaddress.ip_address(hostname)
                if not address.is_global:
                    continue
            except ValueError:
                if '.' not in hostname:
                    continue
            if not parsed.path or parsed.path == '/':
                continue
            if parsed.port not in (None, 80, 443):
                # Avoid grouping unrelated applications on nonstandard ports.
                hostname += ':' + str(parsed.port)
            path = parsed.path.rstrip('/') or '/'
            params = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
                      if k.casefold() not in TRACKING_PARAMETERS and not k.casefold().startswith('utm_')]
            suffix = '?' + urlencode(sorted(params)) if params else ''
            result.add(hostname + path + suffix)
        except ValueError:
            continue
    return result


def _item(post):
    return {'id': post['id'], 'source': post['source'], 'actor': post['actor'],
            'url': post['url'], 'created_at': post['created_at']}


def _candidate(kind, anchor, members, pattern, sample_text, reason):
    return {'id': kind + '-' + hashlib.sha256((kind + '|' + anchor).encode()).hexdigest()[:12],
            'signal_type': kind, 'pattern': pattern, 'reason': reason,
            'distinct_actors': len({(p['source'], p['actor']) for p in members}),
            'post_count': len(members), 'first_seen': members[0]['created_at'],
            'last_seen': members[-1]['created_at'], 'sample_text': sample_text,
            'evidence': [_item(p) for p in members[:MAX_EVIDENCE]],
            'evidence_truncated':len(members) > MAX_EVIDENCE}


def time_batches(posts, window):
    """Non-overlapping windows anchored at the first post; no chain bridging."""
    current = []
    first = None
    for post in sorted(posts, key=lambda p: (p['created_at'], p['id'])):
        t = utc_seconds(post['created_at'])
        if current and t - first > window:
            yield current
            current = []
        if not current:
            first = t
        current.append(post)
    if current:
        yield current


def detect_patterns(posts):
    """Conservative lead candidates. Stable IDs use the first supporting post.

    Near-text: long messages, min 3 distinct actors, multiple variations, 0.78
    token-bigram Jaccard similarity relative to an anchor within 10 minutes.
    Candidate retrieval uses 4 lexical shingle keys to avoid O(n^2) globally.
    Some genuine similarities may be missed; this is a recall/precision trade-off.

    Shared link: same canonical FULL external URL within 10 minutes across
    3 actors. Common media links may be shared entirely organically.
    """
    posts = sorted(posts[:MAX_POSTS], key=lambda p: (p['created_at'], p['id']))
    results = []

    # Link candidates are grouped by the full URL, not simply domain names.
    by_link = defaultdict(list)
    for p in posts:
        literal_links = canonical_links(p['text'])
        try:
            external = json.loads(p.get('external_links') or '[]')
        except (TypeError, json.JSONDecodeError):
            external = []
        if isinstance(external, list):
            for url in external[:10]:
                if isinstance(url, str):
                    literal_links.update(canonical_links(url))
        for link in literal_links:
            by_link[link].append(p)
    for link, entries in by_link.items():
        for batch in time_batches(entries, LINK_WINDOW):
            if len({(p['source'], p['actor']) for p in batch}) < MIN_ACTORS:
                continue
            results.append(_candidate('shared_link', link + '|' + batch[0]['id'], batch,
                'same external URL shared within 10 minutes', link,
                'Sharing a news article, petition, or event URL can be entirely organic.'))

    # Build overlapping candidate index using the four lexicographically smallest
    # bigrams as deterministic lightweight blocking keys.
    features = []
    key_index = defaultdict(set)
    for idx, post in enumerate(posts):
        grams = shingles(post['text'])
        features.append(grams)
        for key in sorted(grams)[:4]:
            key_index[key].add(idx)

    assigned = set()
    for i, anchor in enumerate(posts):
        a = features[i]
        if not a or i in assigned:
            continue
        keys = sorted(a)[:4]
        candidates = defaultdict(int)
        for key in keys:
            if len(key_index[key]) > 300:
                continue  # Extremely common templates are not informative blocking keys.
            for j in key_index[key]:
                if j > i and j not in assigned:
                    candidates[j] += 1
        group = [anchor]
        member_indices = [i]
        start = utc_seconds(anchor['created_at'])
        for j in sorted(candidates):
            if candidates[j] < 2:
                continue
            other = posts[j]
            elapsed = utc_seconds(other['created_at']) - start
            if elapsed > NEAR_WINDOW:
                continue
            b = features[j]
            if abs(len(a) - len(b)) > max(3, len(a) * (1 - NEAR_THRESHOLD)):
                continue
            if jaccard(a, b) >= NEAR_THRESHOLD:
                group.append(other)
                member_indices.append(j)
        if (len({(p['source'], p['actor']) for p in group}) >= MIN_ACTORS
                and len({normalized_text(p['text']) for p in group}) >= 2):
            results.append(_candidate('near_text', anchor['id'], group,
                'similar long-form wording within 10 minutes', anchor['text'],
                'Templates, quotations and press statements can produce similar wording.'))
            assigned.update(member_indices)

    return sorted(results, key=lambda c: (-c['distinct_actors'], c['first_seen'], c['id']))


def search_posts(database, query='', scope='live', limit=60, start=None, end=None, profile='all', language='all'):
    """Case-insensitive local search in stored posts; no external lookup.

    Bounded to OIO's 5000-post live cap, 100 visible results. Records retain
    source provenance but never enrich or query an actor's identity.
    """
    if not isinstance(query, str) or len(query) > 120 or any(ord(c) < 32 for c in query):
        raise ValueError('Search must be at most 120 characters without control characters')
    if scope not in ('live', 'all', 'synthetic'):
        raise ValueError('Source must be live, synthetic or all')
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError('Limit must be 1–100')
    if profile != 'all' and profile not in PROFILE_BY_ID:
        raise ValueError('Unknown topic profile')
    if not isinstance(language, str) or (language != 'all' and not LANG_RE.fullmatch(language.lower())):
        raise ValueError('Language must be all or a valid language tag')
    language = language.lower()
    for field, value in (('from', start), ('to', end)):
        if value is not None:
            if not isinstance(value, str) or len(value) > 40:
                raise ValueError(f'{field} must be an ISO timestamp')
            try:
                parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
                if parsed.utcoffset() is None:
                    raise ValueError()
            except ValueError:
                raise ValueError(f'{field} must be a timezone-aware ISO timestamp') from None
    if start and end and utc_seconds(start) > utc_seconds(end):
        raise ValueError('Start time must be before end time')

    with database() as c:
        rows = [dict(r) for r in c.execute('''
            SELECT p.id,p.source,p.actor,p.text,p.created_at,p.url,
                   v.provider,v.session_id,v.cid,v.captured_at,v.external_links,
                   v.declared_langs,v.profile_id
            FROM posts p LEFT JOIN live_post_provenance v ON p.id=v.post_id
            ORDER BY p.created_at DESC,p.id DESC''')]
    term = query.strip().casefold()
    lower = utc_seconds(start) if start else None
    upper = utc_seconds(end) if end else None
    found = []
    for p in rows:
        try:
            external_links = json.loads(p.get('external_links') or '[]')
            if not isinstance(external_links,list):
                external_links = []
        except (TypeError,json.JSONDecodeError):
            external_links = []
        p['external_links'] = external_links
        try:
            declared = json.loads(p.get('declared_langs') or '[]')
            if not isinstance(declared, list): declared = []
        except (TypeError, json.JSONDecodeError):
            declared = []
        p['declared_langs'] = declared
        live = p['session_id'] is not None
        if scope == 'live' and not live or scope == 'synthetic' and p['source'] != 'synthetic':
            continue
        if profile != 'all' and (not live or p['profile_id'] != profile):
            continue
        if language != 'all' and not any(lang == language or
            ('-' not in language and lang.startswith(language + '-')) for lang in declared):
            continue
        t = utc_seconds(p['created_at'])
        if lower is not None and t < lower or upper is not None and t > upper:
            continue
        if term and term not in '\n'.join(str(p[k]) for k in ('actor','text','url','external_links')).casefold():
            continue
        found.append(p)
    return {'posts': found[:limit], 'total_matches': len(found), 'limit': limit,
            'scope': scope, 'query': query.strip(), 'profile': profile, 'language': language,
            'truncated': len(found) > limit,
            'notice': 'Local captured records only. Matches are not bot detections or a representative sample.'}
