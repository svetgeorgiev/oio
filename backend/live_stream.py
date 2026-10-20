"""OIO v0.4: opt-in, bounded public Bluesky Jetstream observation.

Only official Bluesky-hosted Jetstream legacy JSON /subscribe endpoint is contacted.
No account searches, private feeds, enrichment, attribution, or publication.
The live feed cannot cryptographically attest source record authenticity.
"""
import hashlib
import json
import re
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, quote

PROVIDERS = {
    'us-east': 'jetstream.us-east.bsky.network',
    'us-west': 'jetstream.us-west.bsky.network',
}
SOURCE = 'bluesky-jetstream'
MAX_SCANNED = 50000
MAX_TOTAL_POSTS = 5000
RETENTION_DAYS = 7
DID_RE = re.compile(r'^did:(?:plc:[a-z2-7]{16,40}|web:[A-Za-z0-9.%_-]{4,190})$')
RKEY_RE = re.compile(r'^[A-Za-z0-9._~-]{1,80}$')


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def init_schema(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS live_capture_sessions (
        id TEXT PRIMARY KEY, keyword TEXT NOT NULL, region TEXT NOT NULL,
        started_at TEXT NOT NULL, ended_at TEXT, status TEXT NOT NULL,
        duration_seconds INTEGER NOT NULL, max_posts INTEGER NOT NULL,
        scanned INTEGER NOT NULL DEFAULT 0, matched INTEGER NOT NULL DEFAULT 0,
        inserted INTEGER NOT NULL DEFAULT 0, removed INTEGER NOT NULL DEFAULT 0,
        stop_reason TEXT NOT NULL DEFAULT '', error TEXT NOT NULL DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS live_post_provenance (
        post_id TEXT PRIMARY KEY, did TEXT NOT NULL, rkey TEXT NOT NULL,
        cid TEXT NOT NULL, event_time_us INTEGER NOT NULL,
        record_created_at TEXT, collection TEXT NOT NULL,
        provider TEXT NOT NULL, session_id TEXT NOT NULL,
        captured_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS ix_live_captured_at ON live_post_provenance(captured_at);
    PRAGMA user_version=4;
    ''')


def validate_config(payload):
    if not isinstance(payload, dict) or set(payload) != {'keyword', 'region', 'duration_seconds', 'max_posts', 'permission_confirmed'}:
        raise ValueError('Provide keyword, region, duration_seconds, max_posts and permission_confirmed')
    if payload['permission_confirmed'] is not True:
        raise ValueError('Confirm authorized public-data research and seven-day retention')
    phrase = payload['keyword']
    if not isinstance(phrase, str) or len(phrase) > 64 or len(phrase.strip()) < 4 or not phrase.strip():
        raise ValueError('Keyword must be 4–64 characters; a literal phrase, not a regex')
    if any(ord(ch) < 32 for ch in phrase):
        raise ValueError('Keyword must not contain control characters')
    if payload['region'] not in PROVIDERS:
        raise ValueError('Unknown official Jetstream region')
    duration = payload['duration_seconds']
    maximum = payload['max_posts']
    if isinstance(duration, bool) or not isinstance(duration, int) or not 15 <= duration <= 180:
        raise ValueError('Duration must be 15–180 seconds')
    if isinstance(maximum, bool) or not isinstance(maximum, int) or not 5 <= maximum <= 200:
        raise ValueError('Maximum saved posts must be 5–200')
    return {'keyword': phrase.strip(), 'region': payload['region'],
            'duration_seconds': duration, 'max_posts': maximum}


def normalize_live_event(event, keyword):
    """Return a creation record, deletion marker or None; never trust input shapes."""
    if not isinstance(event, dict) or event.get('kind') != 'commit':
        return None
    commit = event.get('commit')
    if not isinstance(commit, dict) or commit.get('collection') != 'app.bsky.feed.post':
        return None
    did, rkey = event.get('did'), commit.get('rkey')
    if not isinstance(did, str) or not DID_RE.fullmatch(did) or not isinstance(rkey, str) or not RKEY_RE.fullmatch(rkey):
        return None
    identifier = f'bsky:{did}:{rkey}'
    if commit.get('operation') in ('delete', 'update'):
        return {'action': 'remove', 'id': identifier}
    if commit.get('operation') != 'create':
        return None
    record = commit.get('record')
    if not isinstance(record, dict) or record.get('$type') != 'app.bsky.feed.post':
        return None
    text = record.get('text')
    if not isinstance(text, str) or not 1 <= len(text) <= 3000 or keyword.casefold() not in text.casefold():
        return None
    stamp = event.get('time_us')
    if isinstance(stamp, bool) or not isinstance(stamp, int):
        return None
    try:
        observed = datetime.fromtimestamp(stamp / 1000000, tz=timezone.utc)
    except (ValueError, OverflowError, OSError):
        return None
    if abs((datetime.now(timezone.utc) - observed).total_seconds()) > 48 * 3600:
        # This is a live-only collector, not a replay or historical dataset importer.
        return None
    cid = commit.get('cid', '')
    if not isinstance(cid, str) or len(cid) > 200:
        return None
    raw_created = record.get('createdAt')
    if raw_created is not None and (not isinstance(raw_created, str) or len(raw_created) > 80):
        raw_created = None
    url = f'https://bsky.app/profile/{quote(did, safe=":")}/post/{quote(rkey, safe="")}'
    post = {'id': identifier, 'source': SOURCE, 'actor': did, 'text': text,
            'created_at': observed.isoformat(), 'url': url,
            'fingerprint': hashlib.sha256(re.sub(r'\s+', ' ', re.sub(r'https?://\S+', '', text.lower())).strip().encode('utf-8')).hexdigest()[:16]}
    return {'action': 'create', 'post': post,
            'provenance': {'did': did, 'rkey': rkey, 'cid': cid, 'event_time_us': stamp,
                           'record_created_at': raw_created, 'collection': 'app.bsky.feed.post'}}


def insert_record(database, record, session_id, provider):
    p = record['post']; data = record['provenance']; now = utcnow()
    with database() as c:
        changed = c.execute('''INSERT OR IGNORE INTO posts
          (id,source,actor,text,created_at,url,fingerprint) VALUES (?,?,?,?,?,?,?)''',
          (p['id'], p['source'], p['actor'], p['text'], p['created_at'], p['url'], p['fingerprint'])).rowcount
        if changed:
            c.execute('''INSERT INTO live_post_provenance
              (post_id,did,rkey,cid,event_time_us,record_created_at,collection,provider,session_id,captured_at)
              VALUES (?,?,?,?,?,?,?,?,?,?)''',
              (p['id'], data['did'], data['rkey'], data['cid'], data['event_time_us'],
               data['record_created_at'], data['collection'], provider, session_id, now))
    return changed


def remove_record(database, identifier):
    with database() as c:
        marked = c.execute('DELETE FROM live_post_provenance WHERE post_id=?', (identifier,)).rowcount
        if marked:
            c.execute('DELETE FROM posts WHERE id=? AND source=?', (identifier, SOURCE))
    return marked


def live_count(database):
    with database() as c:
        return c.execute('SELECT count(*) FROM live_post_provenance').fetchone()[0]


def prune_expired(database):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)).isoformat()
    with database() as c:
        ids = [r[0] for r in c.execute('SELECT post_id FROM live_post_provenance WHERE captured_at < ?', (cutoff,))]
        if ids:
            c.executemany('DELETE FROM live_post_provenance WHERE post_id=?', ((x,) for x in ids))
            c.executemany('DELETE FROM posts WHERE id=? AND source=?', ((x, SOURCE) for x in ids))
        c.execute('DELETE FROM live_capture_sessions WHERE ended_at IS NOT NULL AND ended_at < ?', (cutoff,))
    return len(ids)


def clear_captured(database):
    with database() as c:
        ids = [r[0] for r in c.execute('SELECT post_id FROM live_post_provenance')]
        c.execute('DELETE FROM live_post_provenance')
        c.executemany('DELETE FROM posts WHERE id=? AND source=?', ((x, SOURCE) for x in ids))
    return len(ids)


def recent_posts(database, limit=60):
    limit = min(max(int(limit), 1), 60)
    with database() as c:
        return [dict(row) for row in c.execute('''SELECT p.id,p.actor,p.text,p.created_at,p.url,
                v.cid,v.event_time_us,v.record_created_at,v.provider,v.captured_at,v.session_id
                FROM live_post_provenance v JOIN posts p ON p.id=v.post_id
                ORDER BY v.captured_at DESC,p.id DESC LIMIT ?''', (limit,))]


class CaptureManager:
    """One bounded, explicitly started collector per localhost backend process."""
    def __init__(self, database, websocket_factory=None):
        self.database = database
        self.websocket_factory = websocket_factory
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.thread = None
        self.session = None
        self.last_start = 0.0

    def _connect(self, url):
        if self.websocket_factory:
            return self.websocket_factory(url)
        try:
            from websocket import create_connection
        except ImportError as exc:
            raise RuntimeError('Install backend dependency: python -m pip install -r requirements.txt') from exc
        return create_connection(url, timeout=8, enable_multithread=True)

    def start(self, payload):
        config = validate_config(payload)
        with self.lock:
            if self.thread and self.thread.is_alive():
                raise RuntimeError('A live observation is already running')
            if time.monotonic() - self.last_start < 3:
                raise RuntimeError('Wait three seconds before starting another session')
            prune_expired(self.database)
            if live_count(self.database) >= MAX_TOTAL_POSTS:
                raise RuntimeError('Local live-post capacity reached; clear captured posts first')
            now = utcnow()
            session = {**config, 'id': uuid.uuid4().hex[:16], 'status': 'connecting',
                       'started_at': now, 'ended_at': None, 'scanned': 0, 'matched': 0,
                       'inserted': 0, 'removed': 0, 'stop_reason': '', 'error': ''}
            with self.database() as c:
                c.execute('''INSERT INTO live_capture_sessions
                  (id,keyword,region,started_at,status,duration_seconds,max_posts)
                  VALUES (?,?,?,?,?,?,?)''', (session['id'], config['keyword'], config['region'], now,
                                              'connecting', config['duration_seconds'], config['max_posts']))
            self.session = session
            self.stop_event.clear()
            self.last_start = time.monotonic()
            self.thread = threading.Thread(target=self._worker, args=(session['id'],), daemon=True, name='oio-jetstream')
            self.thread.start()
            return self.status()

    def stop(self):
        with self.lock:
            if not self.thread or not self.thread.is_alive():
                raise RuntimeError('No active observation to stop')
            self.stop_event.set()
            self.session['status'] = 'stopping'
        return self.status()

    def status(self):
        # Apply age-based deletion when the UI checks the live collector, even if idle.
        prune_expired(self.database)
        with self.lock:
            current = dict(self.session) if self.session else None
        if not current:
            with self.database() as c:
                row = c.execute('SELECT * FROM live_capture_sessions ORDER BY started_at DESC LIMIT 1').fetchone()
                current = dict(row) if row else None
        return {'session': current, 'active': bool(current and current['status'] in ('connecting', 'running', 'stopping')
                                                  and self.thread and self.thread.is_alive()),
                'stored_posts': live_count(self.database), 'storage_limit': MAX_TOTAL_POSTS,
                'retention_days': RETENTION_DAYS, 'max_scanned_events': MAX_SCANNED,
                'source': SOURCE, 'verified': False, 'publication_enabled': False}

    def _worker(self, session_id):
        ws = None
        result = 'completed'
        failure = ''
        with self.lock:
            settings = dict(self.session)
        host = PROVIDERS[settings['region']]
        url = 'wss://' + host + '/subscribe?' + urlencode({'wantedCollections': 'app.bsky.feed.post',
                                                           'maxMessageSizeBytes': 131072})
        deadline = time.monotonic() + settings['duration_seconds']
        try:
            ws = self._connect(url)
            ws.settimeout(1.0)
            with self.lock:
                self.session['status'] = 'running'
            while time.monotonic() < deadline and not self.stop_event.is_set():
                with self.lock:
                    if self.session['scanned'] >= MAX_SCANNED:
                        result = 'event_limit'; break
                    if self.session['inserted'] >= settings['max_posts']:
                        result = 'post_limit'; break
                try:
                    message = ws.recv()
                except Exception as exc:
                    # Timeout may be emitted by either websocket-client or test doubles.
                    if isinstance(exc, TimeoutError) or type(exc).__name__ in ('WebSocketTimeoutException', 'TimeoutError'):
                        continue
                    raise
                if message is None or message == '':
                    result = 'stream_closed'; break
                with self.lock:
                    self.session['scanned'] += 1
                if not isinstance(message, str) or len(message) > 131072:
                    continue
                try:
                    event = json.loads(message)
                except (ValueError, TypeError):
                    continue
                parsed = normalize_live_event(event, settings['keyword'])
                if not parsed:
                    continue
                if parsed['action'] == 'remove':
                    if remove_record(self.database, parsed['id']):
                        with self.lock: self.session['removed'] += 1
                    continue
                with self.lock: self.session['matched'] += 1
                if live_count(self.database) >= MAX_TOTAL_POSTS:
                    result = 'storage_limit'; break
                if insert_record(self.database, parsed, session_id, host):
                    with self.lock: self.session['inserted'] += 1
            if self.stop_event.is_set():
                result = 'user_stopped'
            elif time.monotonic() >= deadline and result == 'completed':
                result = 'time_limit'
        except Exception as exc:
            result = 'error'
            failure = f'{type(exc).__name__}: {str(exc)[:180]}'
        finally:
            if ws:
                try: ws.close()
                except Exception: pass
            with self.lock:
                self.session['status'] = 'error' if result == 'error' else 'finished'
                self.session['ended_at'] = utcnow()
                self.session['stop_reason'] = result
                self.session['error'] = failure
                final = dict(self.session)
            with self.database() as c:
                c.execute('''UPDATE live_capture_sessions SET ended_at=?,status=?,scanned=?,matched=?,
                  inserted=?,removed=?,stop_reason=?,error=? WHERE id=?''',
                  (final['ended_at'], final['status'], final['scanned'], final['matched'],
                   final['inserted'], final['removed'], final['stop_reason'], final['error'], session_id))

    def purge(self, payload):
        if not isinstance(payload, dict) or payload.get('confirmation') != 'DELETE LIVE POSTS':
            raise ValueError('Confirm by typing DELETE LIVE POSTS')
        with self.lock:
            if self.thread and self.thread.is_alive():
                raise RuntimeError('Stop the live session before clearing captured posts')
            deleted = clear_captured(self.database)
            with self.database() as c:
                c.execute('DELETE FROM live_capture_sessions')
            self.session = None
            self.last_start = 0
            return {'deleted': deleted}


    def maintenance(self, stop=None):
        """Offline housekeeping only (no web connection); prune hourly while API runs."""
        while not (stop and stop.is_set()):
            if stop:
                if stop.wait(3600):
                    return
            else:
                time.sleep(3600)
            try:
                prune_expired(self.database)
            except sqlite3.Error:
                # A busy or inaccessible database is retried next cycle.
                pass

    def reconcile(self):
        """Mark sessions interrupted on backend crash / restart; never auto-resume."""
        with self.database() as c:
            c.execute("UPDATE live_capture_sessions SET status='interrupted',ended_at=?,stop_reason='backend_restarted' "
                      "WHERE status IN ('connecting','running','stopping')", (utcnow(),))
        prune_expired(self.database)
