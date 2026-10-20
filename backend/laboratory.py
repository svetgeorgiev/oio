"""OIO evidence laboratory: local-only metadata, source provenance, and reproducible exports.

No network access, scraping, private account discovery or automatic publication.
"""
import csv
import hashlib
import io
import ipaddress
import json
import re
from collections import Counter
from datetime import datetime, timezone
from urllib.parse import urlparse

KINDS = ('observation', 'context', 'counterevidence')
MAX_ITEMS_PER_CASE = 500
MAX_IMPORT_RECORDS = 100
MAX_IMPORT_CHARS = 128 * 1024
MAX_SOURCE_LENGTH = 2048


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def sha256(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def bounded_string(value, field, limit, required=False):
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError(f'{field} must be text of at most {limit} characters')
    value = value.strip()
    if required and not value:
        raise ValueError(f'{field} cannot be empty')
    return value


def valid_public_url(value):
    value = bounded_string(value, 'source_url', MAX_SOURCE_LENGTH, required=True)
    if any(ch.isspace() or ord(ch) < 32 for ch in value):
        raise ValueError('source_url must not contain whitespace or control characters')
    try:
        parsed = urlparse(value)
        port = parsed.port  # force validation of malformed ports
    except ValueError as exc:
        raise ValueError('Invalid source URL') from exc
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('source_url requires a public http(s) URL without credentials')
    hostname = parsed.hostname.rstrip('.').lower()
    if hostname == 'localhost' or hostname.endswith(('.localhost', '.local', '.internal')) or '.' not in hostname:
        raise ValueError('Local/private source URLs are not accepted')
    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        if not ip.is_global:
            raise ValueError('Local/private source URLs are not accepted')
    if port is not None and port not in (80, 443):
        raise ValueError('Only standard HTTP(S) ports are supported')
    return value


def utc_timestamp(value):
    if value is None or value == '':
        return None
    raw = bounded_string(value, 'observed_at', 45, required=True)
    try:
        date = datetime.fromisoformat(raw.replace('Z', '+00:00'))
    except ValueError as exc:
        raise ValueError('observed_at must be a valid ISO timestamp') from exc
    if date.tzinfo is None:
        raise ValueError('observed_at must include a timezone')
    return date.astimezone(timezone.utc).isoformat()


def validate_evidence(value):
    if not isinstance(value, dict):
        raise ValueError('Evidence entry must be an object')
    allowed = {'kind', 'title', 'source_url', 'observed_at', 'notes'}
    if set(value) - allowed:
        raise ValueError('Unexpected evidence fields: ' + ', '.join(sorted(set(value) - allowed)))
    kind = bounded_string(value.get('kind', 'observation'), 'kind', 20, required=True)
    if kind not in KINDS:
        raise ValueError('kind must be observation, context, or counterevidence')
    data = {
        'kind': kind,
        'title': bounded_string(value.get('title'), 'title', 160, required=True),
        'source_url': valid_public_url(value.get('source_url')),
        'observed_at': utc_timestamp(value.get('observed_at')),
        'notes': bounded_string(value.get('notes', ''), 'notes', 4000),
    }
    return {**data, 'sha256': sha256(data)}


def require_permission(payload):
    if not isinstance(payload, dict) or payload.get('permission_confirmed') is not True:
        raise ValueError('Confirm permission to use and retain the source references')


def case_exists(connection, identifier):
    return connection.execute('SELECT id FROM investigations WHERE id=?', (identifier,)).fetchone() is not None


def insert_evidence_batch(database, identifier, prepared):
    """Atomic, deduplicated import; unique item hashes per investigation."""
    now = utcnow()
    with database() as c:
        if not case_exists(c, identifier):
            raise LookupError('Investigation not found')
        existing = c.execute('SELECT COUNT(*) FROM evidence_items WHERE investigation_id=?', (identifier,)).fetchone()[0]
        existing_hashes = {r[0] for r in c.execute('SELECT sha256 FROM evidence_items WHERE investigation_id=?', (identifier,))}
        incoming = {item['sha256'] for item in prepared} - existing_hashes
        if existing + len(incoming) > MAX_ITEMS_PER_CASE:
            raise ValueError(f'Investigation capacity is {MAX_ITEMS_PER_CASE} evidence entries')
        inserted = 0
        for item in prepared:
            inserted += c.execute('''INSERT OR IGNORE INTO evidence_items
                (investigation_id,kind,title,source_url,observed_at,notes,sha256,captured_at)
                VALUES (?,?,?,?,?,?,?,?)''',
                (identifier, item['kind'], item['title'], item['source_url'], item['observed_at'],
                 item['notes'], item['sha256'], now)).rowcount
        if inserted:
            c.execute('''INSERT INTO investigation_events (investigation_id,event_type,summary,created_at)
                VALUES (?,?,?,?)''', (identifier, 'evidence_added', f'Added {inserted} local evidence reference(s)', now))
    return inserted


def add_evidence(database, identifier, payload):
    require_permission(payload)
    if 'evidence' not in payload:
        raise ValueError('Missing evidence object')
    item = validate_evidence(payload['evidence'])
    return insert_evidence_batch(database, identifier, [item])


def parse_import(payload):
    require_permission(payload)
    fmt = payload.get('format')
    content = payload.get('content')
    if fmt not in ('csv', 'json') or not isinstance(content, str) or not 0 < len(content) <= MAX_IMPORT_CHARS:
        raise ValueError('Provide a CSV or JSON text file of at most 128 KiB')
    if fmt == 'json':
        try:
            rows = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError('Invalid JSON evidence import') from exc
    else:
        try:
            reader = csv.DictReader(io.StringIO(content, newline=''), strict=True)
            if not reader.fieldnames or len(reader.fieldnames) > 20:
                raise ValueError('CSV must contain a header row')
            fields = [name.lstrip('\ufeff').strip() if name else '' for name in reader.fieldnames]
            if len(set(fields)) != len(fields):
                raise ValueError('CSV has duplicate headers')
            reader.fieldnames = fields
            rows = list(reader)
        except csv.Error as exc:
            raise ValueError('Invalid CSV evidence import') from exc
        if any(None in row for row in rows):
            raise ValueError('CSV rows have more columns than the header')
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_IMPORT_RECORDS:
        raise ValueError(f'Import requires 1 to {MAX_IMPORT_RECORDS} evidence rows')
    return [validate_evidence(row) for row in rows]


def import_evidence(database, identifier, payload):
    return insert_evidence_batch(database, identifier, parse_import(payload))


def delete_evidence(database, identifier, item_id, payload):
    if not isinstance(payload, dict) or set(payload) != {'reason'}:
        raise ValueError('A deletion reason is required')
    reason = bounded_string(payload['reason'], 'reason', 300, required=True)
    if len(reason) < 10:
        raise ValueError('Deletion reason must be at least 10 characters')
    now = utcnow()
    with database() as c:
        if not case_exists(c, identifier):
            raise LookupError('Investigation not found')
        row = c.execute('SELECT sha256 FROM evidence_items WHERE id=? AND investigation_id=?',
                        (item_id, identifier)).fetchone()
        if not row:
            raise LookupError('Evidence reference not found')
        c.execute('DELETE FROM evidence_items WHERE id=? AND investigation_id=?', (item_id, identifier))
        c.execute('INSERT INTO investigation_events (investigation_id,event_type,summary,created_at) VALUES (?,?,?,?)',
                  (identifier, 'evidence_deleted', f'Removed reference #{item_id} ({row["sha256"][:12]}…): {reason}', now))
    return True


def hostname(url):
    try:
        return urlparse(url).hostname or ''
    except ValueError:
        return ''


def referenced_domains(text):
    # Extract only domains publicly written in post text. Never access those URLs.
    result = []
    for url in re.findall(r'https?://[^\s<>"\']+', text, re.IGNORECASE):
        host = hostname(url.rstrip('.,;:!?)'))
        if host:
            result.append(host.lower())
    return sorted(set(result))


def lab_snapshot(database, identifier, find_cluster):
    with database() as c:
        row = c.execute('SELECT * FROM investigations WHERE id=?', (identifier,)).fetchone()
        if not row:
            raise LookupError('Investigation not found')
        investigation = dict(row)
        items = [dict(item) for item in c.execute('''SELECT id,kind,title,source_url,observed_at,notes,sha256,captured_at
            FROM evidence_items WHERE investigation_id=? ORDER BY captured_at DESC,id DESC''', (identifier,))]
        events = [dict(e) for e in c.execute('''SELECT id,event_type,summary,created_at FROM investigation_events
            WHERE investigation_id=? ORDER BY id DESC''', (identifier,))]
        cluster = find_cluster(investigation['cluster_id'])
        post_ids = [p['id'] for p in cluster['evidence']] if cluster else []
        posts = []
        if post_ids:
            placeholders = ','.join('?' for _ in post_ids)
            posts = [dict(p) for p in c.execute('SELECT id,source,actor,text,created_at,url FROM posts WHERE id IN (' + placeholders + ') ORDER BY created_at,id', post_ids)]
    for p in posts:
        p['sha256'] = sha256(p)
    timeline = ([{'id': p['id'], 'kind': 'detected_post', 'label': p['actor'], 'at': p['created_at']}
                 for p in posts] +
                [{'id': f'evidence-{e["id"]}', 'kind': 'analyst_reference', 'label': e['title'], 'at': e['observed_at']}
                 for e in items if e['observed_at']])
    timeline.sort(key=lambda e: (e['at'], str(e['id'])))
    sources = Counter(hostname(item['source_url']).lower() for item in items)
    original_sources = Counter(hostname(p['url']).lower() for p in posts)
    referred = Counter(domain for p in posts for domain in referenced_domains(p['text']))
    domains = {
        'manual_reference_hosts': [{'domain': k, 'count': v} for k, v in sorted(sources.items(), key=lambda p: (-p[1], p[0])) if k],
        'post_record_hosts': [{'domain': k, 'count': v} for k, v in sorted(original_sources.items(), key=lambda p: (-p[1], p[0])) if k],
        'post_text_link_hosts': [{'domain': k, 'count': v} for k, v in sorted(referred.items(), key=lambda p: (-p[1], p[0])) if k],
    }
    return {'investigation': investigation, 'cluster': cluster, 'evidence_items': items,
            'source_posts': posts, 'timeline': timeline, 'domains': domains, 'audit_events': events,
            'limitations': ['Analyst URLs are manually provided; OIO did not fetch or verify page contents.',
                            'User-supplied observation times are not independently verified.',
                            'Matching content does not establish fake accounts, shared control, intent, or wrongdoing.',
                            'Source-record domains, manually cited domains and domains shared in post text are different measurements.']}


def lab_export(database, identifier, find_cluster):
    snapshot = lab_snapshot(database, identifier, find_cluster)
    return {'format': 'oio-evidence-snapshot', 'schema_version': 1, 'application_version': '0.3.0',
            'generated_at': utcnow(), 'scope': 'local analyst research',
            'analysis_parameters': {'method': 'normalized exact-text fingerprint', 'window_seconds': 180,
                                    'minimum_distinct_source_actor_pairs': 3,
                                    'normalization': 'lowercase; strip http(s) URLs; collapse whitespace'},
            **snapshot}
