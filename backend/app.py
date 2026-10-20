"""OIO v0.1 prototype: stdlib-only API, fixture ingestion and evidence-first coordination detection."""
import json, sqlite3, os, re, hashlib
from collections import defaultdict
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(__file__))
DB = os.environ.get('OIO_DB', os.path.join(ROOT, 'data.sqlite3'))
FIXTURE = os.path.join(ROOT, 'fixtures', 'sample_posts.json')

def connect():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA journal_mode=WAL')
    c.executescript('''CREATE TABLE IF NOT EXISTS posts (id TEXT PRIMARY KEY, source TEXT NOT NULL, actor TEXT NOT NULL, text TEXT NOT NULL, created_at TEXT NOT NULL, url TEXT NOT NULL, fingerprint TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS ix_posts_fingerprint_time ON posts(fingerprint, created_at);
    CREATE TABLE IF NOT EXISTS reviews (cluster_id TEXT PRIMARY KEY, status TEXT NOT NULL, notes TEXT NOT NULL, updated_at TEXT NOT NULL);''')
    return c

def normalize(text):
    return re.sub(r'\s+', ' ', re.sub(r'https?://\S+', '', text.lower())).strip()

def ingest(posts):
    count=0
    with connect() as c:
        for p in posts:
            required=('id','source','actor','text','created_at','url')
            if any(not isinstance(p.get(k),str) or not p[k] for k in required):
                raise ValueError('Each post requires nonempty string fields: '+', '.join(required))
            if urlparse(p['url']).scheme not in ('http','https'):
                raise ValueError('Post URL must be http(s)')
            dt=datetime.fromisoformat(p['created_at'].replace('Z','+00:00'))
            if dt.tzinfo is None: raise ValueError('Timestamps must include timezone')
            fp=hashlib.sha256(normalize(p['text']).encode()).hexdigest()[:16]
            cur=c.execute('INSERT OR IGNORE INTO posts VALUES (?,?,?,?,?,?,?)',(p['id'],p['source'],p['actor'],p['text'],dt.astimezone(timezone.utc).isoformat(),p['url'],fp))
            count+=cur.rowcount
    return count

def clusters(window_seconds=180, min_actors=3):
    with connect() as c:
        posts=[dict(r) for r in c.execute('SELECT * FROM posts ORDER BY fingerprint,created_at,id')]
        reviews={r['cluster_id']:dict(r) for r in c.execute('SELECT * FROM reviews')}
    groups=defaultdict(list)
    for p in posts: groups[p['fingerprint']].append(p)
    results=[]
    for fp, entries in groups.items():
        # Split into non-overlapping windows anchored at first post, preventing chain bridging.
        batches=[]; batch=[]; start=None
        for p in entries:
            ts=datetime.fromisoformat(p['created_at']).timestamp()
            if batch and ts-start>window_seconds:
                batches.append(batch); batch=[]; start=None
            if not batch: start=ts
            batch.append(p)
        if batch: batches.append(batch)
        for b in batches:
            actors=sorted(set((p['source'],p['actor']) for p in b))
            if len(actors)<min_actors: continue
            key=hashlib.sha256((fp+'|'+b[0]['id']).encode()).hexdigest()[:12]
            results.append({'id':key,'pattern':'exact normalized text in short time window', 'distinct_actors':len(actors),'post_count':len(b),'first_seen':b[0]['created_at'],'last_seen':b[-1]['created_at'],'sample_text':b[0]['text'], 'evidence':[{'id':p['id'],'actor':p['actor'],'source':p['source'],'url':p['url'],'created_at':p['created_at']} for p in b], 'review':reviews.get(key,{'status':'unreviewed','notes':''})})
    return sorted(results,key=lambda x:(-x['distinct_actors'],x['first_seen']))

class Handler(BaseHTTPRequestHandler):
    def reply(self,status,data):
        body=json.dumps(data,ensure_ascii=False).encode()
        self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Access-Control-Allow-Origin','http://localhost:5173'); self.send_header('Access-Control-Allow-Headers','Content-Type'); self.send_header('Access-Control-Allow-Methods','GET, POST, OPTIONS'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_OPTIONS(self): self.reply(200,{})
    def do_GET(self):
        path=urlparse(self.path).path
        if path=='/api/health': return self.reply(200,{'status':'ok','version':'0.1.0','mode':'local prototype'})
        if path=='/api/clusters': return self.reply(200,{'clusters':clusters(),'notice':'Signals are not proof of automation, shared control or wrongdoing.'})
        if path=='/api/stats':
            with connect() as c:
                n=c.execute('SELECT COUNT(*) FROM posts').fetchone()[0]
            return self.reply(200,{'posts':n,'candidate_clusters':len(clusters()),'published_cases':0})
        self.reply(404,{'error':'Not found'})
    def do_POST(self):
        # Localhost only: no public admin endpoint or ingestion until auth and abuse controls exist.
        if self.client_address[0] not in ('127.0.0.1','::1'): return self.reply(403,{'error':'Local only'})
        if urlparse(self.path).path!='/api/load-fixture': return self.reply(404,{'error':'Not found'})
        try:
            with open(FIXTURE,encoding='utf-8') as f: count=ingest(json.load(f))
            self.reply(200,{'inserted':count})
        except (ValueError,OSError) as e: self.reply(400,{'error':str(e)})

if __name__=='__main__':
    connect().close()
    print('OIO local API: http://127.0.0.1:8765')
    ThreadingHTTPServer(('127.0.0.1',8765),Handler).serve_forever()
