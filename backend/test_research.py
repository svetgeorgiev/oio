"""v0.5 research signals: false-positive boundaries and HTTP search limits."""
import http.client
import json
import os
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from app import Handler, clusters, create_investigation, database, ingest
from research import canonical_links, detect_patterns, search_posts

BASE = datetime(2026, 10, 20, 18, 0, tzinfo=timezone.utc)
LONG = 'Community volunteers are sharing the same public statement about scheduled railway maintenance tomorrow morning near the station'


def post(idx, actor, text, seconds=0, source='bsky-jetstream'):
    return {'id':f'{source}:{idx}', 'source':source, 'actor':actor,'text':text,
            'created_at':(BASE+timedelta(seconds=seconds)).isoformat(),
            'url':f'https://bsky.app/profile/example/post/{idx}'}


class SignalResearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_patch = patch('app.DB', os.path.join(self.tmp.name, 'oio.sqlite3'))
        self.db_patch.start()
        # Make these posts count as live, where specified, without changing v0.4 capture.

    def tearDown(self):
        self.db_patch.stop()
        self.tmp.cleanup()

    def test_near_text_groups_variants_from_three_actors(self):
        records=[post(1,'one',LONG,0),
                 post(2,'two',LONG.replace('railway','local railway'),20),
                 post(3,'three',LONG.replace('maintenance','maintenance work'),40)]
        ingest(records)
        found=[x for x in clusters() if x['signal_type']=='near_text']
        self.assertEqual(len(found),1)
        self.assertEqual(found[0]['distinct_actors'],3)
        self.assertEqual(found[0]['post_count'],3)
        self.assertEqual(len(found[0]['evidence']),3)
        self.assertIn('Template',found[0]['reason'])
        record,created=create_investigation({'cluster_id':found[0]['id']})
        self.assertTrue(created)
        self.assertEqual(record['cluster_id'],found[0]['id'])
        self.assertEqual(clusters()[0]['investigation_id'], record['id'])

    def test_canonical_link_across_tracking_variants(self):
        records=[post(1,'one','Please read https://publisher.example.org/story?id=5&utm_source=bsky',0),
                 post(2,'two','Here is https://publisher.example.org/story?utm_campaign=x&id=5',10),
                 post(3,'three','Found https://publisher.example.org/story?id=5#section',15)]
        ingest(records)
        found=[x for x in clusters() if x['signal_type']=='shared_link']
        self.assertEqual(len(found),1)
        self.assertEqual(found[0]['sample_text'],'publisher.example.org/story?id=5')
        self.assertEqual(found[0]['post_count'],3)
        self.assertEqual(len([x for x in clusters() if x['signal_type']=='near_text']),0)

    def test_no_bot_claim_or_group_for_same_actor_or_far_apart(self):
        ingest([post(1,'same',LONG,0),post(2,'same',LONG+' today',1),post(3,'same',LONG+' soon',2)])
        self.assertEqual(clusters(),[])
        ingest([post(4,'a','https://site.example.org/path',3601),
                post(5,'b','https://site.example.org/path',4500),
                post(6,'c','https://site.example.org/path',5600)])
        self.assertEqual(clusters(),[])

    def test_exact_cluster_id_is_not_changed(self):
        original='A made-up announcement is circulating today!'
        ingest([post(i,str(i),original,i) for i in range(3)])
        items=clusters()
        self.assertEqual(len(items),1)
        self.assertEqual(items[0]['signal_type'],'exact_text')
        self.assertEqual(len(items[0]['id']),12)

    def test_invalid_or_generic_link_not_a_shared_link(self):
        self.assertEqual(canonical_links('https://example.org/page https://bsky.app/profile/someone/post/xyz'),set())
        self.assertEqual(canonical_links('https://localhost/private http://127.0.0.1/private https://test.com/'),set())
        self.assertEqual(canonical_links('https://site.example.org/path?q=5&utm_source=social'),{'site.example.org/path?q=5'})

    def test_local_query_is_literal_and_date_bounded(self):
        ingest([post(1,'alpha','News about 100% of reports',0,source='synthetic'),
                post(2,'beta','News about personal stories',5,source='other')])
        self.assertEqual(search_posts(database,scope='all',query='100%')['total_matches'],1)
        self.assertEqual(search_posts(database,scope='live')['total_matches'],0)
        self.assertEqual(search_posts(database,scope='synthetic')['total_matches'],1)
        self.assertEqual(search_posts(database,scope='all',start='2026-10-21T00:00:00Z')['total_matches'],0)
        for kwargs in ({'limit':1000},{'scope':'private'},{'start':'2026-10-20'},{'query':'x'*121},
                       {'start':'2026-10-21T00:00:00Z','end':'2026-10-20T00:00:00Z'}):
            with self.assertRaises(ValueError):search_posts(database,**kwargs)

    def test_api_routes_read_only_and_invalid_search(self):
        ingest([post(1,'test','Something searchable',0,source='synthetic')])
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
        try:
            def get(url):
                conn=http.client.HTTPConnection('127.0.0.1',server.server_address[1],timeout=3)
                conn.request('GET',url)
                response=conn.getresponse(); code=response.status; data=json.loads(response.read()); conn.close()
                return code,data
            status,payload=get('/api/research/search?q=Something&scope=all')
            self.assertEqual(status,200)
            self.assertEqual(payload['total_matches'],1)
            status,payload=get('/api/research/search?limit=123')
            self.assertEqual(status,400)
            status,payload=get('/api/research/signals')
            self.assertEqual(status,200)
            self.assertEqual(payload['counts']['shared_link'],0)
        finally:
            server.shutdown();server.server_close();t.join(3)

    def test_performance_common_text_does_not_generate_near_duplicate_noise(self):
        batch=[post(i, str(i), LONG, i) for i in range(350)]
        signals=detect_patterns(batch)
        self.assertEqual([s for s in signals if s['signal_type']=='near_text'],[])


if __name__=='__main__': unittest.main()
