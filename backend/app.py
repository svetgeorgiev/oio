"""OIO v0.5: local, evidence-first research API with opt-in bounded Bluesky capture.

No authentication or public publication. Never bind this prototype to a public interface.
"""
import hashlib
import json
import os
import re
import sqlite3
import threading
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from laboratory import add_evidence, delete_evidence, import_evidence, lab_snapshot, lab_export
from live_stream import CaptureManager, init_schema, recent_posts, SOURCE
from research import detect_patterns, search_posts
from regions import public_profiles

ROOT = os.path.dirname(os.path.dirname(__file__))
DB = os.environ.get('OIO_DB', os.path.join(ROOT, 'data.sqlite3'))
FIXTURE = os.path.join(ROOT, 'fixtures', 'sample_posts.json')
VERSION = '0.5.2'
MAX_BODY = 16 * 1024
ALLOWED_STATUSES = ('investigating', 'needs_context', 'dismissed', 'closed')


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def connect():
    """Create/migrate SQLite structures without removing existing v0.1 posts or reviews."""
    c = sqlite3.connect(DB, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA busy_timeout=10000')
    c.execute('PRAGMA journal_mode=WAL')
    c.executescript('''
      CREATE TABLE IF NOT EXISTS posts (
        id TEXT PRIMARY KEY, source TEXT NOT NULL, actor TEXT NOT NULL,
        text TEXT NOT NULL, created_at TEXT NOT NULL, url TEXT NOT NULL,
        fingerprint TEXT NOT NULL
      );
      CREATE INDEX IF NOT EXISTS ix_posts_fingerprint_time ON posts(fingerprint,created_at);
      CREATE TABLE IF NOT EXISTS reviews (
        cluster_id TEXT PRIMARY KEY, status TEXT NOT NULL,
        notes TEXT NOT NULL, updated_at TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS investigations (
        id TEXT PRIMARY KEY,
        cluster_id TEXT NOT NULL UNIQUE,
        title TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('investigating','needs_context','dismissed','closed')),
        notes TEXT NOT NULL DEFAULT '',
        alternative_explanation TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
      );
      CREATE INDEX IF NOT EXISTS ix_investigations_updated ON investigations(updated_at);
      CREATE TABLE IF NOT EXISTS investigation_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        investigation_id TEXT NOT NULL REFERENCES investigations(id),
        event_type TEXT NOT NULL,
        summary TEXT NOT NULL,
        created_at TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS evidence_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        investigation_id TEXT NOT NULL REFERENCES investigations(id),
        kind TEXT NOT NULL CHECK(kind IN ('observation','context','counterevidence')),
        title TEXT NOT NULL,
        source_url TEXT NOT NULL,
        observed_at TEXT,
        notes TEXT NOT NULL,
        sha256 TEXT NOT NULL,
        captured_at TEXT NOT NULL,
        UNIQUE(investigation_id,sha256)
      );
      CREATE INDEX IF NOT EXISTS ix_evidence_case ON evidence_items(investigation_id);
    ''')
    init_schema(c)
    return c


@contextmanager
def database():
    """Transactional connection that also closes its sqlite handle."""
    connection = connect()
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def normalize(value):
    return re.sub(r'\s+', ' ', re.sub(r'https?://\S+', '', value.lower())).strip()


def ingest(posts):
    """Validate a complete batch before inserting, so a bad record adds nothing."""
    if not isinstance(posts, list) or len(posts) > 5000:
        raise ValueError('Expected an array of at most 5000 posts')
    prepared = []
    required = ('id', 'source', 'actor', 'text', 'created_at', 'url')
    for p in posts:
        if not isinstance(p, dict) or any(not isinstance(p.get(k), str) or not p[k].strip() for k in required):
            raise ValueError('Each post requires nonempty string fields: ' + ', '.join(required))
        if urlparse(p['url']).scheme not in ('http', 'https'):
            raise ValueError('Post URL must be http(s)')
        try:
            dt = datetime.fromisoformat(p['created_at'].replace('Z', '+00:00'))
        except ValueError as exc:
            raise ValueError('Invalid ISO timestamp') from exc
        if dt.tzinfo is None:
            raise ValueError('Timestamps must include timezone')
        fp = hashlib.sha256(normalize(p['text']).encode('utf-8')).hexdigest()[:16]
        prepared.append((p['id'], p['source'], p['actor'], p['text'],
                         dt.astimezone(timezone.utc).isoformat(), p['url'], fp))
    count = 0
    with database() as c:
        for record in prepared:
            count += c.execute('INSERT OR IGNORE INTO posts VALUES (?,?,?,?,?,?,?)', record).rowcount
    return count


def clusters(window_seconds=180, min_actors=3):
    with database() as c:
        posts = [dict(r) for r in c.execute('''SELECT p.*,v.external_links
            FROM posts p LEFT JOIN live_post_provenance v ON v.post_id=p.id
            ORDER BY p.fingerprint,p.created_at,p.id''')]
        investigations = {r['cluster_id']: dict(r) for r in c.execute('SELECT id,cluster_id,status FROM investigations')}
        old_reviews = {r['cluster_id']: dict(r) for r in c.execute('SELECT * FROM reviews')}
    groups = defaultdict(list)
    for p in posts:
        groups[p['fingerprint']].append(p)
    results = []
    for fp, entries in groups.items():
        batches, batch, start = [], [], None
        for p in entries:
            ts = datetime.fromisoformat(p['created_at']).timestamp()
            if batch and ts - start > window_seconds:
                batches.append(batch)
                batch, start = [], None
            if not batch:
                start = ts
            batch.append(p)
        if batch:
            batches.append(batch)
        for b in batches:
            actors = sorted(set((p['source'], p['actor']) for p in b))
            if len(actors) < min_actors:
                continue
            key = hashlib.sha256((fp + '|' + b[0]['id']).encode()).hexdigest()[:12]
            investigation = investigations.get(key)
            legacy = old_reviews.get(key, {'status': 'unreviewed', 'notes': ''})
            results.append({
                'id': key, 'signal_type': 'exact_text',
                'reason': 'Breaking news, collective campaigns and quotations may match exactly.',
                'pattern': 'exact normalized text in short time window',
                'distinct_actors': len(actors), 'post_count': len(b),
                'first_seen': b[0]['created_at'], 'last_seen': b[-1]['created_at'],
                'sample_text': b[0]['text'],
                'evidence': [{'id': p['id'], 'actor': p['actor'], 'source': p['source'],
                              'url': p['url'], 'created_at': p['created_at']} for p in b[:120]],
                'evidence_truncated': len(b) > 120,
                'review': {'status': investigation['status'] if investigation else legacy['status'],
                           'notes': legacy['notes'] if not investigation else ''},
                'investigation_id': investigation['id'] if investigation else None,
            })
    # Add distinct, explainable research leads without changing existing exact IDs.
    # A shared URL or near-match is not a bot verdict or proof of common control.
    for candidate in detect_patterns(posts):
        investigation = investigations.get(candidate['id'])
        legacy = old_reviews.get(candidate['id'], {'status': 'unreviewed', 'notes': ''})
        candidate['review'] = {
            'status': investigation['status'] if investigation else legacy['status'],
            'notes': legacy['notes'] if not investigation else '',
        }
        candidate['investigation_id'] = investigation['id'] if investigation else None
        results.append(candidate)
    return sorted(results, key=lambda x: (-x['distinct_actors'], x['first_seen'], x['id']))


def find_cluster(cluster_id):
    return next((cluster for cluster in clusters() if cluster['id'] == cluster_id), None)


def row_investigation(c, row, include_events=False):
    obj = dict(row)
    if include_events:
        obj['events'] = [dict(e) for e in c.execute(
            'SELECT id,event_type,summary,created_at FROM investigation_events '
            'WHERE investigation_id=? ORDER BY id DESC', (obj['id'],))]
    return obj


def investigations():
    with database() as c:
        return [row_investigation(c, r) for r in c.execute(
            'SELECT * FROM investigations ORDER BY updated_at DESC,id')]


def investigation_by_id(identifier):
    with database() as c:
        row = c.execute('SELECT * FROM investigations WHERE id=?', (identifier,)).fetchone()
        return row_investigation(c, row, True) if row else None


def validate_text(value, field, max_length, required=False):
    if not isinstance(value, str) or len(value) > max_length:
        raise ValueError(f'{field} must be text of at most {max_length} characters')
    value = value.strip()
    if required and not value:
        raise ValueError(f'{field} cannot be empty')
    return value


def create_investigation(payload):
    if not isinstance(payload, dict):
        raise ValueError('Expected a JSON object')
    cluster_id = validate_text(payload.get('cluster_id'), 'cluster_id', 32, required=True)
    cluster = find_cluster(cluster_id)
    if not cluster:
        raise LookupError('Candidate cluster not found')
    title = validate_text(payload.get('title', f'Investigation · {cluster_id}'), 'title', 120, required=True)
    identifier = 'inv-' + cluster_id
    now = utcnow()
    with database() as c:
        old = c.execute('SELECT id FROM investigations WHERE cluster_id=?', (cluster_id,)).fetchone()
        if old:
            return investigation_by_id(old['id']), False
        c.execute('INSERT INTO investigations '
                  '(id,cluster_id,title,status,notes,alternative_explanation,created_at,updated_at) '
                  'VALUES (?,?,?, ?,?,?,?,?)',
                  (identifier, cluster_id, title, 'investigating', '', '', now, now))
        c.execute('INSERT INTO investigation_events (investigation_id,event_type,summary,created_at) '
                  'VALUES (?,?,?,?)', (identifier, 'created', 'Investigation opened for human review', now))
    return investigation_by_id(identifier), True


def update_investigation(identifier, payload):
    if not isinstance(payload, dict):
        raise ValueError('Expected a JSON object')
    allowed = {'title', 'status', 'notes', 'alternative_explanation'}
    if not payload or set(payload) - allowed:
        raise ValueError('Allowed fields: title, status, notes, alternative_explanation')
    with database() as c:
        row = c.execute('SELECT * FROM investigations WHERE id=?', (identifier,)).fetchone()
        if not row:
            raise LookupError('Investigation not found')
        values = dict(row)
        for field in payload:
            values[field] = validate_text(payload[field], field, 120 if field == 'title' else 5000,
                                          required=(field == 'title'))
        if values['status'] not in ALLOWED_STATUSES:
            raise ValueError('Invalid investigation status')
        if values['status'] in ('dismissed', 'closed') and len(values['notes']) < 10:
            raise ValueError('Closing or dismissing requires reviewer notes (10+ characters)')
        changes = [field for field in allowed if values[field] != row[field]]
        if changes:
            now = utcnow()
            c.execute('UPDATE investigations SET title=?,status=?,notes=?,alternative_explanation=?,updated_at=? WHERE id=?',
                      (values['title'], values['status'], values['notes'], values['alternative_explanation'], now, identifier))
            summary = 'Updated: ' + ', '.join(sorted(changes))
            if 'status' in changes:
                summary += f" ({row['status']} → {values['status']})"
            c.execute('INSERT INTO investigation_events (investigation_id,event_type,summary,created_at) VALUES (?,?,?,?)',
                      (identifier, 'updated', summary, now))
    return investigation_by_id(identifier)


live_manager = CaptureManager(database)


class Handler(BaseHTTPRequestHandler):
    def local_host_allowed(self):
        """Reject DNS-rebinding Host headers while keeping ephemeral local test ports usable."""
        host = self.headers.get('Host', '')
        return bool(re.fullmatch(r'(?:127\.0\.0\.1|localhost|\[::1\])(?::[0-9]{1,5})?', host))

    def reply(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self.local_host_allowed():
            return self.reply(403, {'error': 'Local host only'})
        path = urlparse(self.path).path
        if path == '/api/health':
            return self.reply(200, {'status': 'ok', 'version': VERSION, 'mode': 'localhost research; optional user-triggered Jetstream capture'})
        if path == '/api/live/status':
            return self.reply(200, live_manager.status())
        if path == '/api/live/posts':
            return self.reply(200, {'posts': recent_posts(database),
                                    'notice': 'Sampled public posts, not verified identities or bot verdicts.'})
        if path == '/api/research/profiles':
            with database() as c:
                by_profile = {r['profile_id']: r['count'] for r in c.execute('''
                    SELECT profile_id, COUNT(*) AS count FROM live_post_provenance
                    GROUP BY profile_id''')}
            return self.reply(200, {'profiles': public_profiles(), 'saved_by_selected_profile': by_profile,
                'notice': 'Research profiles are analyst-selected topics, NOT verified geographic origins.'})
        if path == '/api/research/search':
            args = parse_qs(urlparse(self.path).query, keep_blank_values=True)
            try:
                limit = int(args.get('limit', ['60'])[0])
                result = search_posts(database, query=args.get('q', [''])[0],
                                      scope=args.get('scope', ['live'])[0], limit=limit,
                                      start=args.get('from', [None])[0], end=args.get('to', [None])[0],
                                      profile=args.get('profile', ['all'])[0],
                                      language=args.get('lang', ['all'])[0])
                return self.reply(200, result)
            except (ValueError, OverflowError) as exc:
                return self.reply(400, {'error': str(exc)})
        if path == '/api/research/signals':
            candidates = clusters()
            return self.reply(200, {
                'signals': candidates,
                'counts': {kind: sum(c['signal_type'] == kind for c in candidates)
                           for kind in ('exact_text', 'near_text', 'shared_link')},
                'notice': 'Candidate patterns require independent human verification, including benign explanations.',
            })
        if path == '/api/clusters':
            return self.reply(200, {'clusters': clusters(), 'notice': 'Signals are not proof of automation, shared control or wrongdoing.'})
        if path.startswith('/api/clusters/'):
            cluster = find_cluster(path.split('/')[-1])
            return self.reply(200, {'cluster': cluster}) if cluster else self.reply(404, {'error': 'Cluster not found'})
        if path == '/api/investigations':
            return self.reply(200, {'investigations': investigations()})
        parts = path.strip('/').split('/')
        if len(parts) == 4 and parts[:2] == ['api', 'investigations'] and parts[3] in ('lab',):
            try:
                return self.reply(200, {'lab': lab_snapshot(database, parts[2], find_cluster)})
            except LookupError as exc:
                return self.reply(404, {'error': str(exc)})
        if len(parts) == 5 and parts[:2] == ['api', 'investigations'] and parts[3:] == ['lab', 'export']:
            try:
                return self.reply(200, lab_export(database, parts[2], find_cluster))
            except LookupError as exc:
                return self.reply(404, {'error': str(exc)})
        if path.startswith('/api/investigations/'):
            item = investigation_by_id(path.split('/')[-1])
            return self.reply(200, {'investigation': item}) if item else self.reply(404, {'error': 'Investigation not found'})
        if path == '/api/stats':
            with database() as c:
                n = c.execute('SELECT COUNT(*) FROM posts').fetchone()[0]
                live = c.execute('SELECT COUNT(*) FROM live_post_provenance').fetchone()[0]
                cases = c.execute('SELECT COUNT(*) FROM investigations').fetchone()[0]
                active = c.execute("SELECT COUNT(*) FROM investigations WHERE status IN ('investigating','needs_context')").fetchone()[0]
            return self.reply(200, {'posts': n, 'candidate_clusters': len(clusters()), 'investigations': cases,
                                    'open_investigations': active, 'published_cases': 0,
                                    'live_posts': live, 'non_live_posts': n - live})
        return self.reply(404, {'error': 'Not found'})

    def read_json(self, limit=MAX_BODY):
        size = self.headers.get('Content-Length')
        if not size or not size.isdigit() or not 0 < int(size) <= limit:
            raise ValueError(f'Request body must be between 1 and {limit} bytes')
        try:
            return json.loads(self.rfile.read(int(size)))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError('Invalid JSON body') from exc

    def do_POST(self):
        # The API is localhost-only, unauthenticated, and unsuitable for public hosting.
        if not self.local_host_allowed() or self.client_address[0] not in ('127.0.0.1', '::1'):
            return self.reply(403, {'error': 'Local only'})
        origin = self.headers.get('Origin')
        if origin and origin not in ('http://127.0.0.1:5173', 'http://localhost:5173'):
            return self.reply(403, {'error': 'Origin not permitted'})
        path = urlparse(self.path).path
        try:
            parts = path.strip('/').split('/')
            if len(parts) == 5 and parts[:2] == ['api', 'investigations'] and parts[3:] == ['lab', 'evidence']:
                added = add_evidence(database, parts[2], self.read_json())
                return self.reply(201 if added else 200, {'inserted': added})
            if len(parts) == 5 and parts[:2] == ['api', 'investigations'] and parts[3:] == ['lab', 'import']:
                added = import_evidence(database, parts[2], self.read_json(limit=160 * 1024))
                return self.reply(200, {'inserted': added})
            if (len(parts) == 7 and parts[:2] == ['api', 'investigations']
                    and parts[3:5] == ['lab', 'evidence'] and parts[6] == 'delete'):
                if not parts[5].isdigit():
                    raise ValueError('Invalid evidence identifier')
                delete_evidence(database, parts[2], int(parts[5]), self.read_json())
                return self.reply(200, {'deleted': True})
            if path == '/api/live/start':
                return self.reply(202, live_manager.start(self.read_json()))
            if path == '/api/live/stop':
                return self.reply(200, live_manager.stop())
            if path == '/api/live/purge':
                return self.reply(200, live_manager.purge(self.read_json()))
            if path == '/api/load-fixture':
                if os.environ.get('OIO_ENABLE_DEMO') != '1':
                    return self.reply(403, {'error': 'Synthetic fixtures disabled. Set OIO_ENABLE_DEMO=1 only in a separate test workspace.'})
                with open(FIXTURE, encoding='utf-8') as f:
                    return self.reply(200, {'inserted': ingest(json.load(f))})
            if path == '/api/investigations':
                result, created = create_investigation(self.read_json())
                return self.reply(201 if created else 200, {'investigation': result, 'created': created})
            if path.startswith('/api/investigations/') and path.endswith('/review'):
                identifier = path.split('/')[-2]
                return self.reply(200, {'investigation': update_investigation(identifier, self.read_json())})
            return self.reply(404, {'error': 'Not found'})
        except RuntimeError as exc:
            return self.reply(409, {'error': str(exc)})
        except (ValueError, OSError) as exc:
            return self.reply(400, {'error': str(exc)})
        except LookupError as exc:
            return self.reply(404, {'error': str(exc)})
        except sqlite3.Error:
            return self.reply(500, {'error': 'Local storage error'})


if __name__ == '__main__':
    connect().close()
    live_manager.reconcile()
    retention_stop = threading.Event()
    housekeeping = threading.Thread(target=live_manager.maintenance, args=(retention_stop,), daemon=True)
    housekeeping.start()
    server = ThreadingHTTPServer(('127.0.0.1', 8765), Handler)
    print('OIO local API v0.4: http://127.0.0.1:8765', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nOIO server stopped cleanly.')
    finally:
        retention_stop.set()
        server.server_close()
