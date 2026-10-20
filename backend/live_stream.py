"""OIO v0.5.2: opt-in, bounded Bluesky observation with aggregate diagnostics.

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
from collections import Counter
from urllib.parse import urlencode, quote
from research import canonical_links
from regions import (capture_languages, observed_languages, declared_language_matches,
                     profile_id)

PROVIDERS = {
    'us-east': 'jetstream.us-east.bsky.network',
    'us-west': 'jetstream.us-west.bsky.network',
}
SOURCE = 'bluesky-jetstream'
MAX_SCANNED = 50000
MAX_TOTAL_POSTS = 5000
RETENTION_DAYS = 7
DIAGNOSTIC_LANGUAGE_LIMIT = 20
MAX_IN_MEMORY_LANGUAGE_TAGS = 80
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
    ''')
    cols = {r[1] for r in c.execute('PRAGMA table_info(live_post_provenance)')}
    if 'external_links' not in cols:
        c.execute("ALTER TABLE live_post_provenance ADD COLUMN external_links TEXT NOT NULL DEFAULT '[]'")
    session_cols = {r[1] for r in c.execute('PRAGMA table_info(live_capture_sessions)')}
    if 'profile_id' not in session_cols:
        c.execute("ALTER TABLE live_capture_sessions ADD COLUMN profile_id TEXT NOT NULL DEFAULT 'custom'")
    if 'language_filter' not in session_cols:
        c.execute("ALTER TABLE live_capture_sessions ADD COLUMN language_filter TEXT NOT NULL DEFAULT '[]'")
    if 'declared_langs' not in cols:
        c.execute("ALTER TABLE live_post_provenance ADD COLUMN declared_langs TEXT NOT NULL DEFAULT '[]'")
    if 'profile_id' not in cols:
        c.execute("ALTER TABLE live_post_provenance ADD COLUMN profile_id TEXT NOT NULL DEFAULT 'custom'")
    # Non-sensitive per-session diagnostic counters; additive migration from v0.5.1.
    session_cols = {r[1] for r in c.execute('PRAGMA table_info(live_capture_sessions)')}
    additions = {
        'mode': "TEXT NOT NULL DEFAULT 'capture'",
        'diagnostics_available': 'INTEGER NOT NULL DEFAULT 0',
        'post_creations': 'INTEGER NOT NULL DEFAULT 0',
        'eligible_text_posts': 'INTEGER NOT NULL DEFAULT 0',
        'keyword_matches': 'INTEGER NOT NULL DEFAULT 0',
        'language_rejections': 'INTEGER NOT NULL DEFAULT 0',
        'malformed_events': 'INTEGER NOT NULL DEFAULT 0',
        'invalid_post_records': 'INTEGER NOT NULL DEFAULT 0',
        'language_counts': "TEXT NOT NULL DEFAULT '{}'",
        'unknown_language_posts': 'INTEGER NOT NULL DEFAULT 0',
    }
    for name, definition in additions.items():
        if name not in session_cols:
            c.execute(f'ALTER TABLE live_capture_sessions ADD COLUMN {name} {definition}')
    c.execute('PRAGMA user_version=7')


def parse_keywords(value):
    """1–3 literal OR phrases; no regex, wildcards, account targeting or broad query syntax."""
    if not isinstance(value, str) or len(value) > 90 or any(ord(ch) < 32 for ch in value):
        raise ValueError('Provide 1–3 literal phrases, at most 90 characters total')
    phrases = [item.strip() for item in value.split('|')]
    if not 1 <= len(phrases) <= 3 or any(not 4 <= len(item) <= 40 for item in phrases):
        raise ValueError('Each of 1–3 literal phrases must be 4–40 characters')
    return phrases


def validate_config(payload):
    allowed = {'keyword', 'region', 'duration_seconds', 'max_posts', 'permission_confirmed', 'profile_id', 'languages', 'mode'}
    required = {'keyword', 'region', 'duration_seconds', 'max_posts', 'permission_confirmed'}
    if not isinstance(payload, dict) or not required.issubset(payload) or set(payload) - allowed:
        raise ValueError('Provide keyword, region, duration_seconds, max_posts and permission_confirmed')
    if payload['permission_confirmed'] is not True:
        raise ValueError('Confirm authorized public-data research and seven-day retention')
    phrase = payload['keyword']
    parse_keywords(phrase)
    if payload['region'] not in PROVIDERS:
        raise ValueError('Unknown official Jetstream region')
    duration = payload['duration_seconds']
    maximum = payload['max_posts']
    if isinstance(duration, bool) or not isinstance(duration, int) or not 15 <= duration <= 180:
        raise ValueError('Duration must be 15–180 seconds')
    if isinstance(maximum, bool) or not isinstance(maximum, int) or not 5 <= maximum <= 200:
        raise ValueError('Maximum saved posts must be 5–200')
    selected_profile = profile_id(payload.get('profile_id', 'custom'))
    languages = capture_languages(payload.get('languages', []))
    mode = payload.get('mode', 'capture')
    if mode not in ('capture', 'diagnostic'):
        raise ValueError('mode must be capture or diagnostic')
    return {'keyword': phrase.strip(), 'region': payload['region'],
            'duration_seconds': duration, 'max_posts': maximum,
            'profile_id': selected_profile, 'languages': languages, 'mode': mode}


def extract_record_links(record):
    """Observe public link facet/embed targets without fetching them.

    The text body is preserved unchanged; embed URLs become separate provenance.
    These references are source-supplied, not verified canonical locations.
    """
    found = set()
    for facet in record.get('facets', []) if isinstance(record.get('facets'), list) else []:
        if not isinstance(facet, dict):
            continue
        for feature in facet.get('features', []) if isinstance(facet.get('features'), list) else []:
            if isinstance(feature, dict) and feature.get('$type') == 'app.bsky.richtext.facet#link':
                url = feature.get('uri')
                if isinstance(url, str) and len(url) <= 2048 and canonical_links(url):
                    found.add(url)
    embed = record.get('embed')
    if isinstance(embed, dict):
        if embed.get('$type') == 'app.bsky.embed.recordWithMedia':
            embed = embed.get('media')
        if isinstance(embed, dict) and embed.get('$type') == 'app.bsky.embed.external':
            external = embed.get('external')
            url = external.get('uri') if isinstance(external, dict) else None
            if isinstance(url, str) and len(url) <= 2048 and canonical_links(url):
                found.add(url)
    return sorted(found)[:10]



def inspect_filter_path(event, phrases, language_filter):
    """Return ephemeral, non-identifying observations about a public post event.

    No post body, actor ID, or URL is retained by this inspection function.
    Used for both collection and diagnostics-only observations so their
    filter funnel is computed with identical logic.
    """
    if not isinstance(event, dict) or event.get('kind') != 'commit':
        return None
    commit = event.get('commit')
    if not isinstance(commit, dict) or commit.get('collection') != 'app.bsky.feed.post' or commit.get('operation') != 'create':
        return None
    record = commit.get('record')
    if not isinstance(record, dict) or record.get('$type') != 'app.bsky.feed.post':
        return {'valid_text': False, 'tags': [], 'keyword': False, 'language': False}
    text = record.get('text')
    if not isinstance(text, str) or not 1 <= len(text) <= 3000:
        return {'valid_text': False, 'tags': [], 'keyword': False, 'language': False}
    tags = observed_languages(record.get('langs'))
    keyword = any(phrase.casefold() in text.casefold() for phrase in phrases)
    return {'valid_text': True, 'tags': tags, 'keyword': keyword,
            'language': keyword and declared_language_matches(tags, language_filter)}


def compact_language_counts(counts):
    """Bound language histogram output and persist only aggregate counts."""
    ordered = sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
    keep = ordered[:DIAGNOSTIC_LANGUAGE_LIMIT]
    overflow = sum(value for _, value in ordered[DIAGNOSTIC_LANGUAGE_LIMIT:])
    result = dict(keep)
    if overflow:
        result['(other tags)'] = result.get('(other tags)', 0) + overflow
    return result


def normalize_live_event(event, keyword, languages=None):
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
    if not isinstance(text, str) or not 1 <= len(text) <= 3000 or not any(phrase.casefold() in text.casefold() for phrase in parse_keywords(keyword)):
        return None
    tags = observed_languages(record.get('langs'))
    if not declared_language_matches(tags, languages or []):
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
                           'record_created_at': raw_created, 'collection': 'app.bsky.feed.post',
                           'external_links': extract_record_links(record),
                           'declared_langs': tags}}


def insert_record(database, record, session_id, provider, selected_profile='custom'):
    p = record['post']; data = record['provenance']; now = utcnow()
    with database() as c:
        changed = c.execute('''INSERT OR IGNORE INTO posts
          (id,source,actor,text,created_at,url,fingerprint) VALUES (?,?,?,?,?,?,?)''',
          (p['id'], p['source'], p['actor'], p['text'], p['created_at'], p['url'], p['fingerprint'])).rowcount
        if changed:
            c.execute('''INSERT INTO live_post_provenance
              (post_id,did,rkey,cid,event_time_us,record_created_at,collection,provider,session_id,captured_at,external_links,declared_langs,profile_id)
              VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
              (p['id'], data['did'], data['rkey'], data['cid'], data['event_time_us'],
               data['record_created_at'], data['collection'], provider, session_id, now,
               json.dumps(data.get('external_links', []), ensure_ascii=False),
               json.dumps(data.get('declared_langs', []), ensure_ascii=False), selected_profile))
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
        rows = [dict(row) for row in c.execute('''SELECT p.id,p.actor,p.text,p.created_at,p.url,
                v.cid,v.event_time_us,v.record_created_at,v.provider,v.captured_at,v.session_id,v.external_links, v.declared_langs,v.profile_id
                FROM live_post_provenance v JOIN posts p ON p.id=v.post_id
                ORDER BY v.captured_at DESC,p.id DESC LIMIT ?''', (limit,))]
        for row in rows:
            row['declared_langs'] = json.loads(row['declared_langs'])
        return rows


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
                       'inserted': 0, 'removed': 0, 'stop_reason': '', 'error': '',
                       'post_creations': 0, 'eligible_text_posts': 0, 'keyword_matches': 0,
                       'language_rejections': 0, 'malformed_events': 0,
                       'invalid_post_records': 0, 'unknown_language_posts': 0,
                       'language_counts': {}, 'diagnostics_available': 1}
            with self.database() as c:
                c.execute('''INSERT INTO live_capture_sessions
                  (id,keyword,region,started_at,status,duration_seconds,max_posts)
                  VALUES (?,?,?,?,?,?,?)''', (session['id'], config['keyword'], config['region'], now,
                                              'connecting', config['duration_seconds'], config['max_posts']))
                c.execute('UPDATE live_capture_sessions SET profile_id=?,language_filter=?,mode=?,diagnostics_available=1 WHERE id=?',
                          (config['profile_id'], json.dumps(config['languages']), config['mode'], session['id']))
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
            if current:
                # Copy aggregate histogram while holding the lock: the worker
                # may receive more languages as an API response is serialized.
                current['language_counts'] = compact_language_counts(dict(self.session['language_counts']))
        if not current:
            with self.database() as c:
                row = c.execute('SELECT * FROM live_capture_sessions ORDER BY started_at DESC LIMIT 1').fetchone()
                current = dict(row) if row else None
                if current:
                    current['languages'] = json.loads(current.pop('language_filter', '[]'))
                    current['language_counts'] = json.loads(current.get('language_counts') or '{}')
        return {'session': current, 'active': bool(current and current['status'] in ('connecting', 'running', 'stopping')
                                                  and self.thread and self.thread.is_alive()),
                'stored_posts': live_count(self.database), 'storage_limit': MAX_TOTAL_POSTS,
                'retention_days': RETENTION_DAYS, 'max_scanned_events': MAX_SCANNED,
                'source': SOURCE, 'verified': False, 'publication_enabled': False,
                'diagnostic_language_limit': DIAGNOSTIC_LANGUAGE_LIMIT}

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
        phrases = parse_keywords(settings['keyword'])
        try:
            ws = self._connect(url)
            ws.settimeout(1.0)
            with self.lock:
                self.session['status'] = 'running'
            while time.monotonic() < deadline and not self.stop_event.is_set():
                with self.lock:
                    if self.session['scanned'] >= MAX_SCANNED:
                        result = 'event_limit'; break
                    if settings['mode'] == 'capture' and self.session['inserted'] >= settings['max_posts']:
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
                    with self.lock: self.session['malformed_events'] += 1
                    continue
                try:
                    event = json.loads(message)
                except (ValueError, TypeError):
                    with self.lock: self.session['malformed_events'] += 1
                    continue
                diagnostic = inspect_filter_path(event, phrases, settings.get('languages', []))
                if diagnostic is not None:
                    with self.lock:
                        self.session['post_creations'] += 1
                        if not diagnostic['valid_text']:
                            self.session['invalid_post_records'] += 1
                        else:
                            self.session['eligible_text_posts'] += 1
                            tags = diagnostic['tags']
                            if not tags:
                                self.session['unknown_language_posts'] += 1
                            else:
                                histogram = self.session['language_counts']
                                for tag in tags:
                                    if tag in histogram or len(histogram) < MAX_IN_MEMORY_LANGUAGE_TAGS:
                                        histogram[tag] = histogram.get(tag, 0) + 1
                                    else:
                                        histogram['(other tags)'] = histogram.get('(other tags)', 0) + 1
                            if diagnostic['keyword']:
                                self.session['keyword_matches'] += 1
                                if not diagnostic['language']:
                                    self.session['language_rejections'] += 1
                if diagnostic is None:
                    # In capture mode, deletions/updates of previously saved posts
                    # remain effective regardless of current keyword/language filters.
                    if settings['mode'] == 'capture':
                        parsed = normalize_live_event(event, settings['keyword'], settings.get('languages', []))
                        if parsed and parsed['action'] == 'remove':
                            if remove_record(self.database, parsed['id']):
                                with self.lock: self.session['removed'] += 1
                    continue
                if not diagnostic['valid_text'] or not diagnostic['keyword'] or not diagnostic['language']:
                    continue
                # Check source identifier, event timestamp and record fields before
                # treating a textual match as a usable observation.
                parsed = normalize_live_event(event, settings['keyword'], settings.get('languages', []))
                if not parsed or parsed['action'] != 'create':
                    with self.lock: self.session['invalid_post_records'] += 1
                    continue
                with self.lock: self.session['matched'] += 1
                if settings['mode'] == 'diagnostic':
                    continue  # Discovery-only: never save post bodies, IDs or URLs.
                if live_count(self.database) >= MAX_TOTAL_POSTS:
                    result = 'storage_limit'; break
                if insert_record(self.database, parsed, session_id, host, settings.get('profile_id', 'custom')):
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
                final['language_counts'] = compact_language_counts(final['language_counts'])
                self.session['language_counts'] = final['language_counts']
            with self.database() as c:
                c.execute('''UPDATE live_capture_sessions SET ended_at=?,status=?,scanned=?,matched=?,
                  inserted=?,removed=?,stop_reason=?,error=?,post_creations=?,eligible_text_posts=?,
                  keyword_matches=?,language_rejections=?,malformed_events=?,invalid_post_records=?,
                  unknown_language_posts=?,language_counts=? WHERE id=?''',
                  (final['ended_at'], final['status'], final['scanned'], final['matched'],
                   final['inserted'], final['removed'], final['stop_reason'], final['error'],
                   final['post_creations'], final['eligible_text_posts'], final['keyword_matches'],
                   final['language_rejections'], final['malformed_events'], final['invalid_post_records'],
                   final['unknown_language_posts'], json.dumps(final['language_counts']), session_id))

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
